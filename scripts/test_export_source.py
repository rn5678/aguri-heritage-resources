"""Export safety and portable asset checks using isolated Git repositories."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('export_source', Path(__file__).with_name('export_source.py'))
export = importlib.util.module_from_spec(spec)
spec.loader.exec_module(export)


class SourceExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.root, self.dest = base / 'authoring', base / 'checkout'
        self.root.mkdir(); self.dest.mkdir()
        self.write('build.py', 'print("build")\n')
        self.write('content/page-history.json', '{}')
        self.write('contributions/worker.mjs', 'export default {};')
        self.git('init', '-q')
        self.git('config', 'user.name', 'Export Test')
        self.git('config', 'user.email', 'export@example.invalid')
        (self.dest / 'README.md').write_text('Existing resource downloads\n')
        self.commit()

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def git(self, *args):
        subprocess.run(['git', '-C', str(self.dest), *args], check=True,
                       capture_output=True, text=True)

    def commit(self):
        self.git('add', '.')
        self.git('commit', '-qm', 'Fixture snapshot')

    def run_export(self, **kwargs):
        return export.export_source(self.root, self.dest, **kwargs)

    def test_materializes_allowed_library_asset_and_excludes_private_state(self):
        library = self.root.parent / 'Aguri_Research_Library'
        library.mkdir()
        image = library / 'photo.jpg'; image.write_bytes(b'photo')
        (self.root / 'assets').mkdir()
        (self.root / 'assets/photo.jpg').symlink_to(image)
        self.write('contributions/.env', 'SECRET=value')
        self.write('local-editor/backups/private.html', 'private')
        self.write('push/messages/private.json', '{}')
        self.write('assets/documents/Ugrakshatriya_Pratinidhi_Vol_02.pdf', 'large-original')
        summary = self.run_export()
        self.assertEqual(summary['materialized_links'], 1)
        self.assertEqual((self.dest / 'assets/photo.jpg').read_bytes(), b'photo')
        self.assertFalse((self.dest / 'assets/photo.jpg').is_symlink())
        for name in ('contributions/.env', 'local-editor/backups/private.html',
                     'push/messages/private.json', 'assets/documents/Ugrakshatriya_Pratinidhi_Vol_02.pdf'):
            self.assertFalse((self.dest / name).exists())
        self.assertTrue((self.root / 'assets/photo.jpg').is_symlink())
        self.assertEqual((self.dest / 'README.md').read_text(), 'Existing resource downloads\n')

    def test_existing_readme_requires_explicit_adoption(self):
        self.write('README.md', 'Website source\n')
        with self.assertRaisesRegex(export.ExportError, '--adopt-existing README.md'):
            self.run_export()
        self.run_export(adopt_existing=['README.md'])
        self.assertEqual((self.dest / 'README.md').read_text(), 'Website source\n')

    def test_dry_run_writes_nothing(self):
        result = self.run_export(dry_run=True)
        self.assertTrue(result['dry_run'])
        self.assertFalse((self.dest / export.MANIFEST).exists())
        self.assertFalse((self.dest / 'build.py').exists())

    def test_removes_only_previously_exported_paths(self):
        self.write('assets/old.js', 'old')
        self.run_export(); self.commit()
        (self.root / 'assets/old.js').unlink()
        self.run_export()
        self.assertFalse((self.dest / 'assets/old.js').exists())
        self.assertTrue((self.dest / 'README.md').exists())

    def test_refuses_uncommitted_destination(self):
        (self.dest / 'notes.txt').write_text('my work')
        with self.assertRaisesRegex(export.ExportError, 'uncommitted'):
            self.run_export()

    def test_refuses_independent_committed_edit(self):
        self.run_export(); self.commit()
        (self.dest / 'build.py').write_text('different committed edit')
        self.commit()
        with self.assertRaisesRegex(export.ExportError, 'changed independently'):
            self.run_export()

    def test_accepts_remote_edit_after_it_is_reconciled_with_authoring_source(self):
        self.run_export(); self.commit()
        revised = 'print("reconciled change")\n'
        (self.dest / 'build.py').write_text(revised)
        self.commit()
        (self.root / 'build.py').write_text(revised)
        self.run_export()
        manifest = json.loads((self.dest / export.MANIFEST).read_text())
        self.assertEqual(manifest['files']['build.py']['sha256'], export.digest(self.dest / 'build.py'))

    def test_refuses_external_and_broken_asset_links(self):
        (self.root / 'assets').mkdir()
        secret = self.root.parent / 'secret.txt'; secret.write_text('secret')
        link = self.root / 'assets/photo.jpg'; link.symlink_to(secret)
        with self.assertRaisesRegex(export.ExportError, 'escapes'):
            self.run_export()
        link.unlink(); link.symlink_to(self.root / 'missing.jpg')
        with self.assertRaisesRegex(export.ExportError, 'Broken source'):
            self.run_export()

    def test_refuses_non_asset_source_link(self):
        (self.root / 'build.py').unlink()
        (self.root / 'build.py').symlink_to(self.root / 'contributions/worker.mjs')
        with self.assertRaisesRegex(export.ExportError, 'Only published assets'):
            self.run_export()

    def test_refuses_root_asset_directory_link(self):
        library = self.root.parent / 'Aguri_Research_Library'
        library.mkdir()
        (self.root / 'assets').symlink_to(library, target_is_directory=True)
        with self.assertRaisesRegex(export.ExportError, 'directory links'):
            self.run_export()

    def test_refuses_destination_symlink(self):
        (self.dest / 'content').symlink_to(self.root / 'content', target_is_directory=True)
        self.commit()
        with self.assertRaisesRegex(export.ExportError, 'symbolic link'):
            self.run_export()

    def test_refuses_oversized_asset_before_copying(self):
        path = self.write('assets/large.pdf', '')
        with path.open('wb') as stream:
            stream.truncate(export.MAX_ASSET_BYTES + 1)
        with self.assertRaisesRegex(export.ExportError, '25 MiB'):
            self.run_export()
        self.assertFalse((self.dest / 'build.py').exists())

    def test_rejects_manifest_path_traversal(self):
        (self.dest / export.MANIFEST).write_text(json.dumps({
            'format': 'aguri-source-export-v1',
            'files': {'../outside.txt': {'sha256': 'a' * 64}}
        }))
        self.commit()
        with self.assertRaisesRegex(export.ExportError, 'manifest is invalid'):
            self.run_export()


if __name__ == '__main__':
    unittest.main()
