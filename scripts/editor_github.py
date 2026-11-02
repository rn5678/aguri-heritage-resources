"""Prepare a portable review branch and follow its GitHub publication.

Only an explicit confirmation pushes source. GitHub creates/merges the review;
its protected main-branch workflow owns the Cloudflare deployment.
"""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import ssl
import subprocess
import sys
import threading
import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent))
from export_source import ExportError, export_source, source_inventory, digest

REPOSITORY = 'rn5678/aguri-heritage-resources'
REMOTE = 'git@github.com:' + REPOSITORY + '.git'
WEB = 'https://github.com/' + REPOSITORY
API = 'https://api.github.com/repos/' + REPOSITORY
SITE = 'https://aguri-heritage.in/'
SHA = re.compile(r'[a-f0-9]{40}')
BRANCH = re.compile(r'editor/update-[0-9]{8}-[0-9]{6}-[a-f0-9]{8}')


class PublishError(ValueError):
    pass


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def fingerprints(root):
    files = {name: digest(path) for name, path in source_inventory(root).items()}
    return hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()


class Publisher:
    def __init__(self, root, edit_lock):
        self.root = Path(root).resolve()
        self.edit_lock = edit_lock
        self.mutex = threading.RLock()
        self.work = self.root / 'local-editor/publishing/github'
        self.checkout = self.root / 'hosting/source-repository'
        self.receipt = self.work / 'state.json'
        self.state = {'phase': 'idle', 'message': 'Save and preview your changes, then prepare a GitHub review.'}
        self.pending = None
        self.baseline = None
        self.baseline_job = None
        self.refreshing = False
        self.recovering = False
        self.last_recovery = 0
        self.last_refresh = 0
        self.api_requests = []
        self.api_resume_at = 0
        budget_path = self.work / 'api-budget.json'
        if budget_path.is_file():
            try:
                budget = json.loads(budget_path.read_text())
                self.api_requests = [float(value) for value in budget.get('requests', []) if float(value) > time.time() - 3600]
                self.api_resume_at = float(budget.get('resumeAt', 0))
            except (OSError, ValueError, TypeError):
                self.api_resume_at = time.time() + 3600
        if self.receipt.is_file():
            try:
                record = json.loads(self.receipt.read_text())
                if record.get('version') != 1:
                    raise ValueError('version')
                self.state = record['state']
                if not isinstance(self.state, dict) or self.state.get('phase') not in {'idle', 'preparing', 'ready', 'publishing', 'review', 'deploying', 'clean', 'success', 'error'}:
                    raise ValueError('state')
                self.pending = record.get('pending')
                self.baseline = record.get('baseline')
                self.baseline_job = record.get('baselineJob')
                if self.baseline_job and not re.fullmatch(r'[a-f0-9]{32}', self.baseline_job):
                    raise ValueError('baseline job')
                if self.baseline and not SHA.fullmatch(self.baseline):
                    raise ValueError('baseline')
                if self.pending:
                    if not isinstance(self.pending, dict):
                        raise ValueError('pending')
                    if not re.fullmatch(r'[a-f0-9]{32}', self.pending['id']) or not BRANCH.fullmatch(self.pending['branch']):
                        raise ValueError('preparation')
                    for key in ('baseSha', 'headSha', 'mergeSha'):
                        if self.pending.get(key) and not SHA.fullmatch(self.pending[key]):
                            raise ValueError('commit')
                if self.state.get('phase') == 'preparing':
                    self.pending = None
                    self.state = {'phase': 'error', 'message': 'The previous checks were interrupted. Prepare your saved changes again.'}
                elif self.state.get('phase') == 'publishing':
                    self.state.update(phase='error', uncertain=True,
                                      message='The GitHub transfer was interrupted. Check again to recover its status before sending another update.')
            except (OSError, ValueError, KeyError, TypeError):
                self.pending = None
                self.state = {'phase': 'error', 'message': 'The GitHub publishing receipt needs repair before another update can be sent.', 'receiptInvalid': True}

    def save(self):
        with self.mutex:
            self.work.mkdir(parents=True, exist_ok=True)
            record = {'version': 1, 'state': self.state, 'pending': self.pending, 'baseline': self.baseline, 'baselineJob': self.baseline_job}
            temporary = self.receipt.with_suffix('.tmp')
            temporary.write_text(json.dumps(record, indent=2) + '\n')
            temporary.replace(self.receipt)

    def update(self, **values):
        with self.mutex:
            self.state.update(values)
            self.save()

    def status(self, *, refresh=False):
        with self.mutex:
            result = json.loads(json.dumps(self.state))
            eligible = self.state.get('phase') in {'review', 'deploying', 'clean'} or (self.state.get('phase') == 'error' and self.pending and self.pending.get('mergeSha'))
        if eligible:
            self.schedule_refresh(force=refresh)
        elif result.get('phase') == 'error' and result.get('uncertain') and self.pending and self.pending.get('pushAttempted') and not self.pending.get('mergeSha'):
            self.schedule_recovery()
        return result

    def busy(self):
        with self.mutex:
            return self.state.get('phase') in {'preparing', 'publishing'}

    def environment(self):
        environment = os.environ.copy()
        environment.update(GIT_TERMINAL_PROMPT='0', PYTHONUTF8='1')
        environment['PATH'] = '/opt/homebrew/bin:/usr/bin:/bin:' + environment.get('PATH', '')
        return environment

    def command(self, command, cwd, *, timeout=120, acceptable=(0,), text=True):
        try:
            result = subprocess.run(command, cwd=cwd, env=self.environment(), capture_output=True,
                                    text=text, stdin=subprocess.DEVNULL, timeout=timeout)
        except (OSError, subprocess.TimeoutExpired):
            raise PublishError('The local build or GitHub connection did not finish. Your saved source and review snapshot are preserved.') from None
        if result.returncode not in acceptable:
            raise PublishError('The local checks or GitHub connection failed. Your source is preserved; check the connection and prepared review before retrying.')
        return result.stdout.strip() if text else result.stdout

    def git(self, repository, *args, **kwargs):
        return self.command(['git', *args], repository, **kwargs)

    def checked_repository(self):
        if not self.checkout.is_dir():
            raise PublishError('The website source checkout is missing. Restore hosting/source-repository before preparing an update.')
        top = self.git(self.checkout, 'rev-parse', '--show-toplevel')
        if Path(top).resolve() != self.checkout:
            raise PublishError('The website source checkout is not at its expected location.')
        remote = self.git(self.checkout, 'remote', 'get-url', 'origin')
        if remote not in {REMOTE, 'https://github.com/' + REPOSITORY + '.git'}:
            raise PublishError('The source checkout points to a different GitHub repository.')
        if self.git(self.checkout, 'status', '--porcelain', '--untracked-files=all'):
            raise PublishError('The shared source checkout has other unfinished changes. Commit or reconcile them before preparing an editor update.')
        return self.git(self.checkout, 'rev-parse', 'HEAD')

    def repository(self, pending=None):
        pending = pending or self.pending
        if not pending or not re.fullmatch(r'[a-f0-9]{32}', pending.get('id', '')):
            raise PublishError('The prepared source reference is missing.')
        return self.work / pending['id'] / 'repository'

    def github_fields(self, pending):
        title = 'Update Aguri Heritage website'
        body = 'Prepared and checked in the Aguri content editor. Review the changed source and passing website checks before merging into main. Merging publishes through GitHub Actions.'
        return {
            'branch': pending['branch'], 'headSha': pending.get('headSha'),
            'compareUrl': WEB + '/compare/main...' + pending['branch'] + '?' + urlencode({'expand': '1', 'title': title, 'body': body}),
            'actionsUrl': WEB + '/actions', 'mergeSha': pending.get('mergeSha'),
            'checks': {'state': 'pending', 'url': WEB + '/actions'},
        }

    def start_prepare(self):
        with self.mutex:
            if self.state.get('receiptInvalid'):
                raise PublishError(self.state['message'])
            if self.busy():
                return json.loads(json.dumps(self.state))
            if self.pending and self.pending.get('mergeSha') and self.state.get('phase') in {'deploying', 'error'}:
                self.schedule_refresh(force=True)
                return json.loads(json.dumps(self.state))
            if self.pending and self.pending.get('pushAttempted') and not self.pending.get('mergeSha'):
                if self.state.get('phase') == 'review':
                    self.schedule_refresh(force=True)
                    return json.loads(json.dumps(self.state))
                self.state.update(phase='publishing', message='Checking whether GitHub received the prepared source…')
                self.save()
                threading.Thread(target=self.recover_push, daemon=True).start()
                return json.loads(json.dumps(self.state))
            self.state = {'phase': 'preparing', 'message': 'Building your saved website and preparing a GitHub review…'}
            self.pending = None
            self.save()
            threading.Thread(target=self.prepare, daemon=True).start()
            return json.loads(json.dumps(self.state))

    def check_remote_changes(self, repository, baseline, latest):
        if baseline == latest:
            return
        inventory = source_inventory(self.root)
        changed = self.git(repository, 'diff', '--name-only', '-z', baseline, latest).split('\0')
        for name in filter(None, changed):
            if name == '.source-export.json':
                continue
            local = inventory.get(name)
            try:
                remote = self.git(repository, 'show', latest + ':' + name, text=False)
            except PublishError:
                if local is not None:
                    raise PublishError('GitHub removed a source file that still exists locally. Reconcile remote changes before publishing.') from None
                continue
            if local is None or hashlib.sha256(remote).hexdigest() != digest(local):
                raise PublishError('GitHub contains newer source changes that differ from this Mac. Reconcile them before preparing an update.')

    def prepare(self):
        try:
            with self.edit_lock:
                shared_head = self.checked_repository()
                identifier = secrets.token_hex(16)
                branch = 'editor/update-' + datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S') + '-' + identifier[:8]
                pending = {'id': identifier, 'branch': branch, 'preparedAt': now()}
                repository = self.repository(pending)
                repository.parent.mkdir(parents=True)
                self.command(['git', 'clone', '--no-hardlinks', '--no-checkout', str(self.checkout), str(repository)], self.root)
                self.git(repository, 'remote', 'set-url', 'origin', REMOTE)
                ssh = self.git(self.checkout, 'config', '--get', 'core.sshCommand', acceptable=(0, 1))
                if ssh:
                    self.git(repository, 'config', 'core.sshCommand', ssh)
                self.git(repository, 'config', 'core.hooksPath', os.devnull)
                self.git(repository, 'config', 'user.name', 'rn5678')
                self.git(repository, 'config', 'user.email', '217780494+rn5678@users.noreply.github.com')
                if self.baseline and self.baseline_job:
                    previous_repository = self.work / self.baseline_job / 'repository'
                    if not previous_repository.is_dir():
                        raise PublishError('The last reviewed source snapshot is missing. Restore it before reconciling newer GitHub changes.')
                    self.git(repository, 'fetch', '--no-tags', str(previous_repository), self.baseline)
                self.git(repository, 'fetch', '--no-tags', 'origin', 'main')
                latest = self.git(repository, 'rev-parse', 'FETCH_HEAD')
                if not SHA.fullmatch(latest):
                    raise PublishError('GitHub did not return a valid main-branch commit.')
                self.check_remote_changes(repository, self.baseline or shared_head, latest)
                self.git(repository, 'switch', '-c', branch, latest)
                pending['baseSha'] = latest
                # Local building updates editorial history before the reproducible CI build.
                try:
                    self.command([sys.executable, 'build.py'], self.root, timeout=300)
                    self.command([sys.executable, 'scripts/check_site.py'], self.root, timeout=120)
                except PublishError:
                    raise PublishError('The saved website did not pass its local build and page checks. Correct the content, then prepare again.') from None
                source_hash = fingerprints(self.root)
                export_source(self.root, repository)
                self.git(repository, 'add', '--all')
                changed = list(filter(None, self.git(repository, 'diff', '--cached', '--name-only', '-z').split('\0')))
                if not changed:
                    self.baseline = latest
                    self.baseline_job = None
                    self.pending = None
                    self.state = {'phase': 'clean', 'message': 'There are no new source changes to send to GitHub.',
                                  'github': {'headSha': latest, 'actionsUrl': WEB + '/actions', 'checks': {'state': 'pending', 'url': WEB + '/actions'}}}
                    self.save()
                    self.schedule_refresh(force=True)
                    return
                self.update(message='Checking the portable source exactly as GitHub will build it…')
                try:
                    self.command([sys.executable, 'scripts/ci_build.py'], repository, timeout=900)
                except PublishError:
                    raise PublishError('The portable source failed the GitHub build checks. Your saved source and isolated review snapshot are preserved; correct the source and prepare again.') from None
                if fingerprints(self.root) != source_hash:
                    raise PublishError('Saved source changed while checks were running. Prepare a fresh review for the latest changes.')
                if self.git(repository, 'diff', '--name-only') or self.git(repository, 'ls-files', '--others', '--exclude-standard'):
                    raise PublishError('The checked source changed during its build. Review the preserved snapshot before preparing again.')
                pending.update(inputs=source_hash, tree=self.git(repository, 'write-tree'))
                preparation = {'id': identifier, 'branch': branch, 'files': len(source_inventory(self.root)),
                               'pages': len(list((repository / 'site').rglob('*.html'))), 'changedFiles': changed,
                               'preparedAt': pending['preparedAt'], 'siteUrl': SITE}
                self.pending = pending
                self.state = {'phase': 'ready', 'message': 'Checks passed. Send this prepared source to GitHub for review.',
                              'preparation': preparation, 'github': self.github_fields(pending)}
                self.save()
        except Exception as error:
            self.fail(error)

    def start_publish(self, preparation_id):
        with self.mutex:
            if self.pending and self.pending.get('id') == preparation_id and self.state.get('phase') in {'publishing', 'review', 'deploying', 'success'}:
                return json.loads(json.dumps(self.state))
            if self.state.get('phase') != 'ready' or not self.pending or self.pending['id'] != preparation_id:
                raise PublishError('Prepare and check your website again before sending it to GitHub.')
            self.state.update(phase='publishing', message='Sending the checked source to its GitHub review branch…')
            self.save()
            threading.Thread(target=self.publish, daemon=True).start()
            return json.loads(json.dumps(self.state))

    def validate_preparation(self):
        pending = self.pending
        repository = self.repository()
        if self.git(repository, 'branch', '--show-current') != pending['branch']:
            raise PublishError('The prepared checkout changed branches. Prepare a new review.')
        if fingerprints(self.root) != pending['inputs']:
            raise PublishError('Saved content changed after preparation. Prepare again to include the latest changes.')
        if self.git(repository, 'write-tree') != pending['tree'] or self.git(repository, 'diff', '--name-only') or self.git(repository, 'ls-files', '--others', '--exclude-standard'):
            raise PublishError('The prepared source snapshot changed. Prepare a new review.')
        expected = pending.get('headSha') or pending['baseSha']
        if self.git(repository, 'rev-parse', 'HEAD') != expected:
            raise PublishError('The prepared Git commit changed. Prepare a new review.')
        return repository

    def remote_branch(self, repository):
        output = self.git(repository, 'ls-remote', '--heads', 'origin', 'refs/heads/' + self.pending['branch'])
        if not output:
            return None
        lines = output.splitlines()
        if len(lines) != 1:
            raise PublishError('GitHub returned an unexpected review branch.')
        value, ref = lines[0].split()
        if ref != 'refs/heads/' + self.pending['branch'] or not SHA.fullmatch(value):
            raise PublishError('GitHub returned an invalid review branch reference.')
        return value

    def publish(self):
        try:
            with self.edit_lock:
                repository = self.validate_preparation()
                pending = self.pending
                if not pending.get('headSha'):
                    self.git(repository, 'commit', '-m', 'Update Aguri Heritage from the content editor')
                    pending['headSha'] = self.git(repository, 'rev-parse', 'HEAD')
                    if self.git(repository, 'rev-parse', 'HEAD^{tree}') != pending['tree']:
                        raise PublishError('The committed source differs from the checked review snapshot.')
                    self.save()
                remote = self.remote_branch(repository)
                if remote and remote != pending['headSha']:
                    raise PublishError('The GitHub review branch contains a different commit. It was not overwritten.')
                if not remote:
                    pending['pushAttempted'] = True
                    self.save()  # Durable before the external operation, including interruption.
                    try:
                        self.git(repository, 'push', 'origin', pending['headSha'] + ':refs/heads/' + pending['branch'], timeout=300)
                    except PublishError:
                        pass  # A lost response may still mean GitHub received the commit.
                    remote = self.remote_branch(repository)
                if remote != pending['headSha']:
                    raise PublishError('GitHub has not confirmed the source transfer. Check again before sending another update.')
                self.sent()
        except Exception as error:
            self.fail(error, uncertain=bool(self.pending and self.pending.get('pushAttempted')))

    def sent(self):
        self.pending['pushAttempted'] = True
        self.pending['pushed'] = True
        self.state = {'phase': 'review', 'message': 'Source is on GitHub. Create its review, wait for passing checks, then merge to publish.',
                      'github': self.github_fields(self.pending)}
        self.save()
        self.schedule_refresh(force=True)

    def schedule_recovery(self):
        with self.mutex:
            if self.recovering or time.monotonic() - self.last_recovery < 15:
                return
            self.recovering = True
            self.last_recovery = time.monotonic()
            threading.Thread(target=self.background_recovery, daemon=True).start()

    def background_recovery(self):
        try:
            self.recover_push()  # Read-only remote inspection; never commits or pushes.
        finally:
            with self.mutex:
                self.recovering = False

    def recover_push(self):
        try:
            with self.edit_lock:
                if not self.pending or not self.pending.get('headSha'):
                    raise PublishError('The interrupted source transfer has no commit receipt. Review its saved snapshot before continuing.')
                remote = self.remote_branch(self.repository())
                if remote == self.pending['headSha']:
                    self.sent()
                elif remote:
                    raise PublishError('GitHub contains a different review commit. No branch was overwritten.')
                else:
                    self.pending['pushAttempted'] = False
                    self.state.update(phase='ready', uncertain=False,
                                      message='GitHub has not received this prepared source. Review it, then send it again.')
                    self.save()
        except Exception as error:
            self.fail(error, uncertain=True)

    def save_api_budget(self):
        self.work.mkdir(parents=True, exist_ok=True)
        temporary = self.work / 'api-budget.tmp'
        temporary.write_text(json.dumps({'requests': self.api_requests, 'resumeAt': self.api_resume_at}) + '\n')
        temporary.replace(self.work / 'api-budget.json')

    def public_api(self, path):
        with self.mutex:
            timestamp = time.time()
            self.api_requests = [value for value in self.api_requests if value > timestamp - 3600]
            if len(self.api_requests) >= 45:
                self.api_resume_at = max(self.api_resume_at, self.api_requests[0] + 3601)
            if timestamp < self.api_resume_at:
                self.state['nextRefreshAt'] = datetime.fromtimestamp(self.api_resume_at, timezone.utc).isoformat()
                self.save_api_budget()
                raise PublishError('GitHub status checks are paused to respect its public access limit. The GitHub links remain available.')
            self.api_requests.append(timestamp)
            self.save_api_budget()
        request = Request(API + path, headers={'Accept': 'application/vnd.github+json',
                                              'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'Aguri-Content-Editor'})
        try:
            context = ssl.create_default_context(cafile='/etc/ssl/cert.pem') if Path('/etc/ssl/cert.pem').is_file() else ssl.create_default_context()
            with urlopen(request, timeout=15, context=context) as response:
                result = json.load(response)
                remaining = response.headers.get('X-RateLimit-Remaining')
                if remaining is not None and int(remaining) <= 5:
                    with self.mutex:
                        self.api_resume_at = max(self.api_resume_at, float(response.headers.get('X-RateLimit-Reset', timestamp + 3600)) + 1)
                        self.save_api_budget()
                return result
        except HTTPError as error:
            if error.code in (403, 429):
                with self.mutex:
                    retry = error.headers.get('Retry-After')
                    reset = error.headers.get('X-RateLimit-Reset')
                    try:
                        resume = timestamp + float(retry) if retry else float(reset) + 1 if reset else timestamp + 3600
                    except (ValueError, TypeError):
                        resume = timestamp + 3600
                    self.api_resume_at = max(self.api_resume_at, resume)
                    self.save_api_budget()
            error.close()
            raise PublishError('GitHub status is temporarily unavailable or rate limited. Your source is safe; use the GitHub links while the editor waits.') from None
        except Exception:
            raise PublishError('GitHub status is temporarily unavailable. Your source is safe; check the GitHub links or try again shortly.') from None

    def workflow(self, filename, sha, branch=None):
        query = {'head_sha': sha, 'per_page': '30'}
        if branch:
            query['branch'] = branch
        data = self.public_api('/actions/workflows/' + filename + '/runs?' + urlencode(query))
        runs = [run for run in data.get('workflow_runs', []) if run.get('head_sha') == sha
                and (not branch or run.get('head_branch') == branch)
                and run.get('event') in {'push', 'pull_request', 'workflow_dispatch'}]
        if not runs:
            return {'state': 'pending', 'url': WEB + '/actions'}
        run = max(runs, key=lambda value: (value.get('id', 0), value.get('run_attempt', 0)))
        status = 'pending' if run.get('status') != 'completed' else 'success' if run.get('conclusion') == 'success' else 'failure'
        return {'state': status, 'url': WEB + '/actions/runs/' + str(int(run['id'])),
                'id': run['id'], 'completedAt': run.get('updated_at')}

    def schedule_refresh(self, force=False):
        with self.mutex:
            if self.refreshing or time.time() < self.api_resume_at or (not force and time.monotonic() - self.last_refresh < 300):
                return
            self.refreshing = True
            self.last_refresh = time.monotonic()
            self.state['nextRefreshAt'] = datetime.fromtimestamp(max(time.time() + 300, self.api_resume_at), timezone.utc).isoformat()
            threading.Thread(target=self.refresh, daemon=True).start()

    def refresh(self):
        try:
            with self.mutex:
                pending = json.loads(json.dumps(self.pending))
                phase = self.state.get('phase')
                clean_sha = self.state.get('github', {}).get('headSha') if phase == 'clean' else None
            if clean_sha:
                run = self.workflow('publish.yml', clean_sha, 'main')
                with self.mutex:
                    if self.state.get('phase') != 'clean' or self.state.get('github', {}).get('headSha') != clean_sha:
                        return
                    self.state['github']['checks'] = run
                    if run['state'] == 'success':
                        self.state['message'] = 'There are no new source changes. GitHub confirmed the current main commit was published.'
                        self.state['publication'] = {'url': SITE, 'id': run['id'], 'completedAt': run['completedAt']}
                    elif run['state'] == 'failure':
                        self.state['message'] = 'There are no new source changes. The current main publication needs attention on GitHub.'
                    else:
                        self.state['message'] = 'There are no new source changes. GitHub has not yet confirmed publication of the current main commit.'
                    self.state['lastCheckedAt'] = now()
                    self.save()
                return
            if not pending or not pending.get('pushed'):
                return
            github = self.github_fields(pending)
            pulls = self.public_api('/pulls?' + urlencode({'state': 'all', 'head': 'rn5678:' + pending['branch'], 'base': 'main', 'per_page': '20'}))
            matches = [pr for pr in pulls if pr.get('head', {}).get('ref') == pending['branch'] and pr.get('base', {}).get('ref') == 'main'
                       and pr.get('head', {}).get('repo', {}).get('full_name', REPOSITORY) == REPOSITORY
                       and pr.get('base', {}).get('repo', {}).get('full_name', REPOSITORY) == REPOSITORY]
            pr = max(matches, key=lambda item: item['number']) if matches else None
            next_phase = 'review'
            message = 'Source is on GitHub. Create its review, wait for passing checks, then merge to publish.'
            publication = None
            merge_sha = None
            if pr:
                if pr.get('head', {}).get('sha') != pending['headSha']:
                    raise PublishError('The review branch changed on GitHub. Inspect the new commit before continuing from this editor.')
                github['pullRequestUrl'] = WEB + '/pull/' + str(int(pr['number']))
                if pr.get('state') == 'closed':
                    pr = self.public_api('/pulls/' + str(int(pr['number'])))
                    if (pr.get('head', {}).get('sha') != pending['headSha'] or pr.get('head', {}).get('ref') != pending['branch']
                            or pr.get('base', {}).get('ref') != 'main'
                            or pr.get('head', {}).get('repo', {}).get('full_name', REPOSITORY) != REPOSITORY
                            or pr.get('base', {}).get('repo', {}).get('full_name', REPOSITORY) != REPOSITORY):
                        raise PublishError('The merged review does not match the prepared GitHub source.')
                if pr.get('merged_at'):
                    merge_sha = pr.get('merge_commit_sha', '')
                    if not SHA.fullmatch(merge_sha):
                        raise PublishError('GitHub has not reported a valid merged commit yet.')
                    github['mergeSha'] = merge_sha
                    run = self.workflow('publish.yml', merge_sha, 'main')
                    github['checks'] = run
                    github['actionsUrl'] = run['url']
                    next_phase = 'deploying'
                    message = 'The review is merged. GitHub is checking and publishing that exact commit to Cloudflare.'
                    if run['state'] == 'success':
                        next_phase = 'success'
                        message = 'GitHub confirmed this merged update was published to the live website.'
                        publication = {'url': SITE, 'id': run['id'], 'completedAt': run['completedAt']}
                    elif run['state'] == 'failure':
                        next_phase = 'error'
                        message = 'The review is merged, but its publication failed. Open GitHub Actions to resolve it; the editor has not claimed it is live.'
                elif pr.get('state') == 'closed':
                    next_phase = 'error'
                    message = 'This GitHub review was closed without merging. Prepare again when you want a new review.'
                else:
                    checks = self.workflow('checks.yml', pending['headSha'], pending['branch'])
                    github['checks'] = checks
                    if checks['state'] == 'success':
                        message = 'The review checks passed. Review and merge on GitHub to publish.'
                    elif checks['state'] == 'failure':
                        message = 'The GitHub review checks failed. Inspect the checks; to send corrected local source, close this unmerged review on GitHub, then prepare a new review.'
                    else:
                        message = 'The GitHub review is open. Wait for its checks to pass before merging.'
            with self.mutex:
                if not self.pending or self.pending['id'] != pending['id'] or self.state.get('phase') in {'preparing', 'publishing', 'ready'}:
                    return
                if merge_sha:
                    self.pending['mergeSha'] = merge_sha
                    # This is the source actually present on this Mac. A merge may
                    # include concurrent changes or conflict resolutions absent here.
                    self.baseline = pending['headSha']
                    self.baseline_job = pending['id']
                if pr and pr.get('state') == 'closed' and not pr.get('merged_at'):
                    self.pending = None
                self.state = {'phase': next_phase, 'message': message, 'github': github, 'lastCheckedAt': now(),
                              'nextRefreshAt': datetime.fromtimestamp(max(time.time() + 300, self.api_resume_at), timezone.utc).isoformat()}
                if pr and pr.get('state') == 'closed' and not pr.get('merged_at'):
                    self.state.update(closedWithoutMerge=True, canPrepare=True)
                if publication:
                    self.state['publication'] = publication
                self.save()
        except Exception as error:
            with self.mutex:
                if self.state.get('phase') not in {'preparing', 'publishing', 'ready'}:
                    self.state['statusNotice'] = str(error) if isinstance(error, PublishError) else 'GitHub status could not be checked. Use the GitHub links and try again shortly.'
                    self.save()
        finally:
            with self.mutex:
                self.refreshing = False

    def fail(self, error, uncertain=False):
        message = str(error) if isinstance(error, (PublishError, ExportError)) else 'The source review could not be prepared or sent. Your local source and saved snapshots are preserved.'
        with self.mutex:
            self.state.update(phase='error', message=message, uncertain=uncertain)
            self.save()
