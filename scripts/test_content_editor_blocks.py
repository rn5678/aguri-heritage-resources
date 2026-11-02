#!/usr/bin/env python3
"""Paragraph structure checks using temporary sites; no network or AI calls."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

SPEC=importlib.util.spec_from_file_location('content_editor_blocks_tested',Path(__file__).with_name('content_editor.py'))
editor=importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name]=editor
SPEC.loader.exec_module(editor)

PROFILE='''<div class="person-profiles">
<article class="person-profile" aria-labelledby="test-person"><figure class="person-photo"><img src="assets/portrait.png" alt="Portrait"><figcaption>Photo caption.</figcaption></figure><div class="person-copy">
<p class="eyebrow">Literature</p><h2 id="test-person">Test Person</h2><p class="person-dates">1900–1980</p>
<p>First body paragraph with <em>emphasis</em>.[cite:source-one]</p>
<h3 id="linked-heading">Family</h3><p>Second body paragraph.</p>
<p id="linked-body">Linked body paragraph.</p><p>A <span id="linked-word">linked word</span>.</p>
<p>{{source_count}} published sources.</p><blockquote><p>A remembered quotation.</p></blockquote>
<ul><li>A list item.</li></ul><div class="data-table"><table><caption>Works</caption><tbody><tr><td>A table cell.</td><td><p>A paragraph in a table.</p></td></tr></tbody></table></div>
</div></article>
<article class="person-profile" aria-labelledby="other-person"><div class="person-copy"><h2 id="other-person">Other Person</h2><p>Keep the other biography.</p></div></article>
</div>'''


class StructuralEditing(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='aguri-block-test-')
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        for folder in ('content/bn','assets','scripts','site/assets/uploads'):
            (self.root/folder).mkdir(parents=True,exist_ok=True)
        (self.root/'build.py').write_text("PAGES=[('people','People','Lives','Description')]\n")
        (self.root/'scripts/check_site.py').write_text('')
        self.path=self.root/'content/people.html'
        self.bn=self.root/'content/bn/people.html'
        self.path.write_text(PROFILE);self.bn.write_text(PROFILE.replace('First body paragraph','প্রথম অনুচ্ছেদ'))
        for folder in ('content','content/bn'):
            (self.root/folder/'sources.json').write_text(json.dumps({'source-one':{'title':'Known source'}}))
        self.history=self.root/'content/page-history.json';self.history.write_text('{"pages":{}}\n')
        self.patches=[patch.object(editor,'ROOT',self.root),patch.object(editor,'PUBLISHER',None),
                      patch.object(editor,'TRANSLATOR',None),patch.object(editor.subprocess,'run',side_effect=self.good_run)]
        for item in self.patches:item.start();self.addCleanup(item.stop)

    def good_run(self,command,**options):
        return subprocess.CompletedProcess(command,0,'PASS\n','')

    def request(self,lang='en'):
        doc=editor.document('person-test-person',lang)
        payload={'id':doc['id'],'lang':lang,'version':doc['version'],'blocks':{},'images':{},'deleteBlocks':[],'insertBlocks':[]}
        return payload,doc

    def block(self,doc,needle):
        return next(block for block in doc['blocks'] if needle in block['html'])

    def addition(self,identity,anchor,position='after',html='A new <strong>paragraph</strong>.'):
        return {'id':identity,'anchor':anchor['id'],'position':position,'tag':'p','html':html}

    def test_capabilities_protect_required_and_linked_fields_but_leave_insertion_anchors(self):
        _,doc=self.request()
        for needle in ('First body paragraph','Second body paragraph','A remembered quotation'):
            block=self.block(doc,needle)
            self.assertTrue(block['canDelete']);self.assertTrue(block['canInsertBefore']);self.assertTrue(block['canInsertAfter'])
        for needle in ('Test Person','Literature','1900','linked word','Linked body paragraph','source_count','Photo caption','A list item','A table cell','A paragraph in a table'):
            block=self.block(doc,needle)
            self.assertFalse(block['canDelete'],needle);self.assertTrue(block['deleteReason'],needle)
        self.assertTrue(self.block(doc,'Test Person')['canInsertAfter'])
        for needle in ('Photo caption','A list item','A table cell','A paragraph in a table'):
            self.assertFalse(self.block(doc,needle)['canInsertAfter'],needle)

    def test_complete_paragraph_deletion_removes_wrapper_and_ignores_its_unsaved_text(self):
        payload,doc=self.request();body=self.block(doc,'First body paragraph')
        payload['deleteBlocks']=[body['id']]
        payload['blocks'][body['id']]='This edit was discarded by removal.'
        bn_before=self.bn.read_bytes()
        response=editor.save(payload)
        updated=self.path.read_text()
        self.assertNotIn('First body paragraph',updated)
        self.assertNotIn('This edit was discarded',updated)
        self.assertNotIn('<p></p>',updated)
        self.assertIn('Second body paragraph',updated)
        self.assertIn('Keep the other biography',updated)
        self.assertEqual(self.bn.read_bytes(),bn_before)
        self.assertTrue(response['ok'])
        backup=next((self.root/'local-editor/backups').iterdir())
        self.assertEqual((backup/'content/people.html').read_text(),PROFILE)

    def test_insert_before_after_and_edit_existing_text_in_one_save(self):
        payload,doc=self.request();body=self.block(doc,'First body paragraph');other=self.block(doc,'Second body paragraph')
        payload['blocks'][other['id']]='Revised second paragraph.'
        payload['insertBlocks']=[self.addition('new-before',body,'before','Before text.'),self.addition('new-after',body,html='After text.')]
        response=editor.save(payload);text=self.path.read_text()
        self.assertLess(text.index('Before text.'),text.index('First body paragraph'))
        self.assertLess(text.index('First body paragraph'),text.index('After text.'))
        self.assertIn('<p data-editor-block="new-before">Before text.</p>',text)
        self.assertIn('Revised second paragraph.',text)
        self.assertNotIn('Second body paragraph.',text)
        new=self.block(response['document'],'Before text.')
        self.assertTrue(new['canDelete'])

    def test_multiple_insertions_use_payload_order_and_deleted_anchor_boundaries(self):
        payload,doc=self.request();body=self.block(doc,'First body paragraph')
        payload['deleteBlocks']=[body['id']]
        payload['insertBlocks']=[self.addition('new-a',body,'after','After one.'),
                                 self.addition('new-b',body,'after','After two.'),
                                 self.addition('new-c',body,'before','Before one.'),
                                 self.addition('new-d',body,'before','Before two.')]
        editor.save(payload);text=self.path.read_text()
        self.assertNotIn('First body paragraph',text)
        self.assertEqual(sorted(('Before one.','Before two.','After one.','After two.'),key=text.index),
                         ['Before one.','Before two.','After one.','After two.'])

    def test_headings_allow_new_paragraph_even_when_last_normal_paragraph_was_deleted(self):
        payload,doc=self.request()
        payload['deleteBlocks']=[block['id'] for block in doc['blocks'] if block['canDelete']]
        editor.save(payload)
        payload,doc=self.request();heading=self.block(doc,'Test Person')
        payload['insertBlocks']=[self.addition('new-rebuilt',heading,html='A fresh biography paragraph.')]
        editor.save(payload)
        self.assertIn('A fresh biography paragraph.',self.path.read_text())

    def test_bengali_structure_changes_leave_english_unchanged(self):
        english=self.path.read_bytes();payload,doc=self.request('bn')
        body=self.block(doc,'প্রথম অনুচ্ছেদ');payload['deleteBlocks']=[body['id']]
        payload['insertBlocks']=[self.addition('new-bengali',body,html='নতুন বাংলা অনুচ্ছেদ।')]
        editor.save(payload)
        self.assertEqual(self.path.read_bytes(),english)
        self.assertNotIn('প্রথম অনুচ্ছেদ',self.bn.read_text())
        self.assertIn('নতুন বাংলা অনুচ্ছেদ।',self.bn.read_text())

    def test_protected_deletion_and_unsafe_placement_are_rejected_before_backup(self):
        _,doc=self.request()
        for needle in ('Test Person','Literature','1900','linked word','Linked body paragraph','source_count','Photo caption','A list item','A table cell'):
            payload,_=self.request();payload['deleteBlocks']=[self.block(doc,needle)['id']]
            with self.subTest(delete=needle),self.assertRaises(editor.EditError):editor.save(payload)
        payload,_=self.request();payload['insertBlocks']=[self.addition('new-bad',self.block(doc,'A table cell'))]
        with self.assertRaises(editor.EditError):editor.save(payload)
        self.assertEqual(self.path.read_text(),PROFILE)
        self.assertFalse((self.root/'local-editor/backups').exists())

    def test_new_paragraph_sanitizes_formatting_and_accepts_known_citations_only(self):
        payload,doc=self.request();body=self.block(doc,'First body paragraph')
        payload['insertBlocks']=[self.addition('new-cited',body,html='<a href="https://example.org" onclick="bad()">Known source</a>.[cite:source-one]')]
        editor.save(payload);text=self.path.read_text()
        self.assertIn('<a href="https://example.org">Known source</a>.[cite:source-one]',text)
        self.assertNotIn('onclick',text)
        for html in ('Unknown.[cite:invented]','<span id="new-target">Text</span>',
                     '<a name="target">Text</a>','{{source_count}} items','<script>bad()</script>',
                     '<a href="javascript:bad()">Bad link</a>','[cite:source-one]','<br>'):
            payload,doc=self.request();payload['insertBlocks']=[self.addition('new-invalid',self.block(doc,'First body paragraph'),html=html)]
            before=self.path.read_bytes()
            with self.subTest(html=html),self.assertRaises(editor.EditError):editor.save(payload)
            self.assertEqual(self.path.read_bytes(),before)

    def test_new_identifiers_must_be_valid_and_unique_across_source_and_batch(self):
        payload,doc=self.request();body=self.block(doc,'First body paragraph')
        addition=self.addition('new-reused',body)
        payload['insertBlocks']=[addition,addition]
        with self.assertRaises(editor.EditError):editor.save(payload)
        payload['insertBlocks']=[addition];editor.save(payload)
        payload,doc=self.request();body=self.block(doc,'First body paragraph')
        for identity in ('new-reused','not-new','new-UPPER','new-'+('a'*77),'new-'):
            payload['insertBlocks']=[self.addition(identity,body)]
            with self.subTest(identity=identity),self.assertRaises(editor.EditError):editor.save(payload)

    def test_stale_or_unknown_operations_cannot_change_source(self):
        payload,doc=self.request();body=self.block(doc,'First body paragraph')
        variants=[{'deleteBlocks':['unknown']},{'deleteBlocks':[body['id'],body['id']]},
                  {'deleteBlocks':[{}]},{'insertBlocks':{}},
                  {'insertBlocks':[{**self.addition('new-invalid',body),'anchor':'unknown'}]},
                  {'insertBlocks':[{**self.addition('new-invalid',body),'tag':'h1'}]}]
        for variant in variants:
            with self.subTest(variant=variant),self.assertRaises(editor.EditError):editor.save({**payload,**variant})
        self.path.write_text(PROFILE+'\n<!-- external edit -->')
        with self.assertRaisesRegex(editor.EditError,'changed elsewhere'):editor.save(payload)

    def translation_stub(self,related):
        settings=self.root/'local-editor/translation/settings.json';settings.parent.mkdir(parents=True,exist_ok=True);settings.write_text('{"enabled":true}')
        sync=Mock();sync.enabled=True;sync.error=''
        finish=Mock()
        sync.plan_structure.return_value={'related':related,'finish':finish}
        return sync,finish

    def test_translation_hook_gets_all_offsets_after_atomic_bilingual_save(self):
        payload,doc=self.request();body=self.block(doc,'First body paragraph')
        payload['deleteBlocks']=[body['id']]
        payload['insertBlocks']=[self.addition('new-paired',body,html='New paired paragraph.')]
        bn_before=self.bn.read_text();_,_,bn_blocks,_=editor.authored(payload['id'],'bn')
        bn_node=next(node for node in bn_blocks if 'প্রথম অনুচ্ছেদ' in bn_before[node.opening:node.close])
        related=[{'path':self.bn,'before':bn_before,'patches':[(bn_node.start,bn_node.end,'<p data-editor-block="new-paired">নতুন অনুচ্ছেদ।</p>')]}]
        sync,finish=self.translation_stub(related)
        with patch.object(editor,'translator',return_value=sync):editor.save(payload)
        args,kwargs=sync.plan_structure.call_args
        self.assertEqual(args[:2],('person-test-person','en'))
        self.assertEqual(args[2][0].start,int(body['id']))
        self.assertEqual(args[3][0]['id'],'new-paired')
        self.assertEqual(kwargs['capabilities'],editor.block_capabilities)
        changes=finish.call_args.args[0]
        self.assertEqual(set(changes),{'en','bn'})
        for lang,path in (('en',self.path),('bn',self.bn)):
            self.assertEqual(changes[lang]['after'],path.read_text())
            self.assertEqual(editor.apply_patches(changes[lang]['before'],changes[lang]['patches']),changes[lang]['after'])
        self.assertEqual(sync.capture.call_count,2)
        backup=next((self.root/'local-editor/backups').iterdir())
        self.assertEqual((backup/'content/bn/people.html').read_text(),bn_before)

    def test_failed_build_restores_both_languages_and_never_commits_mapping(self):
        payload,doc=self.request();body=self.block(doc,'First body paragraph')
        payload['deleteBlocks']=[body['id']]
        bn_before=self.bn.read_text();en_before=self.path.read_text();history_before=self.history.read_bytes()
        sync,finish=self.translation_stub([{'path':self.bn,'before':bn_before,'patches':[(0,0,'<!-- paired change -->')]}])
        def failure(command,**options):
            if Path(command[1]).name=='check_site.py':return subprocess.CompletedProcess(command,1,'Check failed','')
            self.history.write_text('Generated history update')
            return self.good_run(command,**options)
        with patch.object(editor,'translator',return_value=sync),patch.object(editor.subprocess,'run',side_effect=failure):
            with self.assertRaisesRegex(editor.EditError,'previous version has been restored'):editor.save(payload)
        self.assertEqual(self.path.read_text(),en_before);self.assertEqual(self.bn.read_text(),bn_before)
        self.assertEqual(self.history.read_bytes(),history_before)
        finish.assert_not_called()

    def test_paused_translation_still_receives_structure_plan_and_successful_finish(self):
        payload,doc=self.request();payload['deleteBlocks']=[self.block(doc,'First body paragraph')['id']]
        sync,finish=self.translation_stub([]);sync.enabled=False
        with patch.object(editor,'translator',return_value=sync):editor.save(payload)
        sync.plan_structure.assert_called_once();finish.assert_called_once()

    def test_mapping_finish_failure_reports_saved_content_without_undoing_it(self):
        payload,doc=self.request();payload['deleteBlocks']=[self.block(doc,'First body paragraph')['id']]
        sync,finish=self.translation_stub([]);finish.side_effect=ValueError('Mapping unavailable')
        with patch.object(editor,'translator',return_value=sync):response=editor.save(payload)
        self.assertTrue(response['ok']);self.assertIn('tracking needs attention',response['message'])
        self.assertNotIn('First body paragraph',self.path.read_text())

    def test_whole_block_removal_renumbers_actual_public_notes_in_both_languages(self):
        actual_root=Path(__file__).resolve().parents[1]
        sys.path.insert(0,str(actual_root))
        try:
            spec=importlib.util.spec_from_file_location('block_deletion_public_render',actual_root/'build.py')
            build=importlib.util.module_from_spec(spec);spec.loader.exec_module(build)
        finally:sys.path.pop(0)
        sources={key:{'title':key,'status':'Verified source','url':'https://example.org/'+key}
                 for key in ('source-one','source-two')}
        for folder in ('content','content/bn'):
            (self.root/folder/'sources.json').write_text(json.dumps(sources))
        class History:
            def updated(self,*args):return '2026-10-11'
        for lang,path in (('en',self.path),('bn',self.bn)):
            with self.subTest(lang=lang):
                path.write_text(path.read_text().replace('Second body paragraph.','Second body paragraph.[cite:source-two]')
                                .replace('A remembered quotation.','A remembered quotation.[cite:source-one]'))
                source_before=(self.root/'content/sources.json').read_bytes()
                payload,doc=self.request(lang)
                first=next(block for block in doc['blocks'] if 'emphasis' in block['html'])
                payload['deleteBlocks']=[first['id']]
                editor.save(payload)
                html,_=build.render_page('rights','Rights','Article','Description',path.read_text(),lang,
                                         sources,{page[0]:page[1] for page in build.PAGES},History())
                notes=re.findall(r'<li id="note-(\d+)"><a href="https://example.org/([^"/]+)">',html)
                references=re.findall(r'<sup class="citation"><a id="[^"]+" href="#note-(\d+)"[^>]*>\[([^]]+)\]',html)
                self.assertEqual(notes,[('1','source-two'),('2','source-one')])
                self.assertEqual(references,[('1','১'),('2','২')] if lang=='bn' else [('1','1'),('2','2')])
                self.assertNotIn('[cite:',html)
                self.assertEqual((self.root/'content/sources.json').read_bytes(),source_before)


class PatchBoundaries(unittest.TestCase):
    def test_insertion_at_both_deletion_boundaries_is_valid_and_ordered(self):
        text='ABCDEF'
        patches=editor.normalized_patches(text,[(1,4,''),(1,1,'before1'),(4,4,'after1'),(1,1,'before2'),(4,4,'after2')])
        self.assertEqual(editor.apply_patches(text,patches),'Abefore1before2after1after2EF')

    def test_interior_and_overlapping_replacements_are_rejected(self):
        for patches in ([(1,4,''),(2,2,'bad')],[(1,4,''),(3,5,'bad')],[(0,99,'bad')]):
            with self.subTest(patches=patches),self.assertRaises(editor.EditError):editor.normalized_patches('ABCDEF',patches)


if __name__=='__main__':unittest.main()
