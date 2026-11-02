"""Keep shared-library assets usable without exposing unrelated local files."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


editor = load('editor_asset_links_tested', 'content_editor.py')
publish = load('publisher_asset_links_tested', 'editor_publish.py')


class SharedAssets(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='aguri-asset-links-')
        self.addCleanup(self.temp.cleanup)
        parent = Path(self.temp.name)
        self.root = parent / 'project'
        self.library = parent / 'Aguri_Research_Library'
        for folder in ('assets', 'content', 'push', 'contributions', 'scripts'):
            (self.root / folder).mkdir(parents=True)
        self.library.mkdir()
        for filename in ('build.py', 'scripts/check_site.py', 'scripts/prepare_cloudflare.py', 'contributions/worker.mjs'):
            (self.root / filename).write_text('fixture')
        self.source = self.library / 'scan.txt'
        self.source.write_text('Shared documentary image')
        self.asset = self.root / 'assets/scan.txt'
        self.asset.symlink_to(self.source)
        self.publisher = publish.Publisher(self.root, threading.Lock())

    def test_publisher_fingerprints_shared_asset_contents(self):
        before = self.publisher.input_fingerprints()
        self.source.write_text('Revised documentary image')
        self.assertNotEqual(self.publisher.input_fingerprints(), before)

    def test_publisher_rejects_other_external_links_and_linked_content(self):
        outside = self.root.parent / 'unrelated.txt'
        outside.write_text('Private unrelated file')
        self.asset.unlink()
        self.asset.symlink_to(outside)
        with self.assertRaises(publish.PublishError):
            self.publisher.input_fingerprints()
        self.asset.unlink()
        (self.root / 'content/linked.html').symlink_to(self.source)
        with self.assertRaises(publish.PublishError):
            self.publisher.input_fingerprints()

    def test_editor_serves_library_asset_but_blocks_traversal(self):
        handler = object.__new__(editor.Handler)
        replies = []
        handler.reply = lambda *args: replies.append(args)
        with patch.object(editor, 'ROOT', self.root):
            handler.file(self.root / 'assets', 'scan.txt')
            self.assertEqual(replies[-1][:2], (200, self.source.read_bytes()))
            handler.file(self.root / 'assets', '../content/hidden.txt')
            self.assertEqual(replies[-1][0], 404)
            handler.file(self.root / 'assets', str(self.source))
            self.assertEqual(replies[-1][0], 404)


if __name__ == '__main__':
    unittest.main()
