"""Production deployment checks with mocked Cloudflare and Wrangler only."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location('deploy_from_github', Path(__file__).with_name('deploy_from_github.py'))
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)
SHA = 'a' * 40
IDENTIFIER = '11111111-2222-3333-4444-555555555555'
OTHER = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'


def deployment_record():
    return {'id': IDENTIFIER, 'project_name': deploy.PROJECT, 'environment': 'production',
            'latest_stage': {'name': 'deploy', 'status': 'success'},
            'deployment_trigger': {'metadata': {'branch': 'main', 'commit_hash': SHA}}}


def project_record(canonical=None):
    return {'name': deploy.PROJECT, 'production_branch': 'main',
            'deployment_configs': {'production': {
                'd1_databases': {'CONTRIBUTIONS_DB': {'id': 'database-id'}},
                'env_vars': {'EDITOR_KEY': {'type': 'secret_text', 'value': 'hidden-value'}},
            }}, 'canonical_deployment': canonical or {}}


class DeployFromGitHubTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        wrangler = self.root / 'local-editor/cloudflare-tools/node_modules/wrangler/bin/wrangler.js'
        wrangler.parent.mkdir(parents=True)
        wrangler.write_text('// fixture')
        self.environment = {
            'GITHUB_REPOSITORY': deploy.REPOSITORY, 'GITHUB_REF': 'refs/heads/main',
            'GITHUB_SHA': SHA, 'CLOUDFLARE_ACCOUNT_ID': deploy.ACCOUNT,
            'CLOUDFLARE_API_TOKEN': 'test-token-never-log', 'PATH': '/usr/bin',
        }
        self.publisher = deploy.Deployment(self.root, self.environment)
        self.records = [project_record(), [], deployment_record(), project_record(deployment_record())]
        self.publisher.remote = Mock(side_effect=lambda *args: self.records.pop(0))
        self.validate = patch.object(self.publisher, 'validate_package', return_value='package-sha')
        self.validate.start(); self.addCleanup(self.validate.stop)
        self.which = patch.object(deploy.shutil, 'which', return_value='/usr/bin/node')
        self.which.start(); self.addCleanup(self.which.stop)
        self.commands = []
        self.runner = patch.object(deploy.subprocess, 'run', side_effect=self.upload)
        self.runner.start(); self.addCleanup(self.runner.stop)

    def upload(self, command, **kwargs):
        self.commands.append((command, kwargs))
        output = Path(kwargs['env']['WRANGLER_OUTPUT_FILE_PATH'])
        output.write_text(json.dumps({'type': 'pages-deploy', 'pages_project': deploy.PROJECT,
                                      'deployment_id': IDENTIFIER}) + '\n')
        return subprocess.CompletedProcess(command, 0, 'private output', '')

    def test_invalid_context_or_secret_stops_before_remote_access(self):
        for key, value in [('GITHUB_REF', 'refs/heads/feature/test'), ('GITHUB_SHA', 'bad'),
                           ('GITHUB_REPOSITORY', 'other/repo'), ('CLOUDFLARE_ACCOUNT_ID', 'other'),
                           ('CLOUDFLARE_API_TOKEN', ''), ('CLOUDFLARE_API_TOKEN', 'token with spaces')]:
            with self.subTest(key=key), self.assertRaises(deploy.DeployError):
                deploy.Deployment(self.root, {**self.environment, key: value})
        self.assertEqual(self.commands, [])

    def test_success_uses_exact_commit_private_logs_and_safe_receipt(self):
        result = self.publisher.run()
        command, options = self.commands[0]
        self.assertIn('--commit-dirty=false', command)
        self.assertEqual(command[command.index('--commit-hash') + 1], SHA)
        self.assertEqual(command[command.index('--branch') + 1], 'main')
        self.assertNotIn('test-token-never-log', ' '.join(command))
        self.assertEqual(options['env']['WRANGLER_WRITE_LOGS'], 'false')
        self.assertTrue(options['capture_output'])
        self.assertFalse(Path(options['cwd']).is_relative_to(self.root))
        self.assertFalse(Path(options['cwd']).exists())
        self.assertEqual(result['deployment_id'], IDENTIFIER)
        text = self.publisher.receipt_path.read_text()
        self.assertNotIn('test-token', text)
        self.assertNotIn('hidden-value', text)
        self.assertEqual(json.loads(text)['status'], 'success')

    def test_missing_database_stops_before_upload(self):
        self.records[0]['deployment_configs']['production']['d1_databases'] = {}
        with self.assertRaisesRegex(deploy.DeployError, 'database binding'):
            self.publisher.run()
        self.assertEqual(self.commands, [])

    def test_changed_configuration_is_not_success(self):
        self.records[-1]['deployment_configs']['production']['env_vars']['NEW'] = {'value': 'new'}
        with self.assertRaisesRegex(deploy.DeployError, 'settings changed'):
            self.publisher.run()
        self.assertEqual(json.loads(self.publisher.receipt_path.read_text())['status'], 'pending')

    def test_wrong_commit_is_not_success(self):
        self.records[2]['deployment_trigger']['metadata']['commit_hash'] = 'b' * 40
        with self.assertRaisesRegex(deploy.DeployError, 'does not match'):
            self.publisher.run()

    def test_preview_deployment_is_not_success(self):
        self.records[2]['environment'] = 'preview'
        with self.assertRaisesRegex(deploy.DeployError, 'does not match'):
            self.publisher.run()

    def test_another_canonical_deployment_is_not_success(self):
        self.records[-1]['canonical_deployment']['id'] = OTHER
        with self.assertRaisesRegex(deploy.DeployError, 'different live production'):
            self.publisher.run()

    def test_failed_deployment_is_not_success(self):
        self.records[2]['latest_stage']['status'] = 'failure'
        with self.assertRaisesRegex(deploy.DeployError, 'failed or was canceled'):
            self.publisher.run()

    def test_already_live_commit_is_verified_without_upload(self):
        self.records = [project_record(deployment_record()), deployment_record(), project_record(deployment_record())]
        result = self.publisher.run()
        self.assertEqual(result['deployment_id'], IDENTIFIER)
        self.assertEqual(self.commands, [])

    def test_lost_tool_output_reconciles_new_exact_commit(self):
        self.runner.stop()
        with patch.object(deploy.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, '', 'secret failure')):
            self.records = [project_record(), [], [deployment_record()], deployment_record(), project_record(deployment_record())]
            self.assertEqual(self.publisher.run()['status'], 'success')

    def test_unconfirmed_upload_exits_without_duplicate(self):
        self.runner.stop()
        with patch.object(deploy.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, '', 'secret failure')) as run:
            with patch.object(deploy, 'POLL_SECONDS', 0), self.assertRaisesRegex(deploy.DeployError, 'not confirmed'):
                self.publisher.run()
            self.assertEqual(run.call_count, 1)

    def test_existing_old_deployment_does_not_confirm_missing_upload(self):
        self.runner.stop()
        self.records = [project_record(), [deployment_record()], [deployment_record()]]
        with patch.object(deploy.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, '', '')):
            with patch.object(deploy.time, 'monotonic', side_effect=[0, 0, 181]), patch.object(deploy.time, 'sleep'):
                with self.assertRaisesRegex(deploy.DeployError, 'not confirmed'):
                    self.publisher.run()

    def test_malformed_machine_output_is_not_logged(self):
        output = self.root / 'bad.jsonl'
        output.write_text('invalid secret-token-data')
        with self.assertRaisesRegex(deploy.DeployError, 'unreadable') as error:
            self.publisher.parse_output(output)
        self.assertNotIn('secret-token-data', str(error.exception))

    def test_package_validates_worker_and_rejects_linked_assets(self):
        self.validate.stop()
        self.runner.stop()
        stage = self.publisher.stage
        stage.mkdir(parents=True)
        for name in ('index.html', 'bn/index.html', '_redirects', 'sitemap.xml'):
            path = stage / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('fixture')
        (self.root / 'contributions').mkdir()
        (self.root / 'contributions/worker.mjs').write_text('worker')
        (stage / '_worker.js').write_text('worker')
        (stage / '_routes.json').write_text(json.dumps({
            'version': 1, 'include': ['/api/*', '/', '/index.html'], 'exclude': []
        }))
        def git_result(command, **kwargs):
            return subprocess.CompletedProcess(command, 0, SHA if command[1] == 'rev-parse' else '', '')
        with patch.object(deploy.subprocess, 'run', side_effect=git_result):
            self.assertEqual(len(self.publisher.validate_package()), 64)
            (stage / 'linked.js').symlink_to(stage / '_worker.js')
            with self.assertRaisesRegex(deploy.DeployError, 'symbolic link'):
                self.publisher.validate_package()
            (stage / 'linked.js').unlink()
            (stage / '_worker.js').write_text('different worker')
            with self.assertRaisesRegex(deploy.DeployError, 'Worker differs'):
                self.publisher.validate_package()

    def test_package_requires_matching_clean_checkout(self):
        self.validate.stop()
        self.runner.stop()
        with patch.object(deploy.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, 'b' * 40, '')):
            with self.assertRaisesRegex(deploy.DeployError, 'does not match'):
                self.publisher.validate_package()
        responses = [subprocess.CompletedProcess([], 0, SHA, ''), subprocess.CompletedProcess([], 0, ' M build.py', '')]
        with patch.object(deploy.subprocess, 'run', side_effect=responses):
            with self.assertRaisesRegex(deploy.DeployError, 'Tracked source changed'):
                self.publisher.validate_package()


if __name__ == '__main__':
    unittest.main()
