"""End-to-end editor translation safeguards, with isolated source files."""
import importlib.util
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import Mock, patch

import test_content_editor as fixture
editor, png = fixture.editor, fixture.png

spec = importlib.util.spec_from_file_location('translation_service', Path(__file__).with_name('editor_translation.py'))
service = importlib.util.module_from_spec(spec)
spec.loader.exec_module(service)


class TranslationFlow(unittest.TestCase):
    request = fixture.TemporarySite.request
    story_edit = fixture.TemporarySite.story_edit
    successful_run = staticmethod(fixture.TemporarySite.successful_run)

    def setUp(self):
        fixture.TemporarySite.setUp(self)
        self.sync = service.Translator(self.root, editor.LOCK, editor.authored, editor.clean_block,
                                       lambda: False, start_worker=False)
        self.sync.configure(True)
        self.sync.initialize(editor.pages()['pages'])
        self.patch = patch.object(editor, 'TRANSLATOR', self.sync)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.call = Mock(side_effect=lambda blocks: {'translations': {b['id']: b['english'].replace('Revised life story', 'সংশোধিত জীবনকথা') for b in blocks},
                                                     'usage': {'input_tokens': 100, 'output_tokens': 25, 'cached_input_tokens': 50}})
        self.sync.client.translate = self.call

    def save_story(self):
        with patch.object(editor.subprocess, 'run', side_effect=self.successful_run):
            editor.save(self.story_edit())

    def process(self):
        with patch.object(service.subprocess, 'run', side_effect=self.successful_run):
            return self.sync.run_once()

    def test_only_changed_block_translates_and_second_run_uses_nothing(self):
        self.save_story()
        self.assertEqual(self.sync.status()['pending'], 1)
        self.assertTrue(self.process())
        self.assertIn('সংশোধিত জীবনকথা', (self.root/'content/bn/people.html').read_text())
        self.assertEqual(len(self.call.call_args.args[0]), 1)
        self.assertEqual(self.sync.status()['pending'], 0)
        self.assertFalse(self.process())
        self.call.assert_called_once()
        self.assertEqual(self.sync.status()['usage']['input_tokens'], 100)

    def test_deletion_uses_no_model_and_has_backup(self):
        payload = self.story_edit()
        payload['blocks'] = {key: '' for key in payload['blocks']}
        with patch.object(editor.subprocess, 'run', side_effect=self.successful_run):
            editor.save(payload)
        self.assertTrue(self.process())
        self.call.assert_not_called()
        self.assertNotIn('Original life story', (self.root/'content/bn/people.html').read_text())
        self.assertTrue(list((self.root/'local-editor/backups').glob('*-bengali-*/content/bn/people.html')))

    def test_citation_only_removal_uses_no_model(self):
        payload, doc = self.request()
        block = next(b for b in doc['blocks'] if 'Original life story' in b['html'])
        payload['blocks'][block['id']] = 'Original life story with <em>emphasis</em>.[cite:source-one]'
        with patch.object(editor.subprocess, 'run', side_effect=self.successful_run):
            editor.save(payload)
        self.assertTrue(self.process())
        self.call.assert_not_called()
        self.assertIn('emphasis</em>.[cite:source-one]</p>', (self.root/'content/bn/people.html').read_text())

    def test_bengali_change_during_model_call_never_overwritten(self):
        self.save_story()
        def concurrent(blocks):
            path = self.root/'content/bn/people.html'
            path.write_text(path.read_text().replace('Original life story', 'আমার নিজের লেখা'))
            return {'translations': {b['id']: b['english'] for b in blocks}, 'usage': {'input_tokens': 1}}
        self.call.side_effect = concurrent
        self.assertFalse(self.process())
        self.assertIn('আমার নিজের লেখা', (self.root/'content/bn/people.html').read_text())
        self.sync.retry()
        self.assertEqual(self.sync.status()['phase'], 'review')
        self.sync.accept('person-test-person')
        self.assertEqual(self.sync.status()['reviewCount'], 0)

    def test_build_failure_restores_bengali_then_retry_reuses_output(self):
        self.save_story()
        path = self.root/'content/bn/people.html'
        before = path.read_bytes()
        failure = subprocess.CompletedProcess([], 1, '', 'broken')
        with patch.object(service.subprocess, 'run', return_value=failure):
            self.assertFalse(self.sync.run_once())
        self.assertEqual(path.read_bytes(), before)
        self.assertIn('Revised life story', self.path.read_text())
        self.sync.retry()
        self.assertTrue(self.process())
        self.call.assert_called_once()

    def test_pending_survives_restart_without_backfill(self):
        self.save_story()
        restored = service.Translator(self.root, editor.LOCK, editor.authored, editor.clean_block, lambda: False, start_worker=False)
        restored.initialize(editor.pages()['pages'])
        self.assertEqual(restored.status()['pending'], 1)
        self.assertEqual(sum(len(restored.mapping.pending_jobs(s)) for s in restored.states.values()), 1)

    def test_pause_keeps_pending_and_allows_explicit_manual_publish(self):
        self.save_story()
        with self.assertRaises(ValueError): self.sync.assert_publish_ready()
        self.sync.configure(False)
        self.sync.assert_publish_ready()
        self.assertFalse(self.process())
        self.assertEqual(self.sync.status()['pending'], 1)

    def test_source_photo_updates_both_languages_without_model(self):
        import base64
        payload, doc = self.request()
        payload['images'] = {doc['images'][0]['id']: {'dataUrl': 'data:image/png;base64,' + base64.b64encode(png()).decode()}}
        with patch.object(editor.subprocess, 'run', side_effect=self.successful_run):
            editor.save(payload)
        english = editor.document('person-test-person', 'en')['images'][0]['src']
        bengali = editor.document('person-test-person', 'bn')['images'][0]['src']
        self.assertEqual(english, bengali)
        self.assertIn('/assets/uploads/', english)
        self.assertFalse(self.process())
        self.call.assert_not_called()

    def test_photo_failure_rolls_back_both_languages(self):
        import base64
        payload, doc = self.request()
        payload['images'] = {doc['images'][0]['id']: {'dataUrl': 'data:image/png;base64,' + base64.b64encode(png()).decode()}}
        before = (self.root/'content/bn/people.html').read_bytes()
        with patch.object(editor.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, '', 'failed')):
            with self.assertRaises(ValueError): editor.save(payload)
        self.assertEqual((self.root/'content/bn/people.html').read_bytes(), before)

    def structural_payload(self, lang='en'):
        doc = editor.document('person-test-person', lang)
        block = next(b for b in doc['blocks'] if 'Original life story' in b['html'])
        return {'id':doc['id'], 'lang':lang, 'version':doc['version'], 'blocks':{}, 'images':{}}, block

    def save_payload(self, payload):
        with patch.object(editor.subprocess, 'run', side_effect=self.successful_run):
            return editor.save(payload)

    def test_added_block_creates_paired_placeholder_and_only_new_text_queues(self):
        payload, block = self.structural_payload()
        payload['insertBlocks'] = [{'id':'new-first', 'anchor':block['id'], 'position':'after', 'tag':'p', 'html':'A new paragraph.'}]
        self.save_payload(payload)
        self.assertIn('<p data-editor-block="new-first"></p>', (self.root/'content/bn/people.html').read_text())
        self.assertEqual(self.sync.status()['pending'], 1)
        self.assertEqual(self.sync.status()['reviewCount'], 0)
        self.assertTrue(self.process())
        self.call.assert_called_once()
        self.assertEqual(self.call.call_args.args[0][0]['english'], 'A new paragraph.')
        self.assertEqual(self.sync.status()['pending'], 0)

    def test_complete_deletion_removes_both_blocks_and_keeps_following_pair_ids(self):
        payload, block = self.structural_payload()
        initial = self.sync.states['person-test-person']
        following_id = next(r['id'] for r in initial['records'] if 'A remembered phrase' in r['en']['html'])
        payload['deleteBlocks'] = [block['id']]
        self.save_payload(payload)
        for lang in ('en', 'bn'):
            self.assertNotIn('Original life story', editor.authored('person-test-person',lang)[1])
        self.assertEqual(self.sync.status()['pending'], 0)
        self.assertEqual(self.sync.status()['reviewCount'], 0)
        following = next(r for r in self.sync.states['person-test-person']['records'] if r.get('en') and 'A remembered phrase' in r['en']['html'])
        self.assertEqual(following['id'], following_id)
        self.assertFalse(self.process())
        self.call.assert_not_called()

    def test_replace_deleted_anchor_with_two_blocks_preserves_order_and_pairs(self):
        payload, block = self.structural_payload()
        payload['deleteBlocks'] = [block['id']]
        payload['insertBlocks'] = [
            {'id':'new-one','anchor':block['id'],'position':'before','tag':'p','html':'First addition.'},
            {'id':'new-two','anchor':block['id'],'position':'before','tag':'p','html':'Second addition.'},
            {'id':'new-three','anchor':block['id'],'position':'after','tag':'p','html':'Third addition.'}]
        self.save_payload(payload)
        for lang in ('en','bn'):
            text=editor.authored('person-test-person',lang)[1]
            self.assertLess(text.index('new-one'),text.index('new-two'))
            self.assertLess(text.index('new-two'),text.index('new-three'))
        self.assertEqual(self.sync.status()['pending'],3)
        self.assertEqual(self.sync.status()['reviewCount'],0)

    def test_paused_structure_requires_review_without_changing_bengali(self):
        self.sync.configure(False)
        original=(self.root/'content/bn/people.html').read_bytes()
        payload,block=self.structural_payload()
        payload['deleteBlocks']=[block['id']]
        self.save_payload(payload)
        self.assertEqual((self.root/'content/bn/people.html').read_bytes(),original)
        self.sync.configure(True)
        self.assertEqual(self.sync.status()['reviewCount'],1)

    def test_manual_bengali_deletion_does_not_change_english(self):
        original=self.path.read_bytes()
        payload,block=self.structural_payload('bn')
        payload['deleteBlocks']=[block['id']]
        self.save_payload(payload)
        self.assertEqual(self.path.read_bytes(),original)
        self.assertEqual(self.sync.status()['pending'],0)
        self.assertEqual(self.sync.status()['reviewCount'],0)
        self.save_story()
        self.assertEqual(self.sync.status()['reviewCount'],1)

    def test_structural_build_failure_restores_both_sources_and_tracking(self):
        before_en=self.path.read_bytes()
        before_bn=(self.root/'content/bn/people.html').read_bytes()
        state=json.dumps(self.sync.states,sort_keys=True)
        payload,block=self.structural_payload()
        payload['deleteBlocks']=[block['id']]
        with patch.object(editor.subprocess, 'run', return_value=subprocess.CompletedProcess([],1,'','broken')):
            with self.assertRaises(ValueError):editor.save(payload)
        self.assertEqual(self.path.read_bytes(),before_en)
        self.assertEqual((self.root/'content/bn/people.html').read_bytes(),before_bn)
        self.assertEqual(json.dumps(self.sync.states,sort_keys=True),state)

    def test_translation_in_flight_cannot_restore_a_removed_block(self):
        self.save_story()
        following_id=next(r['id'] for r in self.sync.states['person-test-person']['records'] if 'A remembered phrase' in r['en']['html'])
        def replace_during_translation(blocks):
            doc=editor.document('person-test-person','en')
            old=next(b for b in doc['blocks'] if 'Revised life story' in b['html'])
            payload={'id':doc['id'],'lang':'en','version':doc['version'], 'blocks':{},'images':{},
                     'deleteBlocks':[old['id']],
                     'insertBlocks':[{'id':'new-replacement','anchor':old['id'],'position':'after','tag':'p','html':'A replacement paragraph.'}]}
            self.save_payload(payload)
            return {'translations':{b['id']:'STALE DRAFT MUST NEVER RETURN' for b in blocks},'usage':{'input_tokens':10}}
        self.call.side_effect=replace_during_translation
        self.assertFalse(self.process())
        for lang in ('en','bn'):
            text=editor.authored('person-test-person',lang)[1]
            self.assertNotIn('life story',text)
            self.assertNotIn('STALE DRAFT',text)
        self.assertEqual(self.sync.status()['pending'],1)
        self.assertEqual(self.sync.status()['reviewCount'],0)
        following=next(r for r in self.sync.states['person-test-person']['records'] if r.get('en') and 'A remembered phrase' in r['en']['html'])
        self.assertEqual(following['id'],following_id)


if __name__ == '__main__': unittest.main()
