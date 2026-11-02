"""Check the real Git index boundary without reading any account credentials."""
import hashlib
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest

import check_public_source as check


class PublicSourceInventory(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        subprocess.run(['git', 'init', '--quiet', str(self.root)], check=True)
        self.files = {
            'build.py': b'# fixture\n',
            'content/page-history.json': b'{"pages": {}}\n',
            'contributions/worker.mjs': b'export default {};\n',
            'assets/translations/example-english.txt': b'Public generated translation\n',
        }
        for name, data in self.files.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        self.write_manifest()
        self.stage()

    def write_manifest(self):
        files = {name: {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
                 for name, data in self.files.items()}
        (self.root / check.MANIFEST).write_text(json.dumps({'format': 'aguri-source-export-v1', 'files': files}))

    def stage(self):
        subprocess.run(['git', '-C', str(self.root), 'add', '--all'], check=True)

    def add(self, name, data=b'private fixture'):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        self.stage()
        return path

    def test_complete_export_passes_without_requiring_generated_asset_hashes(self):
        self.assertEqual(check.check_source(self.root), len(self.files) + 1)
        (self.root / 'assets/translations/example-english.txt').write_text('Regenerated public translation')
        self.assertEqual(check.check_source(self.root), len(self.files) + 1)

    def test_untracked_local_files_are_outside_the_published_inventory(self):
        (self.root / '.env').write_text('local fixture')
        self.assertEqual(check.check_source(self.root), len(self.files) + 1)

    def test_tracked_private_path_or_journal_is_rejected(self):
        for name in ('contributions/.env', 'assets/private.db', 'research/draft.md',
                     'local-editor/backups/page.html', next(iter(check.JOURNALS))):
            with self.subTest(name=name):
                path = self.add(name)
                with self.assertRaises(check.SourceCheckError):
                    check.check_source(self.root)
                path.unlink()
                self.stage()

    def test_tracked_library_symlink_is_rejected(self):
        path = self.root / 'assets/linked.txt'
        path.symlink_to(self.root / 'build.py')
        self.stage()
        with self.assertRaisesRegex(check.SourceCheckError, 'Tracked links'):
            check.check_source(self.root)

    def test_missing_tracked_source_is_rejected_but_new_git_source_is_allowed(self):
        path = self.root / 'assets/translations/example-english.txt'
        path.unlink()
        with self.assertRaisesRegex(check.SourceCheckError, 'missing'):
            check.check_source(self.root)
        path.write_bytes(self.files['assets/translations/example-english.txt'])
        self.add('assets/new.txt')
        self.assertEqual(check.check_source(self.root), len(self.files) + 2)

    def test_git_source_can_remove_files_without_rewriting_or_retaining_export_manifest(self):
        (self.root / 'assets/translations/example-english.txt').unlink()
        self.stage()
        self.assertEqual(check.check_source(self.root), len(self.files))
        (self.root / check.MANIFEST).unlink()
        self.stage()
        self.assertEqual(check.check_source(self.root), len(self.files) - 1)

    def test_recognizable_credential_is_rejected_without_echoing_it(self):
        credential = b'gh' + b'p_' + b'a' * 40
        self.add('assets/public.json', b'{"accident": "' + credential + b'"}')
        with self.assertRaises(check.SourceCheckError) as caught:
            check.check_source(self.root)
        self.assertIn('private credential', str(caught.exception))
        self.assertNotIn(credential.decode(), str(caught.exception))

    def test_cloudflare_credential_is_rejected_without_echoing_it(self):
        credential = b'cf' + b'ut_' + b'a' * 48
        self.add('assets/public.json', b'{"accident": "' + credential + b'"}')
        with self.assertRaises(check.SourceCheckError) as caught:
            check.check_source(self.root)
        self.assertIn('private credential', str(caught.exception))
        self.assertNotIn(credential.decode(), str(caught.exception))

    def test_oversized_tracked_file_is_rejected(self):
        path = self.root / 'assets/translations/example-english.txt'
        with path.open('wb') as stream:
            stream.truncate(check.MAX_FILE_BYTES + 1)
        with self.assertRaisesRegex(check.SourceCheckError, '100 MiB'):
            check.check_source(self.root)

    def test_authoring_folder_requires_export_before_ci(self):
        with TemporaryDirectory() as directory:
            with self.assertRaisesRegex(check.SourceCheckError, 'exported Git checkout'):
                check.check_source(Path(directory))


if __name__ == '__main__':
    unittest.main()
