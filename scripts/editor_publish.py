"""Checked, explicit production publishing for the local Aguri content editor."""
from __future__ import annotations
from datetime import datetime
from zoneinfo import ZoneInfo
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import ssl
import subprocess
import sys
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from asset_paths import is_local_asset

ACCOUNT = '5537dfb96b53a21b9f5c9e278b77679c'
PROJECT = 'aguri-heritage'
BRANCH = 'main'
SITE = 'https://aguri-heritage.in/'
API = f'https://api.cloudflare.com/client/v4/accounts/{ACCOUNT}/pages/projects/{PROJECT}'
NODE = '/opt/homebrew/bin/node'

class PublishError(ValueError):
    pass

def require_direct_publishing(root):
    """Activated only after a verified GitHub production release."""
    marker = Path(root)/'local-editor/github-publishing.json'
    if not marker.exists():
        return
    try:
        enabled = json.loads(marker.read_text()).get('github_only')
    except (ValueError, OSError, AttributeError):
        raise PublishError('The publishing setup needs review. See hosting/PIPELINE.md before publishing.') from None
    if enabled:
        raise PublishError('Publishing now runs through GitHub. Save your changes, then follow hosting/PIPELINE.md to submit and publish them.')

def now():
    return datetime.now(ZoneInfo('Asia/Kolkata')).isoformat(timespec='seconds')

def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()

