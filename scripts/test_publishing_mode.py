from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from editor_publish import PublishError, require_direct_publishing


class PublishingModeTests(unittest.TestCase):
    def test_migration_preserves_direct_upload_until_activated(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            require_direct_publishing(root)
            marker = root/'local-editor/github-publishing.json'
            marker.parent.mkdir()
            marker.write_text('{"github_only": false}')
            require_direct_publishing(root)
            marker.write_text('{"github_only": true}')
            with self.assertRaisesRegex(PublishError, 'Publishing now runs through GitHub'):
                require_direct_publishing(root)

    def test_invalid_activation_file_does_not_bypass_github(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            marker = root/'local-editor/github-publishing.json'
            marker.parent.mkdir()
            marker.write_text('invalid')
            with self.assertRaises(PublishError):
                require_direct_publishing(root)
