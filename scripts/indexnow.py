#!/usr/bin/env python3
"""Notify IndexNow after a confirmed production deployment, never deploy a site.

First use: python3 scripts/indexnow.py --all
Later uses compare the prepared HTML with the last accepted inventory. Run only
after that exact prepared version is live. Receipts and state stay outside the
public upload. A receipt confirms notification, not crawling or indexing.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import ipaddress
import json
import os
from pathlib import Path
import re
import ssl
import sys
import tempfile
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlsplit
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

ENDPOINT = 'https://api.indexnow.org/indexnow'
MAX_URLS = 10_000
ROOT = Path(__file__).resolve().parents[1]


class IndexNowError(ValueError):
    """A concise, safe explanation suitable for a publication receipt."""


def _base_url(value):
    parts = urlsplit(value)
    host = parts.hostname or ''
    if (parts.scheme != 'https' or parts.netloc != host or parts.path not in ('', '/')
            or parts.query or parts.fragment or '.' not in host
            or not re.fullmatch(r'[a-z0-9.-]+', host)
            or host.endswith(('.localhost', '.local', '.internal', '.test', '.invalid'))):
        raise IndexNowError('IndexNow requires the configured public HTTPS site origin.')
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return value.rstrip('/')
    raise IndexNowError('IndexNow requires a public website hostname.')


def _public_url(value, base_url):
    parts = urlsplit(value)
    if (parts.scheme + '://' + parts.netloc != base_url or parts.query or parts.fragment
            or not parts.path.startswith('/') or '//' in parts.path
            or any(ord(c) < 33 for c in value) or '\\' in value
            or any(p in ('.', '..') for p in unquote(parts.path).split('/'))
            or '\\' in unquote(parts.path)):
        raise IndexNowError('The sitemap contains a URL outside the canonical public site.')
    return value


def _page_path(url, base_url):
    """Map Cloudflare's clean canonical URLs to their prepared HTML files."""
    _public_url(url, base_url)
    path = unquote(urlsplit(url).path).lstrip('/')
    if not path or path.endswith('/'):
        path += 'index.html'
    elif not path.endswith('.html'):
        path += '.html'
    return path


def sitemap_urls(sitemap, base_url):
    """Read canonical sitemap URLs from a Path, XML text, or XML bytes."""
    if isinstance(sitemap, Path):
        data = sitemap.read_bytes()
    elif isinstance(sitemap, str) and not sitemap.lstrip().startswith('<'):
        data = Path(sitemap).read_bytes()
    else:
        data = sitemap
    try:
        root = ET.fromstring(data)
    except (ET.ParseError, TypeError):
        raise IndexNowError('The prepared sitemap could not be read.') from None
    if root.tag.rsplit('}', 1)[-1] != 'urlset':
        raise IndexNowError('IndexNow expects the prepared URL sitemap, not a sitemap index.')
    result = []
    for node in root:
        if node.tag.rsplit('}', 1)[-1] != 'url':
            continue
        values = [child.text.strip() for child in node
                  if child.tag.rsplit('}', 1)[-1] == 'loc' and child.text]
        if len(values) != 1:
            raise IndexNowError('A sitemap entry has no unique canonical URL.')
        result.append(_public_url(values[0], base_url))
    if not result or len(result) != len(set(result)):
        raise IndexNowError('The sitemap is empty or repeats canonical URLs.')
    return result


def _manifest(value):
    if isinstance(value, (str, Path)):
        value = json.loads(Path(value).read_text())
    if value is not None and (not isinstance(value, dict)
                             or any(not isinstance(k, str) or not isinstance(v, str)
                                    for k, v in value.items())):
        raise IndexNowError('The prepared file manifest could not be read.')
    return value


def _checked_file(site_dir, relative, manifest):
    path = site_dir / relative
    if not path.resolve().is_relative_to(site_dir.resolve()) or path.is_symlink() or not path.is_file():
        raise IndexNowError('A canonical page or verification file is missing from the prepared site.')
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if manifest is not None and manifest.get(relative) != digest:
        raise IndexNowError('The prepared site differs from its checked file manifest.')
    return data, digest


