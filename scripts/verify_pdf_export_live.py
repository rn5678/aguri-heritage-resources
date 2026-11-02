#!/usr/bin/env python3
"""Verify the published PDF-export release against the prepared Cloudflare copy.

Uses only Python's standard library. Page and stylesheet requests compare exact
bytes; journal checks use HEAD without following or downloading release assets.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
PREPARED = ROOT / 'hosting/cloudflare/site'
REPORT = ROOT / 'hosting/cloudflare/pdf-export-verification-2026-10-03.json'
ASSETS = ('assets/app.js', 'assets/style.css', 'assets/print.css')
MAX_RESPONSE_BYTES = 2 * 1024 * 1024


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


def digest(content):
    return hashlib.sha256(content).hexdigest()


def route_for(relative):
    path = relative.as_posix()
    if relative.name == 'index.html':
        return '/' if relative.parent == Path('.') else '/' + relative.parent.as_posix() + '/'
    if relative.suffix == '.html' and relative.name != '404.html':
        return '/' + path[:-5]
    return '/' + path


def cache_busted(url, token):
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path,
                       urlencode({'pdf_export_verify': token}), parts.fragment))


def check_file(relative, base, token, timeout):
    expected = (PREPARED / relative).read_bytes()
    url = cache_busted(urljoin(base, route_for(relative)), token)
    expected_statuses = [200, 404] if relative.name == '404.html' else [200]
    result = {
        'file': relative.as_posix(), 'request_method': 'GET', 'request_url': url,
        'expected_statuses': expected_statuses, 'actual_status': None,
        'expected_sha256': digest(expected), 'actual_sha256': None,
        'expected_bytes': len(expected), 'actual_bytes': None, 'passed': False,
    }
    request = Request(url, headers={
        'User-Agent': 'Aguri-Heritage-PDF-Export-Verification/1.0',
        'Cache-Control': 'no-cache', 'Pragma': 'no-cache',
        'Accept-Encoding': 'identity',
    })
    try:
        try:
            response = urlopen(request, timeout=timeout)
        except HTTPError as error:
            response = error  # Compare the custom 404 response body too.
        with response:
            actual = response.read(MAX_RESPONSE_BYTES + 1)
            result.update({
                'actual_status': response.code, 'response_url': response.url,
                'actual_bytes': len(actual),
                'content_type': response.headers.get('Content-Type'),
                'cache_status': response.headers.get('CF-Cache-Status'),
            })
        if len(actual) > MAX_RESPONSE_BYTES:
            result['error'] = 'Response exceeded the bounded verification size.'
        else:
            result['actual_sha256'] = digest(actual)
            result['passed'] = (
                result['actual_status'] in expected_statuses
                and result['actual_sha256'] == result['expected_sha256']
            )
    except (OSError, URLError, TimeoutError) as error:
        result['error'] = str(error)
    return result


def check_journal(rule, base, token, timeout):
    route, destination, expected_status = rule
    url = cache_busted(urljoin(base, route), token)
    result = {
        'file': route.lstrip('/'), 'request_method': 'HEAD', 'request_url': url,
        'expected_status': expected_status, 'actual_status': None,
        'expected_location': destination, 'actual_location': None,
        'followed_redirect': False, 'downloaded_body_bytes': 0, 'passed': False,
    }
    request = Request(url, method='HEAD', headers={
        'User-Agent': 'Aguri-Heritage-PDF-Export-Verification/1.0',
        'Cache-Control': 'no-cache', 'Pragma': 'no-cache',
    })
    try:
        try:
            response = build_opener(NoRedirect()).open(request, timeout=timeout)
        except HTTPError as error:
            response = error  # Redirects are deliberately not followed.
        with response:
            location = response.headers.get('Location')
            result.update({'actual_status': response.code, 'actual_location': location})
        expected = urlsplit(destination)
        actual = urlsplit(urljoin(url, location)) if location else None
        allowed_queries = {'', urlsplit(url).query}
        result['passed'] = (
            result['actual_status'] == expected_status
            and actual is not None
            and (actual.scheme, actual.netloc, actual.path) ==
                (expected.scheme, expected.netloc, expected.path)
            and actual.query in allowed_queries
            and not actual.fragment
        )
    except (OSError, URLError, TimeoutError) as error:
        result['error'] = str(error)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    configured_url = json.loads((ROOT / 'content/site-config.json').read_text())['url']
    parser.add_argument('--base-url', default=configured_url,
                        help='Published origin; defaults to content/site-config.json.')
    parser.add_argument('--timeout', type=float, default=15,
                        help='Timeout per request in seconds (default: 15).')
    parser.add_argument('--workers', type=int, default=6,
                        help='Concurrent requests, from 1 to 6 (default: 6).')
    args = parser.parse_args()
    if not 1 <= args.workers <= 6 or not 0 < args.timeout <= 60:
        parser.error('Use 1-6 workers and a timeout greater than zero, at most 60 seconds.')
    parts = urlsplit(args.base_url)
    if parts.scheme != 'https' or not parts.netloc or parts.query or parts.fragment or parts.path not in ('', '/'):
        parser.error('The base URL must be an HTTPS origin without a query or fragment.')
    base = args.base_url.rstrip('/') + '/'
    html = sorted(path.relative_to(PREPARED) for path in PREPARED.rglob('*.html'))
    if not html:
        parser.error('The prepared Cloudflare folder has no HTML pages.')
    files = html + [Path(name) for name in ASSETS]
    rules = []
    for line in (PREPARED / '_redirects').read_text().splitlines():
        fields = line.strip().split()
        if not fields or fields[0].startswith('#'):
            continue
        if fields[0].startswith('/assets/documents/Ugrakshatriya_Pratinidhi_Vol_'):
            if len(fields) != 3 or not fields[1].startswith('https://github.com/'):
                parser.error('Unexpected prepared journal redirect rule.')
            rules.append((fields[0], fields[1], int(fields[2])))
    if len(rules) != 2:
        parser.error('Expected both prepared journal redirect rules.')
    started = datetime.now(timezone.utc)
    token = started.strftime('%Y%m%dT%H%M%S%fZ')
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        file_results = list(pool.map(lambda relative: check_file(relative, base, token, args.timeout), files))
        journal_results = list(pool.map(lambda rule: check_journal(rule, base, token, args.timeout), rules))
    finished = datetime.now(timezone.utc)
    passed = all(item['passed'] for item in file_results + journal_results)
    report = {
        'feature': 'Page PDF export', 'site_url': base, 'passed': passed,
        'started_at_utc': started.isoformat(), 'verified_at_utc': finished.isoformat(),
        'verified_at_india': finished.astimezone(ZoneInfo('Asia/Kolkata')).isoformat(),
        'elapsed_seconds': round((finished - started).total_seconds(), 2),
        'cache_bust_token': token, 'request_timeout_seconds': args.timeout,
        'concurrent_workers': args.workers, 'expected_html_pages': len(html),
        'verified_html_pages': sum(item['passed'] for item in file_results if item['file'].endswith('.html')),
        'expected_assets': len(ASSETS),
        'verified_assets': sum(item['passed'] for item in file_results if item['file'] in ASSETS),
        'verified_journal_redirects': sum(item['passed'] for item in journal_results),
        'files': file_results, 'journal_redirects': journal_results,
    }
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({key: report[key] for key in (
        'passed', 'verified_html_pages', 'expected_html_pages', 'verified_assets',
        'expected_assets', 'verified_journal_redirects', 'elapsed_seconds',
    )}, indent=2))
    print('Report: ' + str(REPORT))
    if not passed:
        for item in file_results + journal_results:
            if not item['passed']:
                print('FAIL: ' + item['file'] + ': ' + item.get('error', 'status, hash or redirect mismatch'), file=sys.stderr)
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
