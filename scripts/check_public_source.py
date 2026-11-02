#!/usr/bin/env python3
"""Check the tracked, portable source before a public GitHub build.

The optional export manifest records migration ownership, not a restriction on
later GitHub edits. All currently tracked files are checked independently.
Generated translation assets may change during a build, so hashes are not compared.
Recognizable credential checks complement the path allowlist; they are not a
general proof that arbitrary document text contains no private information.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess

from export_source import JOURNALS, MANIFEST, allowed_path

ROOT = Path(__file__).resolve().parents[1]
MAX_FILE_BYTES = 100 * 1024 * 1024
TEXT_SUFFIXES = {'.py', '.mjs', '.cjs', '.js', '.css', '.html', '.json',
                 '.xml', '.txt', '.md', '.sql', '.yaml', '.yml', '.svg'}
PRIVATE_PARTS = {'research', 'output', 'tmp', 'site', '__pycache__', 'node_modules',
                 '.wrangler', '.local', '.cache', 'backups', 'publishing', 'translation',
                 'indexnow', 'Claude outputs', 'Aguri_Research_Library'}
CREDENTIAL_PATTERNS = (
    re.compile(rb'gh[pousr]_[A-Za-z0-9]{36,}'),
    re.compile(rb'github_pat_[A-Za-z0-9_]{40,}'),
    re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    re.compile(rb'\bAKIA[A-Z0-9]{16}\b'),
)


class SourceCheckError(ValueError):
    pass


def git(root, *arguments):
    result = subprocess.run(['git', '-C', str(root), *arguments], capture_output=True,
                            check=False)
    if result.returncode:
        raise SourceCheckError('Run CI from the exported Git checkout, not the local authoring '
                               'folder. Export the source and stage its files first.')
    return result.stdout


def tracked_inventory(root):
    if Path(git(root, 'rev-parse', '--show-toplevel').decode().strip()).resolve() != root.resolve():
        raise SourceCheckError('Run the source check from the exported Git repository root.')
    result = {}
    for entry in git(root, 'ls-files', '--stage', '-z').split(b'\0'):
        if not entry:
            continue
        info, raw_path = entry.split(b'\t', 1)
        mode, _, stage = info.decode('ascii').split()
        name = raw_path.decode('utf-8')
        if stage != '0' or mode not in {'100644', '100755'}:
            raise SourceCheckError('Tracked links, submodules, or unresolved conflicts are forbidden: ' + name)
        result[name] = mode
    return result


def forbidden_path(name):
    path = Path(name)
    return (any(part in PRIVATE_PARTS for part in path.parts)
            or any(part == '.env' or part.startswith('.env.') or part.startswith('.dev.vars')
                   for part in path.parts)
            or any(part.endswith(('.sqlite', '.sqlite3', '.db', '.sqlite-wal', '.sqlite-shm'))
                   for part in path.parts)
            or path.suffix in {'.pem', '.key', '.p12', '.pfx', '.log', '.pyc'})


def check_source(root=ROOT):
    root = Path(root).resolve(strict=True)
    tracked = tracked_inventory(root)
    required = {'build.py', 'content/page-history.json', 'contributions/worker.mjs'}
    if missing := required - tracked.keys():
        raise SourceCheckError('Required source files are not tracked: ' + ', '.join(sorted(missing)))
    for name in tracked:
        if name != MANIFEST and (forbidden_path(name) or not allowed_path(name)):
            reason = 'Journal originals must remain release assets' if name in JOURNALS else 'Unapproved public source path'
            raise SourceCheckError(f'{reason}: {name}')
        path = root / name
        if path.is_symlink() or any(parent.is_symlink() for parent in path.parents if parent != root and root in parent.parents):
            raise SourceCheckError('Public source must contain ordinary files, not library links: ' + name)
        if not path.is_file():
            raise SourceCheckError('Tracked source file is missing: ' + name)
        if path.stat().st_size > MAX_FILE_BYTES:
            raise SourceCheckError('Tracked file exceeds the 100 MiB GitHub limit: ' + name)
        if path.suffix.lower() in TEXT_SUFFIXES:
            data = path.read_bytes()
            if any(pattern.search(data) for pattern in CREDENTIAL_PATTERNS):
                # Never repeat the matching credential in an error or build log.
                raise SourceCheckError('A recognizable private credential appears in tracked source: ' + name)
    if MANIFEST in tracked:
        try:
            manifest = json.loads((root / MANIFEST).read_text())
            files = manifest['files']
            if (manifest.get('format') != 'aguri-source-export-v1' or not isinstance(files, dict)
                    or any(not allowed_path(name) or not isinstance(info, dict)
                           or not isinstance(info.get('sha256'), str)
                           or not re.fullmatch(r'[0-9a-f]{64}', info['sha256'])
                           or type(info.get('bytes')) is not int or info['bytes'] < 0
                           for name, info in files.items())):
                raise ValueError('invalid manifest')
        except (ValueError, KeyError, TypeError) as error:
            raise SourceCheckError('The optional source export inventory is invalid; reconcile it before exporting again.') from error
    return len(tracked)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        count = check_source(args.root)
    except (SourceCheckError, OSError) as error:
        parser.exit(1, f'Public source check failed: {error}\n')
    print(f'PASS: {count} tracked source files; portability and private-file exclusions checked.')


if __name__ == '__main__':
    main()
