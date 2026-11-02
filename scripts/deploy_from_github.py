#!/usr/bin/env python3
"""Deploy a checked main-branch GitHub commit to the existing Pages project.

Dashboard configuration remains authoritative. Secrets stay in process memory;
Wrangler output is captured privately and never forwarded to the Actions log.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import ssl
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
ACCOUNT = '5537dfb96b53a21b9f5c9e278b77679c'
PROJECT = 'aguri-heritage'
REPOSITORY = 'rn5678/aguri-heritage-resources'
BRANCH = 'main'
SITE = 'https://aguri-heritage.in/'
API = f'https://api.cloudflare.com/client/v4/accounts/{ACCOUNT}/pages/projects/{PROJECT}'
DEPLOYMENT_ID = re.compile(r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}')
POLL_SECONDS = 180


class DeployError(ValueError):
    pass


def validate_environment(environment):
    if environment.get('GITHUB_REPOSITORY') != REPOSITORY:
        raise DeployError('Production deployment is restricted to the configured GitHub repository.')
    if environment.get('GITHUB_REF') != 'refs/heads/main':
        raise DeployError('Only the main branch may publish production.')
    sha = environment.get('GITHUB_SHA', '')
    if not re.fullmatch(r'[a-f0-9]{40}', sha):
        raise DeployError('GitHub did not provide a valid commit identifier.')
    if environment.get('CLOUDFLARE_ACCOUNT_ID') != ACCOUNT:
        raise DeployError('The Cloudflare account secret is missing or does not match this website.')
    token = environment.get('CLOUDFLARE_API_TOKEN', '')
    if not token.strip() or token != token.strip() or any(c.isspace() for c in token):
        raise DeployError('The Cloudflare API token secret is missing or invalid.')
    return sha


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


class Deployment:
    def __init__(self, root=ROOT, environment=None):
        self.root = Path(root).resolve()
        self.environment = dict(os.environ if environment is None else environment)
        self.sha = validate_environment(self.environment)
        self.stage = self.root / 'hosting/cloudflare/site'
        self.receipt_path = self.root / 'hosting/cloudflare/github-deployment.json'

    def remote(self, suffix=''):
        request = Request(API + suffix, headers={
            'Authorization': 'Bearer ' + self.environment['CLOUDFLARE_API_TOKEN'],
            'Accept': 'application/json',
        })
        context = ssl.create_default_context()
        if sys.platform == 'darwin' and Path('/etc/ssl/cert.pem').is_file():
            context.load_verify_locations(cafile='/etc/ssl/cert.pem')
        try:
            with urlopen(request, timeout=20, context=context) as response:
                body = json.load(response)
            if not body.get('success') or 'result' not in body:
                raise DeployError('Cloudflare did not confirm the requested deployment state.')
            return body['result']
        except (HTTPError, URLError, TimeoutError, ValueError, OSError):
            # Never print response bodies, headers, token-bearing requests or logs.
            raise DeployError('Cloudflare could not verify the deployment. Check account permissions and the Cloudflare dashboard.') from None

    def project(self):
        project = self.remote()
        if not isinstance(project, dict) or project.get('name') != PROJECT or project.get('production_branch') != BRANCH:
            raise DeployError('The Cloudflare production destination does not match the configured website.')
        config = (project.get('deployment_configs') or {}).get('production') or {}
        database = (config.get('d1_databases') or {}).get('CONTRIBUTIONS_DB')
        if not isinstance(database, dict) or not database.get('id'):
            raise DeployError('The production contribution database binding is missing.')
        fingerprint = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()
        return project, fingerprint

    def validate_package(self):
        result = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=self.root,
                                capture_output=True, text=True, timeout=15)
        if result.returncode or result.stdout.strip() != self.sha:
            raise DeployError('The checked-out source does not match the GitHub commit being published.')
        result = subprocess.run(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=self.root,
                                capture_output=True, text=True, timeout=15)
        if result.returncode or result.stdout.strip():
            raise DeployError('Tracked source changed after checkout; commit the checked source before publishing.')
        files = {}
        if not self.stage.is_dir() or self.stage.is_symlink():
            raise DeployError('The checked website upload folder is missing or linked.')
        for path in self.stage.rglob('*'):
            if path.is_symlink():
                raise DeployError('The upload contains a symbolic link; rebuild the portable website.')
            if path.is_file():
                relative = path.relative_to(self.stage)
                if any(part.startswith('.') or part in {'research', 'node_modules', 'local-editor', 'backups'}
                       for part in relative.parts):
                    raise DeployError('The upload contains a private development file.')
                if path.stat().st_size > 25 * 1024 * 1024:
                    raise DeployError('The upload contains a file larger than the Pages limit.')
                files[relative.as_posix()] = digest(path)
        if not files or len(files) > 20000:
            raise DeployError('The upload does not meet the Pages file-count limit.')
        for name in ('index.html', 'bn/index.html', '_worker.js', '_routes.json', '_redirects', 'sitemap.xml'):
            if name not in files:
                raise DeployError('The checked website upload is incomplete.')
        if files['_worker.js'] != digest(self.root / 'contributions/worker.mjs'):
            raise DeployError('The upload Worker differs from the checked source.')
        if json.loads((self.stage / '_routes.json').read_text()) != {
            'version': 1, 'include': ['/api/*', '/', '/index.html'], 'exclude': []
        }:
            raise DeployError('The website API routes differ from the configured production routes.')
        return hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()

    def write_receipt(self, record):
        self.receipt_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.receipt_path.with_suffix('.tmp')
        temporary.write_text(json.dumps(record, indent=2) + '\n')
        temporary.replace(self.receipt_path)

    def parse_output(self, path):
        if not path.exists():
            return None
        identifiers = set()
        try:
            for line in path.read_text().splitlines():
                entry = json.loads(line)
                if entry.get('type') == 'pages-deploy' and entry.get('pages_project') == PROJECT:
                    identifier = entry.get('deployment_id', '')
                    if not DEPLOYMENT_ID.fullmatch(identifier):
                        raise DeployError('Wrangler returned an invalid deployment reference.')
                    identifiers.add(identifier)
        except (ValueError, TypeError, AttributeError):
            raise DeployError('Wrangler returned unreadable deployment metadata; check Cloudflare before retrying.') from None
        if len(identifiers) > 1:
            raise DeployError('Wrangler reported multiple deployments; check Cloudflare before retrying.')
        return next(iter(identifiers), None)

    def verify(self, identifier, expected_config, package_hash, deadline):
        if not DEPLOYMENT_ID.fullmatch(identifier):
            raise DeployError('Cloudflare returned an invalid deployment reference.')
        while time.monotonic() < deadline:
            deployment = self.remote('/deployments/' + identifier)
            metadata = (deployment.get('deployment_trigger') or {}).get('metadata') or {}
            if (deployment.get('id') != identifier or deployment.get('project_name') != PROJECT
                    or deployment.get('environment') != 'production'
                    or metadata.get('branch') != BRANCH or metadata.get('commit_hash') != self.sha):
                raise DeployError('Cloudflare returned a deployment that does not match this production commit.')
            stage = deployment.get('latest_stage') or {}
            if stage.get('status') in {'failure', 'canceled', 'cancelled'}:
                raise DeployError('Cloudflare reported that this production deployment failed or was canceled.')
            if stage.get('name') == 'deploy' and stage.get('status') == 'success':
                project, config_hash = self.project()
                if config_hash != expected_config:
                    raise DeployError('Production settings changed during deployment; inspect Cloudflare before retrying.')
                if (project.get('canonical_deployment') or {}).get('id') != identifier:
                    raise DeployError('The upload completed, but Cloudflare reports a different live production deployment.')
                receipt = {
                    'status': 'success', 'repository': REPOSITORY, 'commit': self.sha,
                    'deployment_id': identifier, 'url': SITE, 'package_sha256': package_hash,
                    'completed_at': datetime.now(timezone.utc).isoformat(),
                }
                self.write_receipt(receipt)
                return receipt
            time.sleep(3)
        raise DeployError('Cloudflare has not confirmed this deployment within three minutes; check its status before retrying.')

    def run(self):
        package_hash = self.validate_package()
        node = shutil.which('node', path=self.environment.get('PATH'))
        wrangler = self.root / 'local-editor/cloudflare-tools/node_modules/wrangler/bin/wrangler.js'
        if not node or not wrangler.is_file():
            raise DeployError('The pinned Cloudflare publishing tools are not installed.')
        project, config_hash = self.project()
        canonical = project.get('canonical_deployment') or {}
        metadata = (canonical.get('deployment_trigger') or {}).get('metadata') or {}
        # A rerun of an already-live commit verifies it without creating a duplicate.
        if metadata.get('commit_hash') == self.sha and canonical.get('id'):
            return self.verify(canonical['id'], config_hash, package_hash, time.monotonic() + POLL_SECONDS)
        before = self.remote('/deployments?per_page=25')
        if not isinstance(before, list):
            raise DeployError('Cloudflare returned an unreadable deployment inventory.')
        previous_ids = {entry.get('id') for entry in before}
        self.write_receipt({'status': 'pending', 'repository': REPOSITORY, 'commit': self.sha,
                            'package_sha256': package_hash, 'url': SITE})
        with tempfile.TemporaryDirectory(prefix='aguri-github-deploy-') as temporary:
            work = Path(temporary)
            for parent in [work, *work.parents]:
                if any((parent / name).exists() for name in ('wrangler.toml', 'wrangler.json', 'wrangler.jsonc')):
                    raise DeployError('A Wrangler configuration could replace dashboard settings; deployment stopped.')
            output = work / 'deployment.jsonl'
            environment = self.environment.copy()
            for name in ('WRANGLER_OUTPUT_FILE_DIRECTORY', 'WRANGLER_LOG', 'WRANGLER_LOG_PATH',
                         'CLOUDFLARE_API_KEY', 'CLOUDFLARE_EMAIL', 'CF_API_KEY', 'CF_API_EMAIL', 'CF_API_TOKEN'):
                environment.pop(name, None)
            environment.update(WRANGLER_OUTPUT_FILE_PATH=str(output), WRANGLER_WRITE_LOGS='false',
                               WRANGLER_SEND_METRICS='false', CI='true', NO_COLOR='1')
            command = [node, str(wrangler), 'pages', 'deploy', str(self.stage),
                       '--project-name', PROJECT, '--branch', BRANCH,
                       '--commit-hash', self.sha, '--commit-dirty=false']
            try:
                subprocess.run(command, cwd=work, env=environment, capture_output=True,
                               text=True, stdin=subprocess.DEVNULL, timeout=600)
            except subprocess.TimeoutExpired:
                pass  # An interrupted client may already have published the upload.
            identifier = self.parse_output(output)
            deadline = time.monotonic() + POLL_SECONDS
            while not identifier and time.monotonic() < deadline:
                recent = self.remote('/deployments?per_page=25')
                matches = [entry for entry in recent if entry.get('id') not in previous_ids
                           and ((entry.get('deployment_trigger') or {}).get('metadata') or {}).get('commit_hash') == self.sha
                           and entry.get('environment') == 'production']
                if len(matches) > 1:
                    raise DeployError('Multiple uploads match this commit; inspect Cloudflare before retrying.')
                if matches:
                    identifier = matches[0].get('id')
                else:
                    time.sleep(3)
            if not identifier:
                raise DeployError('Cloudflare has not confirmed the upload. Inspect the dashboard before retrying; no duplicate was attempted.')
            self.write_receipt({'status': 'pending', 'repository': REPOSITORY, 'commit': self.sha,
                                'deployment_id': identifier, 'package_sha256': package_hash, 'url': SITE})
            return self.verify(identifier, config_hash, package_hash, deadline)


def main():
    try:
        receipt = Deployment().run()
        print(f"{receipt['url']} deployment {receipt['deployment_id']}")
    except DeployError as error:
        print(f'Deployment stopped: {error}', file=sys.stderr)
        return 1
    except Exception:
        print('Deployment could not be verified. Inspect Cloudflare before retrying; raw tool output was withheld.', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
