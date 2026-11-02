"""Editor GitHub flow: isolated local Git fixtures, no network or live uploads."""
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError

spec = importlib.util.spec_from_file_location('aguri_editor_github_test', Path(__file__).with_name('editor_github.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def git(path, *args):
    result = subprocess.run(['git', '-C', str(path), *args], check=True,
                            capture_output=True, text=True)
    return result.stdout.strip()


class EditorGitHubTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        base = Path(self.temporary.name)
        self.root = base / 'authoring'
        self.root.mkdir()
        for name, value in {'build.py': '# fixture\n', 'content/page-history.json': '{}\n',
                            'content/page.html': '<p>Old page</p>\n',
                            'contributions/worker.mjs': 'export default {};\n',
                            '.gitignore': '/site/\n/hosting/cloudflare/\n'}.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(value)
        self.shared = self.root / 'hosting/source-repository'
        self.shared.mkdir(parents=True)
        git(self.shared, 'init', '-q', '-b', 'main')
        git(self.shared, 'config', 'user.name', 'Fixture')
        git(self.shared, 'config', 'user.email', 'fixture@example.invalid')
        git(self.shared, 'commit', '--allow-empty', '-qm', 'Initial fixture')
        module.export_source(self.root, self.shared)
        git(self.shared, 'add', '.')
        git(self.shared, 'commit', '-qm', 'Initial source')
        self.base_sha = git(self.shared, 'rev-parse', 'HEAD')
        self.bare = base / 'remote.git'
        subprocess.run(['git', 'clone', '--bare', str(self.shared), str(self.bare)], check=True, capture_output=True)
        git(self.shared, 'remote', 'add', 'origin', module.REMOTE)
        git(self.shared, 'config', 'core.sshCommand', 'ssh -o BatchMode=yes')
        self.publisher = module.Publisher(self.root, threading.Lock())
        self.publisher.schedule_refresh = Mock()
        actual_command = self.publisher.command
        self.calls = []
        def offline_command(command, cwd, **kwargs):
            command = list(command)
            self.calls.append((command[:], Path(cwd)))
            if command[0] == sys.executable:
                if command[1] == 'scripts/ci_build.py':
                    folder = Path(cwd) / 'site'
                    folder.mkdir(exist_ok=True)
                    (folder / 'index.html').write_text('fixture')
                return ''
            if command[0] == 'git':
                if command[1:4] == ['fetch', '--no-tags', 'origin']:
                    command[3] = str(self.bare)
                elif command[1:3] == ['push', 'origin']:
                    command[2] = str(self.bare)
                elif command[1:4] == ['ls-remote', '--heads', 'origin']:
                    command[3] = str(self.bare)
            return actual_command(command, cwd, **kwargs)
        self.publisher.command = offline_command

    def change(self, value='New page'):
        (self.root / 'content/page.html').write_text('<p>' + value + '</p>\n')

    def prepare(self):
        self.publisher.state = {'phase': 'preparing'}
        self.publisher.prepare()
        return self.publisher.status()

    def sent(self):
        self.change()
        self.assertEqual(self.prepare()['phase'], 'ready')
        self.publisher.publish()
        self.assertEqual(self.publisher.status()['phase'], 'review')

    def pr(self, *, merged=False, sha=None):
        pending = self.publisher.pending
        return {'number': 7, 'state': 'closed' if merged else 'open',
                'head': {'ref': pending['branch'], 'sha': sha or pending['headSha'], 'repo': {'full_name': module.REPOSITORY}},
                'base': {'ref': 'main', 'repo': {'full_name': module.REPOSITORY}},
                'merged_at': '2026-11-02T00:00:00Z' if merged else None,
                'merge_commit_sha': 'b' * 40 if merged else None}

    def test_constructor_does_not_touch_git_or_network(self):
        with patch.object(module.subprocess, 'run') as run, patch.object(module, 'urlopen') as network:
            module.Publisher(self.root, threading.Lock())
        run.assert_not_called(); network.assert_not_called()

    def test_prepare_uses_isolated_branch_and_leaves_shared_checkout_unchanged(self):
        self.change()
        state = self.prepare()
        self.assertEqual(state['phase'], 'ready', state)
        self.assertIn('content/page.html', state['preparation']['changedFiles'])
        self.assertTrue(state['preparation']['branch'].startswith('editor/update-'))
        self.assertEqual(git(self.shared, 'rev-parse', 'HEAD'), self.base_sha)
        self.assertEqual(git(self.shared, 'status', '--porcelain'), '')
        self.assertEqual(git(self.publisher.repository(), 'config', 'core.sshCommand'), 'ssh -o BatchMode=yes')
        self.assertFalse(any(command[1] == 'push' for command, _ in self.calls if command[0] == 'git'))

    def test_no_changes_is_clean_and_keeps_truthful_deployment_pending(self):
        state = self.prepare()
        self.assertEqual(state['phase'], 'clean', state)
        self.assertNotIn('publication', state)
        self.assertEqual(state['github']['headSha'], self.base_sha)

    def test_unknown_shared_checkout_changes_are_not_overwritten(self):
        (self.shared / 'unrelated.txt').write_text('someone else')
        self.change()
        state = self.prepare()
        self.assertEqual(state['phase'], 'error')
        self.assertIn('unfinished changes', state['message'])
        self.assertEqual((self.shared / 'unrelated.txt').read_text(), 'someone else')

    def test_stale_source_is_rejected_and_can_be_prepared_again(self):
        self.change('First')
        self.assertEqual(self.prepare()['phase'], 'ready')
        old_repo = self.publisher.repository()
        self.change('Second')
        self.publisher.publish()
        self.assertEqual(self.publisher.status()['phase'], 'error')
        self.assertIn('changed after preparation', self.publisher.status()['message'])
        self.assertEqual(self.prepare()['phase'], 'ready')
        self.assertNotEqual(self.publisher.repository(), old_repo)
        self.assertTrue(old_repo.exists())

    def test_confirm_sends_only_exact_review_branch_not_main(self):
        self.sent()
        pending = self.publisher.pending
        self.assertEqual(git(self.bare, 'rev-parse', 'main'), self.base_sha)
        self.assertEqual(git(self.bare, 'rev-parse', pending['branch']), pending['headSha'])
        self.assertEqual(git(self.publisher.repository(), 'rev-parse', 'HEAD^{tree}'), pending['tree'])
        pushes = [command for command, _ in self.calls if command[:2] == ['git', 'push']]
        self.assertEqual(len(pushes), 1)
        self.assertNotIn('--force', pushes[0])
        self.assertEqual(self.publisher.start_publish(pending['id'])['phase'], 'review')
        self.assertEqual(len([c for c, _ in self.calls if c[:2] == ['git', 'push']]), 1)

    def test_interrupted_push_recovers_without_another_push(self):
        self.sent()
        self.publisher.state['phase'] = 'publishing'
        self.publisher.save()
        restored = module.Publisher(self.root, threading.Lock())
        restored.command = self.publisher.command
        restored.schedule_refresh = Mock()
        self.assertEqual(restored.state['phase'], 'error')
        restored.recover_push()
        self.assertEqual(restored.state['phase'], 'review')
        self.assertEqual(len([c for c, _ in self.calls if c[:2] == ['git', 'push']]), 1)

    def test_independent_remote_source_edit_blocks_export(self):
        (self.shared / 'content/page.html').write_text('Remote independent change')
        git(self.shared, 'add', '.')
        git(self.shared, 'commit', '-qm', 'Independent change')
        git(self.shared, 'push', str(self.bare), 'HEAD:main')
        # Simulate an authoring baseline older than the newly fetched main.
        self.publisher.baseline = self.base_sha
        self.change('Different local change')
        state = self.prepare()
        self.assertEqual(state['phase'], 'error')
        self.assertIn('newer source changes', state['message'])

    def test_failed_ci_can_retry_without_discarding_other_snapshots(self):
        self.change()
        actual = self.publisher.command
        def fail_ci(command, cwd, **kwargs):
            if command[:2] == [sys.executable, 'scripts/ci_build.py']:
                raise module.PublishError('sanitized failure')
            return actual(command, cwd, **kwargs)
        self.publisher.command = fail_ci
        self.assertEqual(self.prepare()['phase'], 'error')
        self.publisher.command = actual
        self.assertEqual(self.prepare()['phase'], 'ready')
        self.assertEqual(len(list(self.publisher.work.glob('*/repository'))), 2)

    def test_start_methods_do_not_acquire_callers_source_lock(self):
        self.change()
        with patch.object(module.threading, 'Thread') as thread:
            with self.publisher.edit_lock:
                self.assertEqual(self.publisher.start_prepare()['phase'], 'preparing')
            thread.return_value.start.assert_called_once()

    def test_exact_merged_workflow_success_is_required(self):
        self.sent()
        pr = self.pr(merged=True)
        self.publisher.public_api = Mock(side_effect=[
            [pr], pr, {'workflow_runs': [
                {'id': 1, 'head_sha': 'c' * 40, 'head_branch': 'main', 'event': 'push', 'status': 'completed', 'conclusion': 'success'},
                {'id': 2, 'head_sha': 'b' * 40, 'head_branch': 'main', 'event': 'push', 'status': 'in_progress', 'conclusion': None},
            ]}])
        self.publisher.refresh()
        self.assertEqual(self.publisher.state['phase'], 'deploying')
        self.assertNotIn('publication', self.publisher.state)
        self.assertEqual(self.publisher.baseline, self.publisher.pending['headSha'])
        self.assertNotEqual(self.publisher.baseline, 'b' * 40)
        self.publisher.public_api = Mock(side_effect=[[pr], pr, {'workflow_runs': [
            {'id': 2, 'head_sha': 'b' * 40, 'head_branch': 'main', 'event': 'push', 'status': 'completed', 'conclusion': 'success', 'updated_at': '2026-11-02T00:01:00Z'}]}])
        self.publisher.refresh()
        self.assertEqual(self.publisher.state['phase'], 'success')
        self.assertEqual(self.publisher.state['publication']['id'], 2)

    def test_review_checks_do_not_claim_publication(self):
        self.sent()
        pr = self.pr()
        self.publisher.public_api = Mock(side_effect=[[pr], {'workflow_runs': [
            {'id': 3, 'head_sha': self.publisher.pending['headSha'], 'head_branch': self.publisher.pending['branch'],
             'event': 'pull_request', 'status': 'completed', 'conclusion': 'success'}]}])
        self.publisher.refresh()
        self.assertEqual(self.publisher.state['phase'], 'review')
        self.assertEqual(self.publisher.state['github']['checks']['state'], 'success')
        self.assertNotIn('publication', self.publisher.state)

    def test_new_local_edit_after_own_merge_uses_reconciled_source_baseline(self):
        self.sent()
        previous = dict(self.publisher.pending)
        git(self.shared, 'fetch', str(self.bare), previous['branch'])
        git(self.shared, 'merge', '--ff-only', 'FETCH_HEAD')
        git(self.shared, 'push', str(self.bare), 'HEAD:main')
        self.publisher.baseline = previous['headSha']
        self.publisher.baseline_job = previous['id']
        self.publisher.pending['mergeSha'] = previous['headSha']
        self.change('Second local edit')
        self.assertEqual(self.prepare()['phase'], 'ready')

    def test_concurrent_changes_in_merged_main_are_not_silently_overwritten(self):
        self.sent()
        previous = dict(self.publisher.pending)
        git(self.shared, 'fetch', str(self.bare), previous['branch'])
        git(self.shared, 'merge', '--ff-only', 'FETCH_HEAD')
        (self.shared / 'content/new-remote-page.html').write_text('Independent page added during merge')
        git(self.shared, 'add', '.')
        git(self.shared, 'commit', '-qm', 'Concurrent source update')
        git(self.shared, 'push', str(self.bare), 'HEAD:main')
        self.publisher.baseline = previous['headSha']
        self.publisher.baseline_job = previous['id']
        self.publisher.pending['mergeSha'] = git(self.shared, 'rev-parse', 'HEAD')
        self.change('Second local edit')
        state = self.prepare()
        self.assertEqual(state['phase'], 'error')
        self.assertIn('newer source changes', state['message'])

    def test_uncertain_status_only_schedules_read_only_recovery(self):
        self.sent()
        self.publisher.state.update(phase='error', uncertain=True)
        with patch.object(module.threading, 'Thread') as thread:
            self.publisher.status()
            self.assertEqual(thread.call_args.kwargs['target'], self.publisher.background_recovery)
        self.assertEqual(len([c for c, _ in self.calls if c[:2] == ['git', 'push']]), 1)

    def test_closed_unmerged_review_allows_new_preparation(self):
        self.sent()
        pr = self.pr()
        pr['state'] = 'closed'
        self.publisher.public_api = Mock(side_effect=[[pr], pr])
        self.publisher.refresh()
        self.assertIsNone(self.publisher.pending)
        self.assertTrue(self.publisher.state['canPrepare'])
        self.assertTrue(self.publisher.state['closedWithoutMerge'])

    def test_rate_errors_preserve_review_and_links(self):
        self.sent()
        before = self.publisher.state['github']['compareUrl']
        self.publisher.public_api = Mock(side_effect=module.PublishError('Rate limited'))
        self.publisher.refresh()
        self.assertEqual(self.publisher.state['phase'], 'review')
        self.assertEqual(self.publisher.state['github']['compareUrl'], before)
        self.assertIn('Rate limited', self.publisher.state['statusNotice'])

    def test_manual_status_requests_refresh_without_bypassing_request_budget(self):
        self.sent()
        self.publisher.status(refresh=True)
        self.publisher.schedule_refresh.assert_called_with(force=True)
        self.publisher.api_requests = [time.time()] * 45
        with patch.object(module, 'urlopen') as network:
            with self.assertRaisesRegex(module.PublishError, 'public access limit'):
                self.publisher.public_api('/pulls')
            network.assert_not_called()

    def test_public_request_budget_is_persisted_and_honors_retry_after(self):
        self.publisher.api_requests = [time.time()] * 45
        with patch.object(module, 'urlopen') as network:
            with self.assertRaisesRegex(module.PublishError, 'public access limit'):
                self.publisher.public_api('/pulls')
            network.assert_not_called()
        restored = module.Publisher(self.root, threading.Lock())
        self.assertGreater(restored.api_resume_at, time.time())
        self.publisher.api_requests = []
        self.publisher.api_resume_at = 0
        error = HTTPError(module.API, 429, 'limited', {'Retry-After': '600'}, None)
        with patch.object(module, 'urlopen', side_effect=error):
            with self.assertRaises(module.PublishError):
                self.publisher.public_api('/pulls')
        self.assertGreater(self.publisher.api_resume_at, time.time() + 590)

    def test_merged_failure_can_refresh_without_creating_another_review(self):
        self.sent()
        self.publisher.pending['mergeSha'] = 'b' * 40
        self.publisher.state['phase'] = 'error'
        before = self.publisher.pending['id']
        state = self.publisher.start_prepare()
        self.assertEqual(state['phase'], 'error')
        self.assertEqual(self.publisher.pending['id'], before)
        self.publisher.schedule_refresh.assert_called_with(force=True)


if __name__ == '__main__':
    unittest.main()
