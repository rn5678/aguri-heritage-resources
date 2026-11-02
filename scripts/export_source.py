#!/usr/bin/env python3
"""Copy the portable, publishable project source into a clean Git checkout.

The local research-library links stay intact. The destination receives ordinary
files, while the two large journal originals remain GitHub Release assets.
Nothing is committed, pushed, or deployed by this command.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = '.source-export.json'
JOURNALS = {
    f'assets/documents/Ugrakshatriya_Pratinidhi_Vol_{n:02}.pdf'
    for n in (1, 2)
}
MAX_ASSET_BYTES = 25 * 1024 * 1024
CODE_SUFFIXES = {'.py', '.mjs', '.cjs'}
EXACT = {
    'README.md', 'LICENSE.txt', '.gitignore', '.gitattributes',
    'push/sw.js', 'push/README.md', 'hosting/PIPELINE.md',
    'local-editor/cloudflare-tools/package.json',
    'local-editor/cloudflare-tools/package-lock.json',
}


class ExportError(ValueError):
    pass


def allowed_path(relative: str) -> bool:
    """Use a positive source allowlist, never a copy-everything exclusion list."""
    path = PurePosixPath(relative)
    if not path.parts or str(path) != relative or path.is_absolute() or '..' in path.parts:
        return False
    if relative in EXACT:
        return True
    if any(part.startswith('.') or part in {'__pycache__', 'node_modules'}
           for part in path.parts):
        return (len(path.parts) == 3 and path.parts[:2] == ('.github', 'workflows')
                and path.suffix in {'.yml', '.yaml'} and not path.name.startswith('.'))
    if len(path.parts) == 1:
        return path.suffix == '.py'
    first = path.parts[0]
    if first == 'content':
        return path.suffix in {'.html', '.json', '.xml', '.txt', '.md'}
    if first == 'assets':
        return relative not in JOURNALS and path.suffix.lower() in {
            '.css', '.js', '.json', '.txt', '.svg', '.png', '.jpg', '.jpeg',
            '.webp', '.gif', '.ico', '.pdf', '.docx', '.woff', '.woff2', '.ttf',
            '.otf', '.mp3', '.mp4', '.webm', '.avif',
        }
    if first == 'scripts':
        return len(path.parts) == 2 and path.suffix in CODE_SUFFIXES
    if first == 'contributions':
        return ((len(path.parts) == 2 and path.suffix in {'.mjs', '.sql', '.md'})
                or (len(path.parts) == 3 and path.parts[1] == 'migrations'
                    and path.suffix == '.sql'))
    if first == 'local-editor':
        return len(path.parts) == 2 and path.suffix in {'.js', '.css', '.html'}
    return False


def digest(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def source_inventory(root: Path) -> dict[str, Path]:
    """Walk only approved folders; do not traverse archives or local state."""
    root = root.resolve(strict=True)
    candidates = list(root.glob('*.py')) + [root / name for name in EXACT]
    for folder in ('content', 'assets', 'scripts', 'contributions',
                   'local-editor', '.github/workflows'):
        base = root / folder
        if base.is_symlink():
            raise ExportError(f'Source directory links are unsupported: {folder}')
        if not base.exists():
            continue
        for directory, dirs, files in os.walk(base, followlinks=False):
            parent = Path(directory)
            # A directory link could conceal unenumerated required source files.
            # Refuse it instead of silently producing an incomplete repository.
            for name in list(dirs):
                entry = parent / name
                rel = entry.relative_to(root).as_posix()
                if name.startswith('.') or name in {'__pycache__', 'node_modules'}:
                    dirs.remove(name)
                elif entry.is_symlink():
                    raise ExportError(f'Source directory links are unsupported: {rel}')
                elif folder == 'local-editor':
                    dirs.remove(name)
            candidates.extend(parent / name for name in files)
    result = {}
    for path in candidates:
        relative = path.relative_to(root).as_posix()
        if not allowed_path(relative) or (not path.exists() and not path.is_symlink()):
            continue
        if path.is_symlink() and not relative.startswith('assets/'):
            raise ExportError(f'Only published assets may be source links: {relative}')
        try:
            resolved = path.resolve(strict=True)
        except (OSError, RuntimeError) as error:
            raise ExportError(f'Broken source link: {relative}') from error
        allowed_root = root / 'assets' if relative.startswith('assets/') else root
        allowed_library = root.parent / 'Aguri_Research_Library'
        if not resolved.is_file() or not (
            resolved.is_relative_to(allowed_root)
            or (relative.startswith('assets/') and resolved.is_relative_to(allowed_library))
        ):
            raise ExportError(f'Source escapes its permitted location: {relative}')
        if relative.startswith('assets/') and resolved.stat().st_size > MAX_ASSET_BYTES:
            raise ExportError(f'Asset exceeds the Pages 25 MiB limit: {relative}')
        result[relative] = path
    for required in ('build.py', 'content/page-history.json', 'contributions/worker.mjs'):
        if required not in result:
            raise ExportError(f'Missing required project source: {required}')
    return dict(sorted(result.items()))


def git_output(destination: Path, *args: str) -> str:
    result = subprocess.run(['git', '-C', str(destination), *args],
                            capture_output=True, text=True, check=False)
    if result.returncode:
        raise ExportError('Destination must be an existing Git checkout.')
    return result.stdout.strip()


def safe_destination(destination: Path, relative: str) -> Path:
    path = destination / relative
    current = path
    while current != destination:
        if current.is_symlink():
            raise ExportError(f'Destination contains a symbolic link: {relative}')
        current = current.parent
    if path.exists() and not path.is_file():
        raise ExportError(f'Destination is not a regular file: {relative}')
    return path


def export_source(root: Path, destination: Path, *, dry_run=False,
                  adopt_existing=()) -> dict:
    root = root.resolve(strict=True)
    destination = destination.resolve(strict=True)
    if destination == root or root.is_relative_to(destination):
        raise ExportError('Use a separate destination checkout, outside the source root’s ancestors.')
    if Path(git_output(destination, 'rev-parse', '--show-toplevel')).resolve() != destination:
        raise ExportError('Destination must be the Git checkout root.')
    if git_output(destination, 'status', '--porcelain', '--untracked-files=all'):
        raise ExportError('Destination has uncommitted changes. Commit or reconcile them before exporting.')
    manifest_path = safe_destination(destination, MANIFEST)
    previous = {}
    if manifest_path.exists():
        try:
            record = json.loads(manifest_path.read_text())
            if record.get('format') != 'aguri-source-export-v1':
                raise ValueError('wrong manifest format')
            previous = record['files']
            if not isinstance(previous, dict) or any(
                not allowed_path(name) or not isinstance(info, dict)
                or not isinstance(info.get('sha256'), str)
                or len(info['sha256']) != 64
                for name, info in previous.items()
            ):
                raise ValueError('invalid managed paths')
        except (ValueError, KeyError, TypeError) as error:
            raise ExportError('The source export manifest is invalid; reconcile it before continuing.') from error
    source = source_inventory(root)
    adopted = set(adopt_existing)
    if any(name not in source for name in adopted):
        raise ExportError('--adopt-existing must name an approved source file present in this export.')
    metadata = {
        name: {'sha256': digest(path), 'bytes': path.stat().st_size}
        for name, path in source.items()
    }
    copy_names, remove_names = [], []
    for name in sorted(source.keys() | previous.keys()):
        target = safe_destination(destination, name)
        actual = digest(target) if target.exists() else None
        if (name in previous and actual is not None and actual != previous[name]['sha256']
                and (name not in metadata or actual != metadata[name]['sha256'])):
            raise ExportError(f'Destination changed independently; reconcile it with local source: {name}')
        if name not in source:
            if target.exists():
                remove_names.append(name)
        elif actual != metadata[name]['sha256']:
            if name not in previous and target.exists() and name not in adopted:
                raise ExportError(f'Existing repository file differs: {name}. Review it, then explicitly use --adopt-existing {name}.')
            copy_names.append(name)
    summary = {
        'dry_run': dry_run, 'source_files': len(source),
        'bytes': sum(info['bytes'] for info in metadata.values()),
        'copy_files': len(copy_names), 'remove_files': len(remove_names),
        'materialized_links': sum(path.is_symlink() for path in source.values()),
        'excluded_journal_originals': sorted(JOURNALS),
    }
    if dry_run:
        return summary
    for name in copy_names:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.source-copy-', delete=False) as stream:
            temporary = Path(stream.name)
        try:
            shutil.copy2(source[name], temporary, follow_symlinks=True)
            # Verify the snapshot did not change while it was being exported.
            if digest(temporary) != metadata[name]['sha256']:
                raise ExportError(f'Source changed during export; reconcile the partial export: {name}')
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
    for name in remove_names:
        (destination / name).unlink()
    record = {'format': 'aguri-source-export-v1', 'files': metadata}
    manifest_path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + '\n')
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path, help='Root of a clean, existing Git checkout')
    parser.add_argument('--dry-run', action='store_true', help='Check and summarize without copying')
    parser.add_argument('--adopt-existing', action='append', default=[], metavar='PATH',
                        help='Explicitly replace this reviewed, unowned repository file on initial import')
    args = parser.parse_args()
    try:
        print(json.dumps(export_source(ROOT, args.destination, dry_run=args.dry_run,
                                       adopt_existing=args.adopt_existing), indent=2))
    except (ExportError, OSError) as error:
        parser.exit(1, f'Source export stopped: {error}\n')


if __name__ == '__main__':
    main()
