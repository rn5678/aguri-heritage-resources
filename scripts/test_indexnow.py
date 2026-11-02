#!/usr/bin/env python3
"""IndexNow regression tests with temporary files and a fully mocked network."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

SPEC = importlib.util.spec_from_file_location('indexnow_tested', Path(__file__).with_name('indexnow.py'))
indexnow = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(indexnow)

BASE = 'https://example.org'
KEY = 'test-indexnow-key-12345678'


class Response:
    def __init__(self, url, status=200, body=b''):
        self.url, self.status, self.body = url, status, body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def geturl(self):
        return self.url

    def read(self, length=-1):
        return self.body[:length] if length >= 0 else self.body


class IndexNowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='aguri-indexnow-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.site = self.root/'prepared/site'
        self.site.mkdir(parents=True)
        (self.root/'content').mkdir()
        self.config = {'url': BASE, 'indexnow_key': KEY}
        self.write_config()
        (self.site/(KEY + '.txt')).write_text(KEY + '\n')
        self.pages = {'/': 'Homepage', '/history': 'History', '/bn/': 'বাংলা'}
        self.write_site()
        self.calls = []
        self.codes = []
        self.key_body = KEY.encode()
        self.key_redirect = None
        self.opener = Mock(side_effect=self.open_request)
        network = patch.object(indexnow, 'urlopen', side_effect=AssertionError('Tests must never contact the network'))
        network.start()
        self.addCleanup(network.stop)

    def write_config(self):
        (self.root/'content/site-config.json').write_text(json.dumps(self.config))

    def write_site(self):
        for route, text in self.pages.items():
            path = self.site/indexnow._page_path(BASE + route, BASE)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f'<html><head><link rel="canonical" href="{BASE + route}"></head>'
                            f'<body><h1>{text}</h1></body></html>')
        self.sitemap = ('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                        + ''.join(f'<url><loc>{BASE + route}</loc></url>' for route in self.pages)
                        + '</urlset>')
        (self.site/'sitemap.xml').write_text(self.sitemap)

    def manifest(self):
        return {p.relative_to(self.site).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in self.site.rglob('*') if p.is_file()}

    @property
    def state_path(self):
        return self.root/'local-editor/indexnow/state.json'

    def state(self):
        return json.loads(self.state_path.read_text())

    def open_request(self, request, **kwargs):
        self.assertIn('context', kwargs)
        self.assertGreater(kwargs['timeout'], 0)
        self.calls.append(request)
        if request.get_method() == 'GET':
            self.assertEqual(request.full_url, BASE + '/' + KEY + '.txt')
            return Response(self.key_redirect or request.full_url, body=self.key_body)
        self.assertEqual(request.full_url, indexnow.ENDPOINT)
        self.assertEqual(request.get_method(), 'POST')
        self.assertEqual(request.get_header('Content-type'), 'application/json; charset=utf-8')
        code = self.codes.pop(0) if self.codes else 200
        if code >= 400:
            raise HTTPError(request.full_url, code, 'Remote details must stay private', {}, None)
        return Response(request.full_url, status=code)

    def submit(self, **kwargs):
        return indexnow.submit_after_deploy(self.root, self.site, opener=self.opener, **kwargs)

    def payloads(self):
        return [json.loads(r.data) for r in self.calls if r.get_method() == 'POST']

    def test_initial_requires_explicit_all_and_does_not_advance_state(self):
        receipt = self.submit()
        self.assertEqual(receipt['status'], 'skipped')
        self.assertIn('--all', receipt['message'])
        self.assertFalse(self.state_path.exists())
        self.opener.assert_not_called()

    def test_initial_all_verifies_key_and_records_received_without_claiming_indexed(self):
        receipt = self.submit(all_urls=True, manifest=self.manifest())
        self.assertEqual(receipt['status'], 'received')
        self.assertEqual(receipt['submitted'], 3)
        self.assertEqual(self.state()['inventory'], indexnow.build_inventory(self.site, BASE))
        payload = self.payloads()[0]
        self.assertEqual(payload['host'], 'example.org')
        self.assertEqual(payload['key'], KEY)
        self.assertEqual(payload['keyLocation'], BASE + '/' + KEY + '.txt')
        self.assertEqual(payload['urlList'], sorted(BASE + p for p in self.pages))
        self.assertTrue((self.state_path.parent/'last-submission.json').is_file())
        self.assertFalse((self.site/'state.json').exists())

    def test_repeat_all_or_normal_run_never_notifies_unchanged_content(self):
        self.submit(all_urls=True)
        state_bytes = self.state_path.read_bytes()
        self.calls.clear()
        self.opener.reset_mock()
        for kwargs in ({}, {'all_urls': True}):
            receipt = self.submit(**kwargs)
            self.assertEqual(receipt['status'], 'skipped')
        self.assertEqual(self.state_path.read_bytes(), state_bytes)
        self.opener.assert_not_called()

    def test_diff_submits_added_updated_and_removed_canonical_pages(self):
        self.submit(all_urls=True)
        self.calls.clear()
        self.pages['/history'] = 'Updated history'
        self.pages['/sources'] = 'Sources'
        del self.pages['/bn/']
        self.write_site()
        receipt = self.submit()
        self.assertEqual((receipt['added'], receipt['updated'], receipt['removed']), (1, 1, 1))
        self.assertEqual(self.payloads()[0]['urlList'],
                         [BASE + '/bn/', BASE + '/history', BASE + '/sources'])
        self.assertNotIn(BASE + '/bn/', self.state()['inventory'])
        self.assertEqual(self.submit()['status'], 'skipped')

    def test_prior_manifest_and_sitemap_support_removed_pages_without_old_html(self):
        old_manifest, old_sitemap = self.manifest(), self.sitemap
        del self.pages['/history']
        self.pages['/bn/'] = 'নতুন বাংলা'
        self.write_site()
        (self.site/'history.html').unlink()
        receipt = self.submit(previous_manifest=old_manifest, previous_sitemap=old_sitemap)
        self.assertEqual(receipt['status'], 'received')
        self.assertEqual(self.payloads()[0]['urlList'], [BASE + '/bn/', BASE + '/history'])
        self.assertEqual(self.state()['inventory'], indexnow.build_inventory(self.site, BASE))

    def test_prior_manifest_alone_never_guesses_removed_private_pages(self):
        old_manifest = self.manifest()
        old_manifest['private.html'] = 'old'
        self.pages['/history'] = 'Updated history'
        self.write_site()
        receipt = self.submit(previous_manifest=old_manifest)
        self.assertEqual(receipt['submitted'], 1)
        self.assertEqual(self.payloads()[0]['urlList'], [BASE + '/history'])

    def test_pending_is_receipted_and_accepted_inventory_does_not_repeat(self):
        self.codes = [202]
        receipt = self.submit(all_urls=True)
        self.assertEqual(receipt['status'], 'pending')
        self.assertEqual(receipt['batches'][0]['httpStatus'], 202)
        self.assertEqual(self.submit()['status'], 'skipped')

    def test_failed_submission_preserves_state_and_redacts_remote_details(self):
        self.submit(all_urls=True)
        before = self.state_path.read_bytes()
        self.pages['/history'] = 'Updated'
        self.write_site()
        for code in (403, 422, 429, 500):
            self.codes = [code]
            receipt = self.submit()
            self.assertEqual(receipt['status'], 'failed')
            self.assertEqual(receipt['batches'][0]['httpStatus'], code)
            self.assertEqual(self.state_path.read_bytes(), before)
            self.assertNotIn('Remote details', json.dumps(receipt))
        self.assertEqual(self.submit()['submitted'], 1)

    def test_batches_preserve_successes_and_retry_only_failed_urls(self):
        with patch.object(indexnow, 'MAX_URLS', 2):
            self.codes = [200, 429]
            receipt = self.submit(all_urls=True)
            self.assertEqual(receipt['status'], 'failed')
            self.assertEqual(receipt['submitted'], 2)
            self.assertEqual(len(self.state()['inventory']), 2)
            self.assertEqual([len(p['urlList']) for p in self.payloads()], [2, 1])
            self.calls.clear()
            receipt = self.submit()
            self.assertEqual(receipt['submitted'], 1)
            self.assertEqual(len(self.payloads()[0]['urlList']), 1)

    def test_public_key_must_match_and_cannot_redirect(self):
        for body, redirect in ((b'wrong', None), (KEY.encode(), 'https://elsewhere.org/key.txt')):
            self.key_body, self.key_redirect = body, redirect
            receipt = self.submit(all_urls=True)
            self.assertEqual(receipt['status'], 'failed')
            self.assertFalse(self.state_path.exists())
            self.assertEqual(self.payloads(), [])

    def test_unreachable_public_key_does_not_submit_or_expose_exception(self):
        self.opener.side_effect = URLError('Sensitive local proxy details')
        receipt = self.submit(all_urls=True)
        self.assertEqual(receipt['status'], 'failed')
        self.assertFalse(self.state_path.exists())
        self.assertNotIn('Sensitive', json.dumps(receipt))

    def test_manifest_tampering_fails_before_network(self):
        manifest = self.manifest()
        (self.site/'history.html').write_text('Changed after checks')
        receipt = self.submit(all_urls=True, manifest=manifest)
        self.assertEqual(receipt['status'], 'failed')
        self.opener.assert_not_called()

    def test_job_manifest_is_discovered_automatically(self):
        (self.site.parent/'manifest.json').write_text(json.dumps(self.manifest()))
        (self.site/'history.html').write_text('Changed after checks')
        receipt = self.submit(all_urls=True)
        self.assertEqual(receipt['status'], 'failed')
        self.opener.assert_not_called()

    def test_canonical_or_noindex_mismatch_fails_before_network(self):
        path = self.site/'history.html'
        original = path.read_text()
        bad_pages = [original.replace(BASE + '/history', BASE + '/other'),
                     original.replace('</head>', '<meta name="robots" content="noindex, follow"></head>'),
                     original.replace('</head>', '<meta name="bingbot" content="none"></head>')]
        for text in bad_pages:
            path.write_text(text)
            self.assertEqual(self.submit(all_urls=True)['status'], 'failed')
        self.opener.assert_not_called()

    def test_foreign_query_traversal_and_fragment_urls_fail_before_network(self):
        for url in ('https://evil.example/', BASE + '/history?draft=1', BASE + '/%2e%2e/private',
                    BASE + '/history#section', BASE + '/a%5cb', BASE + '//history'):
            (self.site/'sitemap.xml').write_text(f'<urlset><url><loc>{url}</loc></url></urlset>')
            self.assertEqual(self.submit(all_urls=True)['status'], 'failed', url)
        self.opener.assert_not_called()

    def test_state_cannot_be_written_inside_public_upload(self):
        receipt = self.submit(all_urls=True, state_path=self.site/'private/state.json')
        self.assertEqual(receipt['status'], 'failed')
        self.assertFalse((self.site/'private').exists())
        self.opener.assert_not_called()

    def test_local_key_must_be_part_of_the_checked_upload(self):
        (self.site/(KEY + '.txt')).unlink()
        self.assertEqual(self.submit(all_urls=True)['status'], 'failed')
        self.opener.assert_not_called()

    def test_private_site_origin_is_rejected(self):
        for value in ('http://example.org', 'https://localhost', 'https://127.0.0.1',
                      'https://example.local', 'https://user@example.org', 'https://example.org:8443'):
            self.config['url'] = value
            self.write_config()
            self.assertEqual(self.submit(all_urls=True)['status'], 'failed')
        self.opener.assert_not_called()

    def test_wrong_site_state_does_not_submit(self):
        self.state_path.parent.mkdir(parents=True)
        self.state_path.write_text(json.dumps({'version': 1, 'siteUrl': 'https://other.example', 'inventory': {}}))
        self.assertEqual(self.submit()['status'], 'failed')
        self.opener.assert_not_called()

    def test_post_rejects_excessive_batch_before_network(self):
        with self.assertRaises(indexnow.IndexNowError):
            indexnow._post_urls(BASE, KEY, BASE + '/' + KEY + '.txt',
                                [BASE + '/'] * 10_001, self.opener)
        self.opener.assert_not_called()


if __name__ == '__main__':
    unittest.main()