class Publisher:
    def __init__(self, root, edit_lock):
        self.root = Path(root)
        self.edit_lock = edit_lock
        self.mutex = threading.Lock()
        self.work = self.root/'local-editor/publishing'
        self.state = {'phase':'idle','message':'Save and preview your changes, then publish to your live website.'}
        self.prepared = None
        self.pending = None
        journal = self.work/'last-publication.json'
        if journal.is_file():
            try:
                record = json.loads(journal.read_text())
                if record.get('phase') == 'publishing':
                    self.pending = record
                    self.state = {'phase':'error','message':'A publication was interrupted. Check again to confirm its Cloudflare status before publishing another update.','uncertain':True}
                elif record.get('phase') == 'success':
                    self.state = {'phase':'idle','message':'Your last publication succeeded.','publication':record['publication']}
            except (ValueError,KeyError):
                self.state = {'phase':'error','message':'The publication receipt could not be read. Check the Cloudflare dashboard before publishing.','uncertain':True}
                self.pending = {'invalid':True}

    def status(self):
        with self.mutex:
            return json.loads(json.dumps(self.state))

    def busy(self):
        return self.status()['phase'] in ('preparing','publishing')

    def update(self, **values):
        with self.mutex:
            self.state.update(values)

    def environment(self):
        env = os.environ.copy()
        env.update(CLOUDFLARE_ACCOUNT_ID=ACCOUNT, WRANGLER_WRITE_LOGS='false',
                   WRANGLER_SEND_METRICS='false', CI='true', NO_COLOR='1')
        env['PATH'] = '/opt/homebrew/bin:/usr/bin:/bin:' + env.get('PATH','')
        # Never inherit another tool's output-file destination or debug logging.
        for key in ('WRANGLER_OUTPUT_FILE_PATH','WRANGLER_OUTPUT_FILE_DIRECTORY','WRANGLER_LOG'):
            env.pop(key,None)
        return env

    def wrangler(self):
        path = self.root/'local-editor/cloudflare-tools/node_modules/wrangler/bin/wrangler.js'
        if not Path(NODE).is_file() or not path.is_file():
            raise PublishError('The Cloudflare publishing tool is missing. Reinstall the editor’s publishing support.')
        return [NODE,str(path)]

    def auth(self):
        # Token stdout stays in memory. Wrangler disk logging MUST remain off.
        try:
            result = subprocess.run(self.wrangler()+['auth','token','--json'],cwd=self.root,
                                    env=self.environment(),capture_output=True,text=True,
                                    stdin=subprocess.DEVNULL,timeout=75)
            if result.returncode: raise PublishError('Cloudflare could not connect. Check your internet connection; if the session has expired, reconnect Cloudflare on this Mac.')
            data = json.loads(result.stdout)
            if data.get('type') in ('oauth','api_token') and data.get('token'):
                return {'Authorization':'Bearer '+data['token']}
            if data.get('type') == 'api_key' and data.get('key') and data.get('email'):
                return {'X-Auth-Key':data['key'],'X-Auth-Email':data['email']}
        except (ValueError,subprocess.TimeoutExpired):
            pass
        raise PublishError('Cloudflare could not connect. Check your internet connection or reconnect Cloudflare on this Mac.')

    def remote(self, suffix='', headers=None):
        try:
            request = Request(API+suffix,headers={**(headers or self.auth()),'Accept':'application/json'})
            context = ssl.create_default_context()
            # The standalone macOS Python may lack its own CA bundle. Add the
            # system trust bundle while retaining certificate/hostname checks.
            if sys.platform == 'darwin' and Path('/etc/ssl/cert.pem').is_file():
                context.load_verify_locations(cafile='/etc/ssl/cert.pem')
            with urlopen(request,timeout=40,context=context) as response:
                body = json.load(response)
            if not body.get('success'): raise PublishError('Cloudflare could not confirm this request. Try again after checking your connection.')
            return body['result']
        except HTTPError as exc:
            if exc.code in (401,403): raise PublishError('The saved Cloudflare connection needs to be renewed on this Mac.') from None
            raise PublishError('Cloudflare could not confirm this request. Please try again shortly.') from None
        except (URLError,TimeoutError,ValueError):
            raise PublishError('Cloudflare could not be reached. Your local edits are safe; check your internet connection.') from None

    def project(self, headers):
        project = self.remote(headers=headers)
        if project.get('name') != PROJECT or project.get('production_branch') != BRANCH:
            raise PublishError('Cloudflare’s production destination has changed. Review the publishing setup before continuing.')
        config = project.get('deployment_configs',{}).get('production',{})
        if not config.get('d1_databases',{}).get('CONTRIBUTIONS_DB'):
            raise PublishError('The live site’s contribution database connection is missing. Review Cloudflare settings before publishing.')
        # Hash the configuration; never store or display secret values from the API.
        config_hash = hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest()
        return project,config_hash

    def input_fingerprints(self):
        paths = set(self.root.glob('*.py'))
        for folder in ('content','assets','push'):
            paths.update(p for p in (self.root/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
        paths.update(self.root/p for p in ('contributions/worker.mjs','scripts/check_site.py','scripts/prepare_cloudflare.py'))
        if (self.root/'scripts/indexnow.py').is_file():
            paths.add(self.root/'scripts/indexnow.py')
        result = hashlib.sha256()
        authored = hashlib.sha256()
        for path in sorted(paths):
            if path.is_symlink() and not is_local_asset(self.root,path):
                raise PublishError('A source file points outside the project and its research library. Review the local files before publishing.')
            relative = path.relative_to(self.root).as_posix()
            entry = relative.encode()+b'\0'+digest(path).encode()
            result.update(entry)
            if relative not in ('content/page-history.json','content/weekly-feature-state.json'):
                authored.update(entry)
        return result.hexdigest(),authored.hexdigest()

    def inputs(self):
        return self.input_fingerprints()[0]

    def manifest(self, folder):
        files = {}
        for path in sorted(folder.rglob('*')):
            if path.is_symlink(): raise PublishError('The upload contains a linked file. Prepare the website again.')
            if path.is_file():
                relative = path.relative_to(folder)
                if any(p.startswith('.') or p in {'local-editor','node_modules','backups','research'} for p in relative.parts):
                    raise PublishError('The upload contains a private project file. Prepare the website again.')
                files[relative.as_posix()] = digest(path)
        for name in ('_worker.js','_routes.json','_redirects','index.html','bn/index.html','sitemap.xml'):
            if name not in files: raise PublishError('The prepared website is incomplete. Prepare it again.')
        if files['_worker.js'] != digest(self.root/'contributions/worker.mjs'):
            raise PublishError('The prepared contribution service differs from the checked source.')
        routes = json.loads((folder/'_routes.json').read_text())
        if routes != {'version':1,'include':['/api/*','/','/index.html'],'exclude':[]}:
            raise PublishError('The site’s service routing changed. Review it before publishing.')
        redirects = (folder/'_redirects').read_text()
        for n in (1,2):
            path = f'assets/documents/Ugrakshatriya_Pratinidhi_Vol_{n:02}.pdf'
            if path in files or f'/{path} https://github.com/rn5678/aguri-heritage-resources/releases/download/journals-v1/' not in redirects:
                raise PublishError('The large journal downloads were not prepared correctly.')
        redirect_lines = {line.strip() for line in redirects.splitlines()}
        for language in ('','bn/'):
            for person in ('haricharan-bandhu','dhanapati-panja'):
                for extension in ('','.html'):
                    rule = f'/{language}person-{person}{extension} /{language}people 301'
                    if rule not in redirect_lines:
                        raise PublishError('A retired biography redirect is missing. Prepare the website again.')
        if '/assets/people/haricharan-bandhu-signed-foreword.jpg /people 301' not in redirect_lines:
            raise PublishError('A retired photograph redirect is missing. Prepare the website again.')
        return files

    def check_no_config(self, cwd):
        for parent in [cwd,*cwd.parents]:
            if any((parent/name).exists() for name in ('wrangler.toml','wrangler.json','wrangler.jsonc')):
                raise PublishError('A development configuration could replace the live site’s settings. Review it before publishing.')

    def write_journal(self, record):
        self.work.mkdir(parents=True,exist_ok=True)
        path = self.work/'last-publication.json'
        temp = path.with_suffix('.tmp')
        temp.write_text(json.dumps(record,indent=2)+'\n')
        temp.replace(path)

    def start_prepare(self):
        require_direct_publishing(self.root)
        with self.mutex:
            if self.state['phase'] in ('preparing','publishing'):
                raise PublishError('A publication is already being checked or uploaded. Please wait.')
            self.state = {'phase':'preparing','message':'Checking your saved website…'}
        threading.Thread(target=self.prepare,daemon=True).start()
        return self.status()

    def prepare(self):
        try:
            require_direct_publishing(self.root)
            with self.edit_lock:
                if self.pending:
                    self.reconcile(self.pending)
                    return
                self.prepared = None
                self.work.mkdir(parents=True,exist_ok=True)
                self.update(message='Connecting to your existing Cloudflare site…')
                headers = self.auth()
                _,config_hash = self.project(headers)
                _,authored_before = self.input_fingerprints()
                self.update(message='Rebuilding both language editions…')
                for name,args,label in (
                    ('build.py',[],'Checking pages, photographs and links…'),
                    ('scripts/check_site.py',[],'Preparing the upload and preserving download links…'),
                    ('scripts/prepare_cloudflare.py',['--repository','rn5678/aguri-heritage-resources','--tag','journals-v1','--upload-method','wrangler','--skip-archive'],'Creating your checked publication…')):
                    result = subprocess.run([sys.executable,str(self.root/name),*args],cwd=self.root,
                                            capture_output=True,text=True,timeout=240)
                    if result.returncode:
                        raise PublishError('The website checks did not pass. Your local edits are saved; correct the content before publishing.')
                    self.update(message=label)
                job_id = secrets.token_hex(16)
                job = self.work/job_id
                job.mkdir()
                self.check_no_config(job)
                stage = self.root/'hosting/cloudflare/site'
                expected = self.manifest(stage)
                snapshot = job/'site'
                shutil.copytree(stage,snapshot)
                if self.manifest(snapshot) != expected: raise PublishError('The upload changed while it was being prepared. Please check it again.')
                inputs,authored_after = self.input_fingerprints()
                if authored_before != authored_after:
                    raise PublishError('Source content changed while the website was being checked. Check it again before publishing.')
                prepared = {'id':job_id,'files':len(expected),'pages':sum(p.endswith('.html') for p in expected),
                            'preparedAt':now(),'siteUrl':SITE}
                self.prepared = {'summary':prepared,'inputs':inputs,'manifest':expected,'config':config_hash,'job':job}
                (job/'manifest.json').write_text(json.dumps(expected,indent=2)+'\n')
                # Previous prepared copies are disposable; receipts and source backups remain.
                for previous in self.work.iterdir():
                    if previous != job and previous.is_dir() and re.fullmatch('[a-f0-9]{32}',previous.name):
                        shutil.rmtree(previous/'site',ignore_errors=True)
                self.update(phase='ready',message='Checks passed. Review the destination, then publish your saved website.',preparation=prepared)
        except Exception as exc:
            self.fail(exc)

    def start_publish(self, preparation_id):
        require_direct_publishing(self.root)
        with self.mutex:
            if self.state['phase'] != 'ready' or not self.prepared or preparation_id != self.prepared['summary']['id']:
                raise PublishError('Check the website again before publishing.')
            self.state.update(phase='publishing',message='Confirming the checked version is still current…')
        threading.Thread(target=self.publish,daemon=True).start()
        return self.status()

    def publish(self):
        attempted = False
        try:
            require_direct_publishing(self.root)
            with self.edit_lock:
                ready = self.prepared
                if self.inputs() != ready['inputs']:
                    raise PublishError('Saved content changed after the checks. Check the website again to publish the latest version.')
                job = ready['job']; snapshot = job/'site'
                self.check_no_config(job)
                if self.manifest(snapshot) != ready['manifest']:
                    raise PublishError('The prepared upload changed. Check the website again before publishing.')
                headers = self.auth()
                _,config_hash = self.project(headers)
                if config_hash != ready['config']:
                    raise PublishError('Cloudflare settings changed after the checks. Check the website again before publishing.')
                output = job/'deployment.jsonl'
                env = self.environment(); env['WRANGLER_OUTPUT_FILE_PATH'] = str(output)
                commit = hashlib.sha1(ready['summary']['id'].encode()).hexdigest()
                pending = {'phase':'publishing','commit':commit,'startedAt':now(),'job':job.name,'config':config_hash}
                self.write_journal(pending); self.pending = pending
                self.update(message='Uploading the checked website to Cloudflare…')
                attempted = True
                # The fixed project and branch are never accepted from browser input.
                command = self.wrangler()+['pages','deploy',str(snapshot),'--project-name',PROJECT,
                          '--branch',BRANCH,'--commit-hash',commit,'--commit-message','Published from Aguri Content Editor','--commit-dirty=true']
                try:
                    subprocess.run(command,cwd=job,env=env,capture_output=True,text=True,
                                   stdin=subprocess.DEVNULL,timeout=600)
                except subprocess.TimeoutExpired:
                    pass  # An interrupted upload may already have created a deployment.
                if output.exists():
                    for line in output.read_text().splitlines():
                        entry = json.loads(line)
                        if entry.get('type') == 'pages-deploy' and entry.get('pages_project') == PROJECT:
                            pending['deploymentId'] = entry.get('deployment_id')
                    self.write_journal(pending)
                self.update(message='Confirming Cloudflare has published the update…')
                self.reconcile(pending,headers)
        except Exception as exc:
            self.fail(exc,uncertain=attempted)

    def reconcile(self, pending, headers=None):
        if pending.get('invalid'):
            raise PublishError('Check the last deployment in Cloudflare before repairing the publication receipt.')
        headers = headers or self.auth()
        deployment_id = pending.get('deploymentId')
        if not deployment_id:
            recent = self.remote('/deployments?per_page=25',headers)
            match = next((item for item in recent if item.get('deployment_trigger',{}).get('metadata',{}).get('commit_hash') == pending['commit']),None)
            if match: deployment_id = match['id']
        if not deployment_id:
            raise PublishError('Cloudflare has not yet confirmed this upload. Check again to look for its result; the editor will not upload a duplicate.')
        if not re.fullmatch(r'[a-f0-9-]{36}',deployment_id): raise PublishError('Cloudflare returned an unexpected deployment reference.')
        pending['deploymentId'] = deployment_id; self.write_journal(pending)
        for attempt in range(20):
            deployment = self.remote('/deployments/'+deployment_id,headers)
            stage = deployment.get('latest_stage',{})
            metadata = deployment.get('deployment_trigger',{}).get('metadata',{})
            if (deployment.get('id') != deployment_id or deployment.get('project_name') != PROJECT
                    or metadata.get('branch') != BRANCH or metadata.get('commit_hash') != pending['commit']):
                raise PublishError('Cloudflare returned a different publication. Review the dashboard before publishing again.')
            if deployment.get('environment') != 'production':
                raise PublishError('Cloudflare did not report a production deployment. Review the dashboard before publishing again.')
            if stage.get('status') in ('failure','canceled'):
                self.pending = None
                self.write_journal({'phase':'error','deploymentId':deployment_id,'completedAt':now()})
                raise PublishError('Cloudflare could not publish this update. Your local changes are safe. Check the site again before retrying.')
            if stage.get('name') == 'deploy' and stage.get('status') == 'success':
                project,config_hash = self.project(headers)
                if pending.get('config') and pending['config'] != config_hash:
                    raise PublishError('Cloudflare settings changed during publication. Review the dashboard before publishing again.')
                if project.get('canonical_deployment',{}).get('id') != deployment_id:
                    raise PublishError('This upload finished, but another deployment is now live. Review Cloudflare before publishing again.')
                publication = {'id':deployment_id,'url':SITE,'completedAt':now()}
                receipt = {'phase':'success','publication':publication,'commit':pending['commit']}
                self.write_journal(receipt)
                (self.work/pending['job']/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
                self.pending = None
                # Search-engine notification follows confirmed production deployment.
                # A notification failure must never invalidate a successful upload.
                self.notify_indexnow(pending['job'])
                self.update(phase='success',message='Published successfully. Your revised website is live.',publication=publication,uncertain=False)
                return
            time.sleep(3)
        raise PublishError('Cloudflare is still processing this upload. Check again to confirm when it is live.')

    def notify_indexnow(self, job_id):
        try:
            config = self.root/'content/site-config.json'
            if not config.is_file() or not json.loads(config.read_text()).get('indexnow_key'):
                return
            from scripts.indexnow import submit_after_deploy
            job = self.work/job_id
            result = submit_after_deploy(self.root, job/'site')
            (job/'indexnow.json').write_text(json.dumps(result,indent=2)+'\n')
        except Exception:
            result = {'status':'failed','message':'The website is live; its search notification needs a retry.'}
        self.update(indexnow=result)

    def fail(self, exc, uncertain=False):
        message = str(exc) if isinstance(exc,PublishError) else 'Publishing could not be completed. Your saved local edits are safe. Please check the website again.'
        self.update(phase='error',message=message,error=message,uncertain=bool(uncertain or self.pending))
