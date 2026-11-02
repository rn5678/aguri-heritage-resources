"""CI must reject date changes caused by rebuilding an uncommitted source state."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import ci_build


class EditorialHistoryGuard(unittest.TestCase):
    def test_unchanged_registry_is_allowed_but_modified_or_removed_registry_fails(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'content').mkdir()
            history = root / 'content/page-history.json'
            history.write_text('{"pages": {}}\n')
            before = ci_build.registry_snapshot(root)
            ci_build.require_unchanged_registries(before, root)
            history.write_text('{"pages": {"new": {}}}\n')
            with self.assertRaisesRegex(ValueError, 'Build locally'):
                ci_build.require_unchanged_registries(before, root)
            history.unlink()
            with self.assertRaises(ValueError):
                ci_build.require_unchanged_registries(before, root)

    def test_weekly_state_creation_also_requires_review(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'content').mkdir()
            before = ci_build.registry_snapshot(root)
            (root / 'content/weekly-feature-state.json').write_text('{}')
            with self.assertRaisesRegex(ValueError, 'weekly-feature-state.json'):
                ci_build.require_unchanged_registries(before, root)


if __name__ == '__main__':
    unittest.main()
