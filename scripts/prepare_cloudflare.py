#!/usr/bin/env python3
"""Prepare a portable Pages upload, keeping large journal originals in Releases."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
from html.parser import HTMLParser
from urllib.parse import unquote, urlsplit
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from file_links import JOURNAL_ROUTES
JOURNALS = [f'assets/documents/Ugrakshatriya_Pratinidhi_Vol_{n:02}.pdf' for n in (1, 2)]


def file_digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def journal_metadata(source, repository, tag, remote=False):
    """Use reviewed release metadata for CI without downloading large originals.

    This validates the checked-in metadata, not the current remote release.
    When originals are available locally, require their bytes to match the pin.
    """
    release = f'https://github.com/{repository}/releases/download/{tag}'
    if not remote:
        return [
            {'path': path, 'bytes': (source / path).stat().st_size,
             'sha256': file_digest(source / path),
             'planned_download_url': f'{release}/{Path(path).name}'}
            for path in JOURNALS
        ]
    pinned = json.loads((ROOT / 'content/journal-release.json').read_text())
    if (pinned.get('version') != 1 or pinned.get('repository') != repository
            or pinned.get('tag') != tag):
        raise ValueError('Journal release metadata does not match the requested repository and tag.')
    assets = pinned.get('assets')
    if (not isinstance(assets, list) or len(assets) != len(JOURNALS)
            or any(not isinstance(entry, dict) for entry in assets)
            or any(not isinstance(entry.get('path'), str) for entry in assets)
            or {entry.get('path') for entry in assets} != set(JOURNALS)):
        raise ValueError('Journal release metadata must contain exactly both original volumes.')
    by_path = {entry['path']: entry for entry in assets}
    result = []
    for path in JOURNALS:
        entry = by_path[path]
        expected_url = f'{release}/{Path(path).name}'
        if (type(entry.get('bytes')) is not int or entry['bytes'] <= 0
                or not isinstance(entry.get('sha256'), str)
                or not re.fullmatch(r'[0-9a-f]{64}', entry['sha256'])
                or entry.get('download_url') != expected_url):
            raise ValueError('Invalid pinned journal release metadata: ' + path)
        local = source / path
        if local.exists() and (not local.is_file() or local.stat().st_size != entry['bytes']
                               or file_digest(local) != entry['sha256']):
            raise ValueError('Local journal differs from the pinned release: ' + path)
        result.append({'path': path, 'bytes': entry['bytes'], 'sha256': entry['sha256'],
                       'planned_download_url': expected_url,
                       'metadata_source': 'content/journal-release.json',
                       'local_file_verified': local.is_file()})
    return result


def validate_file_limits(files, upload_method):
    limit = {'dashboard': 1000, 'wrangler': 20000}[upload_method]
    if len(files) > limit or any(path.stat().st_size > 25 * 1024 * 1024 for path in files):
        raise ValueError(f'The hosting copy exceeds Cloudflare Pages {upload_method} limits '
                         f'({limit:,} files; 25 MiB per file).')


class Document(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.refs, self.ids = [], set()
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'id' in attrs:
            if attrs['id'] in self.ids:
                raise ValueError('Duplicate HTML identifier: ' + attrs['id'])
            self.ids.add(attrs['id'])
        for name in ('href', 'src') + (('data',) if tag == 'object' else ()):
            if name in attrs:
                self.refs.append(attrs[name])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', required=True, help='GitHub owner/repository for the journal release')
    parser.add_argument('--tag', default='journals-v1')
    parser.add_argument('--remote-journals', action='store_true',
                        help='Use pinned journal release metadata without requiring local PDFs.')
    parser.add_argument('--skip-archive', action='store_true',
                        help='Prepare the deployment folder without producing a ZIP.')
    parser.add_argument('--upload-method', choices=('dashboard', 'wrangler'), default='dashboard',
                        help='Apply the file-count limit for the intended upload method.')
    args = parser.parse_args(argv)
    if not re.fullmatch(r'[A-Za-z0-9-]+/[A-Za-z0-9_.-]+', args.repository):
        parser.error('Use a GitHub owner/repository name.')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+', args.tag):
        parser.error('Use a simple release tag.')

    source = ROOT / 'site'
    if not (source / 'index.html').is_file():
        raise ValueError('Build the website before preparing a Cloudflare upload.')
    journals = journal_metadata(source, args.repository, args.tag, args.remote_journals)
    output = ROOT / 'hosting/cloudflare'
    output.mkdir(parents=True, exist_ok=True)
    stage = output / 'site'
    stage.mkdir(exist_ok=True)
    wanted = set()
    for path in source.rglob('*'):
        if not path.is_file() or any(part.startswith('.') for part in path.relative_to(source).parts):
            continue
        relative = path.relative_to(source).as_posix()
        if relative in JOURNALS:
            continue
        target = stage / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        wanted.add(relative)

    release = f'https://github.com/{args.repository}/releases/download/{args.tag}'
    redirects = {f'/{path}': f'{release}/{Path(path).name}' for path in JOURNALS}
    # Retired biographies lead to the collection in their original language.
    # Explicit redirects also prevent stale clean-URL asset responses.
    retired_redirects = {
        f'/{language}person-{person}{extension}': f'/{language}people'
        for language in ('', 'bn/')
        for person in ('haricharan-bandhu', 'dhanapati-panja')
        for extension in ('', '.html')
    }
    retired_redirects['/assets/people/haricharan-bandhu-signed-foreword.jpg'] = '/people'
    (stage / '_redirects').write_text(
        ''.join(f'{src} {dst} 301\n' for src, dst in retired_redirects.items())
        + ''.join(f'{src} {dst} 302\n' for src, dst in redirects.items())
    )
    wanted.add('_redirects')
    # Advanced-mode worker: existing API plus the neutral homepage only.
    # Explicit /bn/ pages, articles and assets keep normal static delivery.
    worker = ROOT / 'contributions/worker.mjs'
    if not worker.is_file():
        raise ValueError('Contribution service worker is missing.')
    shutil.copy2(worker, stage / '_worker.js')
    (stage / '_routes.json').write_text(json.dumps({
        'version': 1, 'include': ['/api/*', '/', '/index.html'], 'exclude': []
    }, indent=2) + '\n')
    wanted.update(('_worker.js', '_routes.json'))
    # Remove stale generated assets only from the disposable hosting copy.
    for path in stage.rglob('*'):
        if path.is_file() and path.relative_to(stage).as_posix() not in wanted:
            path.unlink()

    docs = {p.resolve(): Document(p.read_text()) for p in stage.rglob('*.html')}
    for path, doc in docs.items():
        for ref in doc.refs:
            url = urlsplit(ref)
            if url.scheme or url.netloc:
                continue
            if url.path in JOURNAL_ROUTES:
                continue
            target = (path.parent / unquote(url.path)).resolve() if url.path else path
            route = '/' + target.relative_to(stage.resolve()).as_posix()
            if not target.is_file() and route not in redirects:
                raise ValueError(f'Missing asset: {path.name}: {ref}')
            if url.fragment and target in docs and unquote(url.fragment) not in docs[target].ids:
                raise ValueError(f'Missing fragment: {path.name}: {ref}')
    files = sorted(p for p in stage.rglob('*') if p.is_file())
    validate_file_limits(files, args.upload_method)
    archive = output / 'aguri-heritage-upload.zip'
    if args.skip_archive:
        archive.unlink(missing_ok=True)
    else:
        with ZipFile(archive, 'w', ZIP_DEFLATED, compresslevel=6) as z:
            for path in files:
                z.write(path, path.relative_to(stage).as_posix())
    manifest = {
        'provider': 'Cloudflare Pages',
        'proposed_repository': args.repository,
        'proposed_release_tag': args.tag,
        'remote_release_verified': False,
        'upload_method': args.upload_method,
        'deployment_status': 'prepared; awaiting account access and release upload',
        'contribution_service': {
            'worker': '_worker.js',
            'routes': ['/api/*', '/', '/index.html'],
            'required_database_binding': 'CONTRIBUTIONS_DB',
            'required_secret': 'EDITOR_KEY',
            'schema': 'contributions/schema.sql (private; not uploaded)',
            'activation_verified': False,
        },
        'html_pages': len(docs),
        'files': len(files),
        'uncompressed_bytes': sum(p.stat().st_size for p in files),
        'archive_bytes': None if args.skip_archive else archive.stat().st_size,
        'archive_sha256': None if args.skip_archive else file_digest(archive),
        'archive_created': not args.skip_archive,
        'journal_assets': journals,
    }
    (output / 'preparation.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(f'Prepared {len(files)} files and {len(docs)} pages; links and Pages file limits checked.')
    if not args.skip_archive:
        print(f'Upload archive: {archive.stat().st_size / 1024 / 1024:.1f} MiB.')
    else:
        print('Deployment folder prepared; no archive created.')
    print('Release URLs must be verified after the journal files are uploaded, before deployment.')


if __name__ == '__main__':
    main()