class _Page(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.canonicals = []
        self.noindex = False
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'link' and 'canonical' in attrs.get('rel', '').lower().split():
            self.canonicals.append(attrs.get('href'))
        if tag == 'meta' and attrs.get('name', '').lower() in ('robots', 'bingbot'):
            directives = re.split(r'[\s,;]+', attrs.get('content', '').lower())
            self.noindex |= 'noindex' in directives or 'none' in directives


def build_inventory(site_dir, base_url, manifest=None):
    """Return canonical public URL → prepared HTML SHA-256, verifying each file."""
    site_dir = Path(site_dir)
    base_url = _base_url(base_url)
    manifest = _manifest(manifest)
    sitemap, _ = _checked_file(site_dir, 'sitemap.xml', manifest)
    result = {}
    for url in sitemap_urls(sitemap, base_url):
        data, digest = _checked_file(site_dir, _page_path(url, base_url), manifest)
        page = _Page(data.decode('utf-8'))
        if page.noindex or page.canonicals != [url]:
            raise IndexNowError('A sitemap page is not indexable at its declared canonical URL.')
        result[url] = digest
    return result


def previous_inventory(manifest, sitemap, base_url):
    """Recover the old canonical inventory even after its HTML was discarded."""
    manifest = _manifest(manifest)
    result = {}
    for url in sitemap_urls(sitemap, base_url):
        digest = manifest.get(_page_path(url, base_url))
        if not digest:
            raise IndexNowError('The previous sitemap does not match its file manifest.')
        result[url] = digest
    return result


def changed_urls(current, previous):
    """Include added/changed canonical pages and removed old canonical URLs."""
    return sorted(url for url in current.keys() | previous.keys()
                  if current.get(url) != previous.get(url))


def _tls_context():
    context = ssl.create_default_context()
    if sys.platform == 'darwin' and Path('/etc/ssl/cert.pem').is_file():
        context.load_verify_locations(cafile='/etc/ssl/cert.pem')
    return context


def _request(request, opener):
    return (opener or urlopen)(request, timeout=25, context=_tls_context())


def verify_public_key(base_url, key, opener=None):
    """Require the deployed root key file to return its expected UTF-8 text."""
    location = base_url + '/' + key + '.txt'
    request = Request(location, headers={'Accept': 'text/plain', 'User-Agent': 'Aguri-IndexNow/1.0'})
    try:
        with _request(request, opener) as response:
            if response.status != 200 or response.geturl() != location:
                raise IndexNowError('The public IndexNow key file could not be verified.')
            if response.read(256).decode('utf-8').strip() != key:
                raise IndexNowError('The public IndexNow key file does not match the prepared key.')
    except HTTPError as exc:
        exc.close()
        raise IndexNowError('The public IndexNow key file could not be verified.') from None
    except (URLError, TimeoutError, UnicodeError, OSError):
        raise IndexNowError('The public IndexNow key file could not be verified.') from None
    return location


def _post_urls(base_url, key, key_location, urls, opener=None):
    if not 0 < len(urls) <= MAX_URLS:
        raise IndexNowError('An IndexNow notification must contain 1 to 10,000 URLs.')
    body = json.dumps({'host': urlsplit(base_url).netloc, 'key': key,
                       'keyLocation': key_location, 'urlList': urls}).encode('utf-8')
    request = Request(ENDPOINT, data=body, method='POST', headers={
        'Content-Type': 'application/json; charset=utf-8', 'User-Agent': 'Aguri-IndexNow/1.0'})
    try:
        with _request(request, opener) as response:
            # Never accept a redirected submission as a successful notification.
            return response.status if response.geturl() == ENDPOINT else 0
    except HTTPError as exc:
        code = exc.code
        exc.close()
        return code
    except (URLError, TimeoutError, OSError):
        return 0


def _outside_site(path, site_dir):
    path = Path(path)
    if path.resolve().is_relative_to(site_dir.resolve()):
        raise IndexNowError('IndexNow state and receipts must stay outside the public upload.')
    return path


def _save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, prefix='.indexnow-',
                                     suffix='.tmp', delete=False) as stream:
        temporary = Path(stream.name)
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write('\n')
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def submit_after_deploy(root, site_dir, manifest=None, *, previous_manifest=None,
                        previous_sitemap=None, all_urls=False, state_path=None, opener=None):
    """Submit only changed canonical URLs after the caller confirms deployment.

    Saved accepted state is authoritative. Without state or a previous inventory,
    the first submission requires all_urls=True. Repeating that option with saved
    state still skips unchanged URLs. Failures never advance their inventory.
    """
    root, site_dir = Path(root), Path(site_dir)
    receipt = {'completedAt': datetime.now(timezone.utc).isoformat(timespec='seconds'),
               'endpoint': ENDPOINT, 'status': 'failed', 'submitted': 0, 'batches': []}
    receipt_path = None
    try:
        state_path = _outside_site(state_path or root/'local-editor/indexnow/state.json', site_dir)
        receipt_path = _outside_site(state_path.parent/'last-submission.json', site_dir)
        config = json.loads((root/'content/site-config.json').read_text())
        base_url = _base_url(config['url'])
        key = config.get('indexnow_key', '')
        if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9-]{8,128}', key):
            raise IndexNowError('A valid IndexNow key is not configured.')
        if manifest is None and (site_dir.parent/'manifest.json').is_file():
            manifest = site_dir.parent/'manifest.json'
        manifest = _manifest(manifest)
        current = build_inventory(site_dir, base_url, manifest)
        key_data, _ = _checked_file(site_dir, key + '.txt', manifest)
        if key_data.decode('utf-8').strip() != key:
            raise IndexNowError('The prepared IndexNow key file does not match the configured key.')
        previous = None
        if state_path.is_file():
            state = json.loads(state_path.read_text())
            if state.get('version') != 1 or state.get('siteUrl') != base_url:
                raise IndexNowError('The saved IndexNow inventory belongs to a different site or format.')
            previous = state.get('inventory')
            if not isinstance(previous, dict) or any(not isinstance(d, str) for d in previous.values()):
                raise IndexNowError('The saved IndexNow inventory could not be read.')
            for url in previous:
                _public_url(url, base_url)
        elif previous_manifest is not None and previous_sitemap is not None:
            previous = previous_inventory(previous_manifest, previous_sitemap, base_url)
        elif previous_manifest is not None:
            # Without the old sitemap, compare surviving pages but do not guess
            # which removed HTML files were previously canonical public pages.
            old_manifest = _manifest(previous_manifest)
            previous = {url: old_manifest[_page_path(url, base_url)] for url in current
                        if _page_path(url, base_url) in old_manifest}
        elif all_urls:
            previous = {}
        if previous is None:
            receipt.update(status='skipped', message='Initial notification requires --all or a previous canonical inventory.')
        else:
            urls = changed_urls(current, previous)
            receipt.update(added=sum(url not in previous for url in urls),
                           updated=sum(url in current and url in previous for url in urls),
                           removed=sum(url not in current for url in urls))
            if not urls:
                receipt.update(status='skipped', message='No canonical page content changed.')
            else:
                location = verify_public_key(base_url, key, opener)
                accepted = dict(previous)
                for offset in range(0, len(urls), MAX_URLS):
                    batch = urls[offset:offset + MAX_URLS]
                    code = _post_urls(base_url, key, location, batch, opener)
                    status = {200: 'received', 202: 'pending'}.get(code, 'failed')
                    receipt['batches'].append({'status': status, 'httpStatus': code, 'urls': batch})
                    if code not in (200, 202):
                        receipt['message'] = 'IndexNow did not accept this notification; retry after checking the receipt.'
                        break
                    for url in batch:
                        if url in current:
                            accepted[url] = current[url]
                        else:
                            accepted.pop(url, None)
                    _save(state_path, {'version': 1, 'siteUrl': base_url, 'inventory': accepted,
                                       'acceptedAt': receipt['completedAt']})
                    receipt['submitted'] += len(batch)
                if receipt['submitted'] == len(urls):
                    receipt['status'] = ('pending' if any(b['httpStatus'] == 202 for b in receipt['batches'])
                                         else 'received')
    except IndexNowError as exc:
        receipt['message'] = str(exc)
    except (OSError, ValueError, TypeError, KeyError):
        receipt['message'] = 'IndexNow could not read or save its checked publication files.'
    if receipt_path is not None:
        try:
            _save(receipt_path, receipt)
        except OSError:
            receipt['message'] = 'The IndexNow receipt could not be saved locally.'
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--site', type=Path, help='Exact prepared site already deployed to production')
    parser.add_argument('--manifest', type=Path, help='Prepared path-to-SHA-256 manifest')
    parser.add_argument('--previous-manifest', type=Path)
    parser.add_argument('--previous-sitemap', type=Path)
    parser.add_argument('--state', type=Path, help='Private local state outside the public site')
    parser.add_argument('--all', action='store_true', help='Explicit initial canonical inventory notification')
    args = parser.parse_args(argv)
    receipt = submit_after_deploy(args.root, args.site or args.root/'hosting/cloudflare/site', args.manifest,
                                  previous_manifest=args.previous_manifest, previous_sitemap=args.previous_sitemap,
                                  all_urls=args.all, state_path=args.state)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 1 if receipt['status'] == 'failed' else 0


if __name__ == '__main__':
    raise SystemExit(main())
