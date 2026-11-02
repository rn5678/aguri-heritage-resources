#!/usr/bin/env python3
"""Publisher regression tests: isolated files and mocked Cloudflare, never a deploy."""
import copy
from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

SPEC = importlib.util.spec_from_file_location('editor_publish_tested', Path(__file__).with_name('editor_publish.py'))
publish = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(publish)
EDITOR_SPEC = importlib.util.spec_from_file_location('content_editor_publish_tested', Path(__file__).with_name('content_editor.py'))
editor = importlib.util.module_from_spec(EDITOR_SPEC)
sys.modules[EDITOR_SPEC.name] = editor
EDITOR_SPEC.loader.exec_module(editor)

SECRET = 'test-only-credential-must-never-be-written'
DEPLOYMENT = '11111111-2222-4333-8444-555555555555'


class TemporaryPublisher(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='aguri-publish-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for folder in ('content/bn','assets','push','scripts','contributions','hosting/cloudflare/site/bn'):
            (self.root/folder).mkdir(parents=True,exist_ok=True)
        for name in ('build.py','scripts/check_site.py','scripts/prepare_cloudflare.py'):
            (self.root/name).write_text('# Test fixture\n')
        (self.root/'content/people.html').write_text('<p>Saved English biography</p>')
        (self.root/'content/bn/people.html').write_text('<p>বাংলা জীবনী</p>')
        (self.root/'contributions/worker.mjs').write_text('export default {fetch(){return new Response("ok")}};')
        self.stage = self.root/'hosting/cloudflare/site'
        (self.stage/'index.html').write_text('<html><body>Saved website</body></html>')
        (self.stage/'bn/index.html').write_text('<html><body>বাংলা</body></html>')
        (self.stage/'sitemap.xml').write_text('<urlset/>')
        (self.stage/'_worker.js').write_bytes((self.root/'contributions/worker.mjs').read_bytes())
        (self.stage/'_routes.json').write_text(json.dumps({'version':1,'include':['/api/*','/','/index.html'],'exclude':[]}))
        retired = [f'/{lang}person-{person}{extension} /{lang}people 301'
                   for lang in ('','bn/') for person in ('haricharan-bandhu','dhanapati-panja')
                   for extension in ('','.html')]
        retired.append('/assets/people/haricharan-bandhu-signed-foreword.jpg /people 301')
        journals = [f'/assets/documents/Ugrakshatriya_Pratinidhi_Vol_{n:02}.pdf https://github.com/rn5678/aguri-heritage-resources/releases/download/journals-v1/Ugrakshatriya_Pratinidhi_Vol_{n:02}.pdf 302' for n in (1,2)]
        (self.stage/'_redirects').write_text('\n'.join(retired+journals)+'\n')
        self.pub = publish.Publisher(self.root,threading.Lock())
        self.project_data = {
            'name':publish.PROJECT,'production_branch':publish.BRANCH,
            'deployment_configs':{'production':{
                'd1_databases':{'CONTRIBUTIONS_DB':{'id':'existing-database'}},
                'env_vars':{'EDITOR_KEY':{'type':'secret_text','value':SECRET}}}},
            'canonical_deployment':{'id':DEPLOYMENT}}
        self.commands = []
        self.remote_calls = []
        self.check_fail = False
        self.deploy_timeout = False
        self.deployment_overrides = {}
        self.deployment_found = True
        self.patches = [
            patch.object(publish.subprocess,'run',side_effect=self.run_command),
            patch.object(publish,'urlopen',side_effect=AssertionError('Tests must never contact the network')),
            patch.object(publish.Publisher,'wrangler',return_value=['test-node','test-wrangler']),
            patch.object(self.pub,'remote',side_effect=self.remote),
            patch.object(publish.time,'sleep',return_value=None),
        ]
        for item in self.patches:
            item.start(); self.addCleanup(item.stop)

    def run_command(self,argv,**kwargs):
        self.commands.append((list(argv),kwargs))
        if argv[:2] == ['test-node','test-wrangler']:
            if argv[2:] == ['auth','token','--json']:
                self.assertEqual(kwargs['env']['WRANGLER_WRITE_LOGS'],'false')
                return subprocess.CompletedProcess(argv,0,json.dumps({'type':'oauth','token':SECRET}),SECRET)
            if argv[2:4] == ['pages','deploy']:
                output = Path(kwargs['env']['WRANGLER_OUTPUT_FILE_PATH'])
                output.write_text(json.dumps({'type':'pages-deploy','pages_project':publish.PROJECT,
                                              'deployment_id':DEPLOYMENT,'url':'https://example.pages.dev'})+'\n')
                if self.deploy_timeout: raise subprocess.TimeoutExpired(argv,600,output=SECRET)
                return subprocess.CompletedProcess(argv,0,SECRET,SECRET)
            raise AssertionError('Unexpected tool command: '+repr(argv))
        script = Path(argv[1]).name
        if script not in ('build.py','check_site.py','prepare_cloudflare.py'):
            raise AssertionError('Unexpected build command: '+repr(argv))
        return subprocess.CompletedProcess(argv,1 if self.check_fail and script=='check_site.py' else 0,SECRET,SECRET)

    def deployment(self):
        pending = self.pub.pending
        value = {'id':DEPLOYMENT,'project_name':publish.PROJECT,'environment':'production',
                 'deployment_trigger':{'metadata':{'branch':publish.BRANCH,'commit_hash':pending['commit']}},
                 'latest_stage':{'name':'deploy','status':'success'}}
        value.update(copy.deepcopy(self.deployment_overrides))
        return value

    def remote(self,suffix='',headers=None):
        self.remote_calls.append(suffix)
        if not suffix: return copy.deepcopy(self.project_data)
        if suffix == '/deployments?per_page=25':
            return [self.deployment()] if self.deployment_found else []
        if suffix == '/deployments/'+DEPLOYMENT: return self.deployment()
        raise AssertionError('Unexpected API path: '+suffix)

    def ready(self):
        self.pub.prepare()
        self.assertEqual(self.pub.status()['phase'],'ready',self.pub.status())
        return self.pub.prepared['summary']['id']

    def deploy_commands(self):
        return [item for item in self.commands if item[0][2:4] == ['pages','deploy']]

    def assert_no_secrets(self):
        self.assertNotIn(SECRET,json.dumps(self.pub.status()))
        for path in self.root.rglob('*'):
            if path.is_file(): self.assertNotIn(SECRET.encode(),path.read_bytes(),str(path))

    def test_prepare_checks_and_snapshots_without_deploying(self):
        self.ready()
        self.assertEqual(self.deploy_commands(),[])
        scripts = [Path(argv[1]).name for argv,_ in self.commands if argv[0] != 'test-node']
        self.assertEqual(scripts,['build.py','check_site.py','prepare_cloudflare.py'])
        self.assertEqual(self.pub.prepared['summary']['pages'],2)
        self.assertEqual(self.pub.manifest(self.pub.prepared['job']/'site'),self.pub.manifest(self.stage))
        self.assert_no_secrets()

    def test_failed_check_cannot_be_confirmed_or_uploaded(self):
        self.check_fail = True
        self.pub.prepare()
        self.assertEqual(self.pub.status()['phase'],'error')
        self.assertIsNone(self.pub.prepared)
        with self.assertRaises(publish.PublishError): self.pub.start_publish('anything')
        self.assertEqual(self.deploy_commands(),[])
        self.assert_no_secrets()

    def test_confirmation_requires_current_preparation_identifier(self):
        self.ready()
        for bad_id in (None,'','previous-id',{'id':'invalid'}):
            with self.subTest(bad_id=bad_id), self.assertRaises(publish.PublishError):
                self.pub.start_publish(bad_id)
        self.assertEqual(self.deploy_commands(),[])

    def test_saved_content_changed_after_check_blocks_upload(self):
        self.ready()
        (self.root/'content/people.html').write_text('<p>Later revision</p>')
        self.pub.publish()
        self.assertEqual(self.pub.status()['phase'],'error')
        self.assertIn('Saved content changed',self.pub.status()['message'])
        self.assertEqual(self.deploy_commands(),[])

    def test_external_source_change_during_build_prevents_ready_snapshot(self):
        def concurrent_edit(argv,**options):
            result=self.run_command(argv,**options)
            if len(argv)>1 and Path(argv[1]).name=='build.py':
                (self.root/'content/people.html').write_text('<p>Changed while building</p>')
            return result
        with patch.object(publish.subprocess,'run',side_effect=concurrent_edit):
            self.pub.prepare()
        self.assertEqual(self.pub.status()['phase'],'error')
        self.assertIn('changed while',self.pub.status()['message'])
        self.assertIsNone(self.pub.prepared)
        self.assertEqual(self.deploy_commands(),[])

    def test_build_managed_editorial_history_can_change_during_prepare(self):
        history=self.root/'content/page-history.json'
        history.write_text('{"pages":{}}')
        def update_history(argv,**options):
            result=self.run_command(argv,**options)
            if len(argv)>1 and Path(argv[1]).name=='build.py':
                history.write_text('{"pages":{"en/people":{"updated":"2026-10-11"}}}')
            return result
        with patch.object(publish.subprocess,'run',side_effect=update_history):
            self.ready()
        self.assertEqual(self.pub.prepared['inputs'],self.pub.inputs())
        history.write_text('{"pages":{"external":"later change"}}')
        self.pub.publish()
        self.assertEqual(self.pub.status()['phase'],'error')
        self.assertEqual(self.deploy_commands(),[])

    def test_snapshot_changed_after_check_blocks_upload(self):
        self.ready()
        (self.pub.prepared['job']/'site/index.html').write_text('Unreviewed page')
        self.pub.publish()
        self.assertEqual(self.pub.status()['phase'],'error')
        self.assertEqual(self.deploy_commands(),[])

    def test_remote_configuration_changed_after_check_blocks_upload(self):
        self.ready()
        self.project_data['deployment_configs']['production']['compatibility_date']='2026-10-11'
        self.pub.publish()
        self.assertIn('settings changed after',self.pub.status()['message'])
        self.assertEqual(self.deploy_commands(),[])

    def test_wrong_project_branch_or_missing_database_blocks_prepare(self):
        original = copy.deepcopy(self.project_data)
        variations = [dict(name='another-project'),dict(production_branch='preview'),dict(deployment_configs={})]
        for changes in variations:
            with self.subTest(changes=changes):
                self.project_data = {**copy.deepcopy(original),**changes}
                self.pub.prepare()
                self.assertEqual(self.pub.status()['phase'],'error')
                self.assertIsNone(self.pub.prepared)
        self.assertEqual(self.deploy_commands(),[])

    def test_success_uses_fixed_destination_without_replacing_bindings(self):
        self.ready()
        expected_config = copy.deepcopy(self.project_data)
        self.pub.publish()
        self.assertEqual(self.pub.status()['phase'],'success',self.pub.status())
        self.assertEqual(self.pub.status()['publication']['id'],DEPLOYMENT)
        self.assertIsNone(self.pub.pending)
        [(argv,options)] = self.deploy_commands()
        self.assertEqual(argv[argv.index('--project-name')+1],publish.PROJECT)
        self.assertEqual(argv[argv.index('--branch')+1],'main')
        self.assertEqual(options['env']['CLOUDFLARE_ACCOUNT_ID'],publish.ACCOUNT)
        self.assertEqual(options['env']['WRANGLER_WRITE_LOGS'],'false')
        self.assertEqual(options['cwd'],self.pub.prepared['job'])
        self.assertNotIn('--config',argv)
        self.assertEqual(self.project_data,expected_config)
        self.assertIn('/deployments/'+DEPLOYMENT,self.remote_calls)
        self.assertEqual(json.loads((self.pub.work/'last-publication.json').read_text())['phase'],'success')
        self.assert_no_secrets()

    def test_cli_timeout_is_reconciled_without_duplicate_upload(self):
        self.ready(); self.deploy_timeout=True
        self.pub.publish()
        self.assertEqual(self.pub.status()['phase'],'success')
        self.assertEqual(len(self.deploy_commands()),1)
        self.assert_no_secrets()

    def test_malformed_optional_search_config_does_not_fail_publication(self):
        (self.root/'content/site-config.json').write_text('invalid json')
        self.ready()
        self.pub.publish()
        self.assertEqual(self.pub.status()['phase'],'success')
        self.assertEqual(self.pub.status()['indexnow']['status'],'failed')
        self.assertFalse(self.pub.status()['uncertain'])

    def test_search_notification_uses_confirmed_snapshot(self):
        (self.root/'content/site-config.json').write_text('{"indexnow_key":"public-test-key"}')
        self.ready()
        notification = Mock(return_value={'status':'received','submitted':2})
        with patch.dict(sys.modules, {'scripts.indexnow':Mock(submit_after_deploy=notification)}):
            self.pub.publish()
        notification.assert_called_once_with(self.root, self.pub.prepared['job']/'site')
        self.assertEqual(self.pub.status()['phase'],'success')
        self.assertEqual(self.pub.status()['indexnow']['submitted'],2)

    def test_success_requires_matching_production_identity(self):
        variants = [
            {'environment':'preview'}, {'id':'99999999-2222-4333-8444-555555555555'},
            {'project_name':'another-project'},
            {'deployment_trigger':{'metadata':{'branch':'preview','commit_hash':'wrong'}}},
            {'deployment_trigger':{'metadata':{'branch':'main','commit_hash':'wrong'}}},
        ]
        for changes in variants:
            with self.subTest(changes=changes):
                self.pub.pending=None; self.deployment_overrides=changes
                self.ready(); self.pub.publish()
                self.assertEqual(self.pub.status()['phase'],'error')
                self.assertTrue(self.pub.status()['uncertain'])
                self.assertIsNotNone(self.pub.pending)

    def test_success_requires_canonical_live_deployment(self):
        self.ready()
        self.project_data['canonical_deployment']['id']='another-deployment'
        self.pub.publish()
        self.assertEqual(self.pub.status()['phase'],'error')
        self.assertIn('another deployment is now live',self.pub.status()['message'])

    def test_cloudflare_failure_clears_pending_and_allows_new_check(self):
        self.ready()
        self.deployment_overrides={'latest_stage':{'name':'deploy','status':'failure'}}
        self.pub.publish()
        self.assertIsNone(self.pub.pending)
        self.assertEqual(self.pub.status()['phase'],'error')
        self.ready()

    def test_duplicate_background_preparations_and_publications_are_rejected(self):
        with patch.object(publish.threading,'Thread') as thread:
            self.pub.start_prepare()
            with self.assertRaises(publish.PublishError): self.pub.start_prepare()
            self.assertEqual(thread.call_count,1)
        identifier=self.ready()
        with patch.object(publish.threading,'Thread') as thread:
            self.pub.start_publish(identifier)
            with self.assertRaises(publish.PublishError): self.pub.start_publish(identifier)
            with self.assertRaises(publish.PublishError): self.pub.start_prepare()
            self.assertEqual(thread.call_count,1)

    def test_restart_reconciles_pending_commit_without_build_or_upload(self):
        self.ready()
        job=self.pub.prepared['job']
        pending={'phase':'publishing','commit':'saved-commit','job':job.name,'config':self.pub.prepared['config']}
        self.pub.write_journal(pending)
        restarted=publish.Publisher(self.root,threading.Lock())
        self.assertTrue(restarted.status()['uncertain'])
        self.pub=restarted
        self.commands.clear()
        with patch.object(restarted,'remote',side_effect=self.remote): restarted.prepare()
        self.assertEqual(restarted.status()['phase'],'success',restarted.status())
        self.assertEqual([argv[2:] for argv,_ in self.commands],[['auth','token','--json']])
        self.assert_no_secrets()

    def test_unconfirmed_upload_remains_blocked_without_retrying_deploy(self):
        self.ready()
        self.pub.pending={'phase':'publishing','commit':'unknown-commit','job':self.pub.prepared['job'].name}
        self.deployment_found=False
        for _ in range(2): self.pub.prepare()
        self.assertEqual(self.pub.status()['phase'],'error')
        self.assertTrue(self.pub.status()['uncertain'])
        self.assertEqual(self.deploy_commands(),[])

    def test_broken_journal_blocks_new_uploads(self):
        self.pub.work.mkdir(parents=True)
        (self.pub.work/'last-publication.json').write_text('{broken')
        restarted=publish.Publisher(self.root,threading.Lock())
        restarted.prepare()
        self.assertTrue(restarted.status()['uncertain'])
        self.assertEqual(self.deploy_commands(),[])

    def test_manifest_rejects_private_files_routes_worker_and_missing_redirects(self):
        variants = [
            ('.env','private'), ('local-editor/private.txt','private'),
            ('_routes.json',json.dumps({'version':1,'include':['/*'],'exclude':[]})),
            ('_worker.js','changed worker'), ('_redirects',''),
        ]
        for name,value in variants:
            with self.subTest(name=name):
                path=self.stage/name; before=path.read_bytes() if path.exists() else None
                path.parent.mkdir(parents=True,exist_ok=True);path.write_text(value)
                try:
                    with self.assertRaises(publish.PublishError): self.pub.manifest(self.stage)
                finally:
                    if before is None: path.unlink()
                    else: path.write_bytes(before)

    def test_parent_wrangler_config_blocks_dashboard_binding_override(self):
        (self.root/'wrangler.toml').write_text('name="unexpected"')
        self.pub.prepare()
        self.assertEqual(self.pub.status()['phase'],'error')
        self.assertIn('configuration could replace',self.pub.status()['message'])
        self.assertEqual(self.deploy_commands(),[])

    def test_auth_failures_never_expose_token_or_subprocess_output(self):
        with patch.object(publish.subprocess,'run',return_value=subprocess.CompletedProcess([],1,SECRET,SECRET)):
            self.pub.prepare()
        self.assertEqual(self.pub.status()['phase'],'error')
        self.assert_no_secrets()

    def test_api_request_is_fixed_and_tokens_stay_in_headers(self):
        response=Mock()
        response.read.return_value=json.dumps({'success':True,'result':{'name':publish.PROJECT}}).encode()
        response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
        with patch.object(publish,'urlopen',return_value=response) as network:
            result=publish.Publisher.remote(self.pub,headers={'Authorization':'Bearer '+SECRET})
        request=network.call_args.args[0]
        self.assertEqual(request.full_url,publish.API)
        self.assertEqual(request.get_header('Authorization'),'Bearer '+SECRET)
        self.assertEqual(result['name'],publish.PROJECT)
        self.assert_no_secrets()

    def test_environment_ignores_inherited_output_and_debug_destinations(self):
        with patch.dict(publish.os.environ,{'WRANGLER_OUTPUT_FILE_PATH':'/bad','WRANGLER_OUTPUT_FILE_DIRECTORY':'/bad','WRANGLER_LOG':'debug'}):
            env=self.pub.environment()
        for key in ('WRANGLER_OUTPUT_FILE_PATH','WRANGLER_OUTPUT_FILE_DIRECTORY','WRANGLER_LOG'):
            self.assertNotIn(key,env)
        self.assertEqual(env['WRANGLER_WRITE_LOGS'],'false')


class EditorConcurrency(unittest.TestCase):
    def test_parallel_status_requests_share_one_publisher(self):
        with tempfile.TemporaryDirectory(prefix='aguri-singleton-test-') as folder:
            with patch.object(editor,'ROOT',Path(folder)), patch.object(editor,'PUBLISHER',None):
                with ThreadPoolExecutor(max_workers=8) as pool:
                    publishers=list(pool.map(lambda _:editor.publisher(),range(24)))
                self.assertEqual(len({id(item) for item in publishers}),1)

    def test_save_rechecks_publication_after_acquiring_edit_lock(self):
        publisher=Mock()
        publisher.busy.side_effect=[False,True]
        with patch.object(editor,'PUBLISHER',publisher), patch.object(editor,'authored') as authored:
            with self.assertRaisesRegex(editor.EditError,'publishing checks'):
                editor.save({})
            authored.assert_not_called()


if __name__ == '__main__':
    unittest.main()
