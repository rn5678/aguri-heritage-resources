"""Asset routing permits the established archive and rejects unrelated links."""
from pathlib import Path
from tempfile import TemporaryDirectory
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from asset_paths import is_local_asset


class AssetPathsTest(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.base = Path(self.temporary.name).resolve()
        self.root = self.base / 'aguri-heritage'
        self.assets = self.root / 'assets'
        self.assets.mkdir(parents=True)
        self.library = self.base / 'Aguri_Research_Library'
        self.library.mkdir()
        self.internal = self.assets / 'internal.txt'
        self.internal.write_text('project asset')
        self.archived = self.library / 'archived.txt'
        self.archived.write_text('archive asset')
        self.unrelated = self.base / 'private.txt'
        self.unrelated.write_text('unrelated data')

    def tearDown(self):
        self.temporary.cleanup()

    def test_regular_project_asset(self):
        self.assertTrue(is_local_asset(self.root, self.internal))
        self.assertTrue(is_local_asset(self.root, 'assets/internal.txt'))
        self.assertFalse(is_local_asset(self.root, 'assets/missing.txt'))
        self.assertFalse(is_local_asset(self.root, self.assets))

    def test_archive_link_must_start_in_assets(self):
        link = self.assets / 'archived.txt'
        link.symlink_to(self.archived)
        self.assertTrue(is_local_asset(self.root, link))
        self.assertFalse(is_local_asset(self.root, self.archived))
        directory = self.assets / 'library'
        directory.symlink_to(self.library, target_is_directory=True)
        self.assertTrue(is_local_asset(self.root, directory / self.archived.name))

    def test_unrelated_links_and_traversal_are_rejected(self):
        link = self.assets / 'private.txt'
        link.symlink_to(self.unrelated)
        self.assertFalse(is_local_asset(self.root, link))
        self.assertFalse(is_local_asset(self.root, 'assets/../assets/internal.txt'))
        self.assertFalse(is_local_asset(self.root, '../Aguri_Research_Library/archived.txt'))
        disguised = self.base / 'Aguri_Research_Library-unrelated'
        disguised.mkdir()
        (disguised / 'private.txt').write_text('outside the allowed archive')
        (self.assets / 'disguised.txt').symlink_to(disguised / 'private.txt')
        self.assertFalse(is_local_asset(self.root, 'assets/disguised.txt'))

    def test_archive_link_cannot_escape_through_another_link(self):
        (self.library / 'escape.txt').symlink_to(self.unrelated)
        (self.assets / 'escape.txt').symlink_to(self.library / 'escape.txt')
        self.assertFalse(is_local_asset(self.root, 'assets/escape.txt'))


if __name__ == '__main__':
    unittest.main()
