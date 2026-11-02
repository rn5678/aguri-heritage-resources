"""Exercise portable deployment packaging without network or project writes."""
from contextlib import redirect_stdout
import copy
import hashlib
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import prepare_cloudflare as prepare


class PortablePackaging(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'site'
        self.source.mkdir()
        (self.root / 'content').mkdir()
        (self.root / 'contributions').mkdir()
        (self.root / 'contributions/worker.mjs').write_text('export default {};')
        (self.source / 'index.html').write_text(
            '<html><body><a href="/api/documents/Ugrakshatriya_Pratinidhi_Vol_01.pdf">Journal</a></body></html>')
        self.release = 'https://github.com/example/resources/releases/download/journals-v1'
        self.pinned = {
            'version': 1, 'repository': 'example/resources', 'tag': 'journals-v1',
            'assets': [{'path': path, 'bytes': 3, 'sha256': hashlib.sha256(b'pdf').hexdigest(),
                        'download_url': f'{self.release}/{Path(path).name}'}
                       for path in prepare.JOURNALS],
        }
        self.write_metadata()
        patcher = patch.object(prepare, 'ROOT', self.root)
        patcher.start()
        self.addCleanup(patcher.stop)

    def write_metadata(self):
        (self.root / 'content/journal-release.json').write_text(json.dumps(self.pinned))

    def run_prepare(self, *flags):
        with redirect_stdout(io.StringIO()):
            prepare.main(['--repository', 'example/resources', *flags])
        return json.loads((self.root / 'hosting/cloudflare/preparation.json').read_text())

    def test_remote_package_works_without_journal_downloads_and_preserves_routes(self):
        output = self.root / 'hosting/cloudflare'
        output.mkdir(parents=True)
        (output / 'aguri-heritage-upload.zip').write_bytes(b'stale archive')
        result = self.run_prepare('--remote-journals', '--skip-archive', '--upload-method', 'wrangler')
        stage = output / 'site'
        self.assertEqual((stage / '_worker.js').read_text(), 'export default {};')
        self.assertEqual(json.loads((stage / '_routes.json').read_text()),
                         {'version': 1, 'include': ['/api/*', '/', '/index.html'], 'exclude': []})
        redirects = (stage / '_redirects').read_text()
        for path in prepare.JOURNALS:
            self.assertIn(f'/{path} {self.release}/{Path(path).name} 302\n', redirects)
            self.assertFalse((stage / path).exists())
        self.assertFalse((output / 'aguri-heritage-upload.zip').exists())
        self.assertFalse(result['archive_created'])
        self.assertIsNone(result['archive_sha256'])
        self.assertFalse(result['remote_release_verified'])
        self.assertTrue(all(not entry['local_file_verified'] for entry in result['journal_assets']))

    def test_default_mode_still_requires_originals_and_creates_archive(self):
        with self.assertRaises(FileNotFoundError):
            self.run_prepare()
        for path in prepare.JOURNALS:
            target = self.source / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b'pdf')
        result = self.run_prepare()
        self.assertEqual(result['upload_method'], 'dashboard')
        self.assertTrue(result['archive_created'])
        self.assertGreater(result['archive_bytes'], 0)
        self.assertTrue((self.root / 'hosting/cloudflare/aguri-heritage-upload.zip').is_file())

    def test_remote_mode_rejects_changed_local_original(self):
        target = self.source / prepare.JOURNALS[0]
        target.parent.mkdir(parents=True)
        target.write_bytes(b'bad')
        with self.assertRaisesRegex(ValueError, 'differs from the pinned release'):
            self.run_prepare('--remote-journals')
        target.write_bytes(b'pdf')
        records = prepare.journal_metadata(self.source, 'example/resources', 'journals-v1', True)
        self.assertTrue(records[0]['local_file_verified'])

    def test_remote_metadata_rejects_wrong_release_or_incomplete_assets(self):
        variants = [
            {**self.pinned, 'repository': 'someone/else'},
            {**self.pinned, 'tag': 'other'},
            {**self.pinned, 'assets': self.pinned['assets'][:1]},
            {**self.pinned, 'assets': [self.pinned['assets'][0]] * 2},
        ]
        for candidate in variants:
            with self.subTest(candidate=candidate):
                self.pinned = candidate
                self.write_metadata()
                with self.assertRaises(ValueError):
                    self.run_prepare('--remote-journals')

    def test_remote_metadata_rejects_invalid_digest_size_and_destination(self):
        original = copy.deepcopy(self.pinned)
        for field, value in [('sha256', 'not-a-hash'), ('bytes', -1),
                             ('download_url', 'https://unrelated.example/document.pdf')]:
            with self.subTest(field=field):
                self.pinned = copy.deepcopy(original)
                self.pinned['assets'][0][field] = value
                self.write_metadata()
                with self.assertRaises(ValueError):
                    self.run_prepare('--remote-journals')

    def test_upload_methods_have_separate_file_limits_and_same_size_limit(self):
        path = self.source / 'index.html'
        with self.assertRaisesRegex(ValueError, 'dashboard limits'):
            prepare.validate_file_limits([path] * 1001, 'dashboard')
        prepare.validate_file_limits([path] * 1001, 'wrangler')
        with self.assertRaisesRegex(ValueError, 'wrangler limits'):
            prepare.validate_file_limits([path] * 20001, 'wrangler')
        with path.open('wb') as stream:
            stream.truncate(25 * 1024 * 1024 + 1)
        for method in ('dashboard', 'wrangler'):
            with self.subTest(method=method), self.assertRaises(ValueError):
                prepare.validate_file_limits([path], method)


if __name__ == '__main__':
    unittest.main()
