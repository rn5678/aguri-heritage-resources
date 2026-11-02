"""CI must reject date changes caused by rebuilding an uncommitted source state."""
from pathlib import Path
import subprocess
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

    def test_generated_source_changes_fail_against_index_without_requiring_a_commit(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(['git', 'init', '--quiet', str(root)], check=True)
            asset = root / 'translation-links.js'
            asset.write_text('window.TRANSLATION_LINKS = [];\n')
            subprocess.run(['git', '-C', str(root), 'add', '--all'], check=True)
            # A newly staged source export has no HEAD commit yet and is valid.
            ci_build.require_unchanged_tracked_source(root)
            (root / 'site').mkdir()
            (root / 'site/index.html').write_text('Untracked generated website')
            ci_build.require_unchanged_tracked_source(root)
            asset.write_text('window.TRANSLATION_LINKS = ["new"];\n')
            with self.assertRaisesRegex(ValueError, 'Build changed tracked source: translation-links.js'):
                ci_build.require_unchanged_tracked_source(root)
            # Reviewing and staging the generated update establishes the next baseline.
            subprocess.run(['git', '-C', str(root), 'add', 'translation-links.js'], check=True)
            ci_build.require_unchanged_tracked_source(root)


if __name__ == '__main__':
    unittest.main()
