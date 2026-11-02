"""Visible block deletion, formatting, and bilingual structural integrity."""
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import test_content_editor_blocks as fixture
editor = fixture.editor
service_spec = importlib.util.spec_from_file_location('visible_block_translation', Path(__file__).with_name('editor_translation.py'))
service = importlib.util.module_from_spec(service_spec)
service_spec.loader.exec_module(service)


class VisibleBlocks(unittest.TestCase):
    setUp = fixture.StructuralEditing.setUp
    request = fixture.StructuralEditing.request
    block = fixture.StructuralEditing.block
    addition = fixture.StructuralEditing.addition
    good_run = fixture.StructuralEditing.good_run

    def translator(self):
        sync = service.Translator(self.root, editor.LOCK, editor.authored, editor.clean_block,
                                  lambda: False, start_worker=False)
        sync.configure(True)
        sync.initialize(editor.pages()['pages'])
        handle = patch.object(editor,'TRANSLATOR',sync)
        handle.start(); self.addCleanup(handle.stop)
        return sync

    def test_delete_image_removes_single_image_figure_and_ignores_caption_edits(self):
        payload,doc=self.request()
        photo=doc['images'][0];caption=self.block(doc,'Photo caption')
        self.assertTrue(photo['canDelete'])
        self.assertIn(caption['id'],photo['deleteBlockIds'])
        payload.update(deleteImages=[photo['id']],blockFormats={caption['id']:{'align':'invalid'}})
        payload['deleteBlocks']=[caption['id']]
        payload['blocks'][caption['id']]='Changed caption that must not survive'
        payload['images'][photo['id']]={'dataUrl':'invalid but deleted'}
        result=editor.save(payload)
        text=self.path.read_text()
        self.assertNotIn('<figure',text)
        self.assertNotIn('Photo caption',text)
        self.assertNotIn('Changed caption',text)
        self.assertEqual(result['document']['images'],[])

    def test_multi_image_figure_keeps_other_image_and_shared_caption(self):
        self.path.write_text(fixture.PROFILE.replace('alt="Portrait">','alt="Portrait"><img src="assets/second.png" alt="Second">',1))
        payload,doc=self.request()
        photo=doc['images'][0]
        self.assertEqual(photo['deleteBlockIds'],[])
        payload['deleteImages']=[photo['id']]
        editor.save(payload)
        text=self.path.read_text()
        self.assertNotIn('assets/portrait.png',text)
        self.assertIn('assets/second.png',text)
        self.assertIn('Photo caption.',text)

    def test_shared_image_link_keeps_other_photo_when_one_is_deleted(self):
        self.path.write_text(fixture.PROFILE.replace('<img src="assets/portrait.png" alt="Portrait">', '<a href="assets/portrait.png"><img src="assets/portrait.png" alt="Portrait"><img src="assets/second.png" alt="Second"></a>',1))
        payload,doc=self.request()
        payload['deleteImages']=[doc['images'][0]['id']]
        editor.save(payload)
        text=self.path.read_text()
        self.assertNotIn('<img src="assets/portrait.png"',text)
        self.assertIn('<img src="assets/second.png"',text)
        self.assertIn('Photo caption.',text)

    def test_deleted_primary_heading_uses_identity_not_remaining_section_heading(self):
        self.path.write_text(fixture.PROFILE.replace('<h3 id="linked-heading">Family</h3>', '<h2 id="linked-heading">Family</h2>'))
        payload,doc=self.request()
        payload['deleteBlocks']=[self.block(doc,'Test Person')['id']]
        result=editor.save(payload)
        self.assertEqual(result['document']['title'],'Test Person')
        self.assertEqual(next(page['title'] for page in editor.pages()['pages'] if page['id']=='person-test-person'),'Test Person')
        marker='<span id="test-person" data-editor-anchor="true" data-editor-tag="h2" hidden></span>'
        self.path.write_text(self.path.read_text().replace(marker, '<h2 id="test-person">Renamed Person</h2>'))
        payload,doc=self.request()
        self.assertEqual(doc['title'],'Renamed Person')
        payload['deleteBlocks']=[self.block(doc,'Renamed Person')['id']]
        result=editor.save(payload)
        self.assertEqual(result['document']['title'],'Renamed Person')
        self.assertIn('data-editor-title="Renamed Person"',self.path.read_text())

    def test_alignment_is_outer_style_and_preserves_other_existing_style(self):
        self.path.write_text(fixture.PROFILE.replace('<p>First body','<p style="margin: 0; text-align: right">First body',1))
        payload,doc=self.request();block=self.block(doc,'First body')
        self.assertEqual(block['format'],{'align':'right'})
        payload['blockFormats']={block['id']:{'align':'center'}}
        result=editor.save(payload)
        self.assertIn('style="margin: 0; text-align: center"',self.path.read_text())
        self.assertEqual(self.block(result['document'],'First body')['format'],{'align':'center'})
        payload,doc=self.request();block=self.block(doc,'First body')
        payload['blockFormats']={block['id']:{'align':''}}
        editor.save(payload)
        self.assertIn('style="margin: 0"',self.path.read_text())
        self.assertNotIn('text-align:',self.path.read_text())

    def test_unapproved_alignment_or_arbitrary_css_is_rejected(self):
        payload,doc=self.request();block=self.block(doc,'First body')
        for value in ({'align':'center;display:none'},{'align':'center','style':'color:red'},{'align':'inherit'},'center'):
            payload['blockFormats']={block['id']:value}
            with self.subTest(value=value),self.assertRaises(editor.EditError):
                editor.save(payload)
        self.assertEqual(self.path.read_text(),fixture.PROFILE)

    def test_delete_all_and_add_new_formatted_body_in_one_save(self):
        payload,doc=self.request()
        payload['deleteBlocks']=[block['id'] for block in doc['blocks']]
        payload['deleteImages']=[image['id'] for image in doc['images']]
        addition=self.addition('new-only',{'id':'document-end'},html='Replacement content.')
        addition['format']={'align':'justify'}
        payload['insertBlocks']=[addition]
        result=editor.save(payload)
        self.assertEqual([block['html'] for block in result['document']['blocks']],['Replacement content.'])
        self.assertEqual(result['document']['blocks'][0]['format'],{'align':'justify'})
        self.assertEqual(result['document']['images'],[])
        self.assertIn('Keep the other biography.',self.path.read_text())
        self.assertIn('data-editor-title="Test Person"',self.path.read_text())

    def test_strike_browser_formatting_and_named_links_survive_cleaning(self):
        original='<a name="old-location" href="https://example.org">Named</a> text.'
        cleaned=editor.clean_block('<a name="old-location">Named</a> <strike>old</strike><del>older</del><span style="text-decoration: underline line-through; color: red">text.</span>',original)
        self.assertIn('<a name="old-location">Named</a>',cleaned)
        self.assertIn('<s>old</s><s>older</s>',cleaned)
        self.assertIn('<span><u><s>text.</s></u></span>',cleaned)
        self.assertNotIn('style=',cleaned)
        with self.assertRaises(editor.EditError):
            editor.clean_block('Removed named anchor',original)

    def test_delete_block_preserves_both_modern_and_legacy_anchor_targets(self):
        self.path.write_text(fixture.PROFILE.replace('First body paragraph', '<a id="modern" name="legacy">Dual linked text</a> First body paragraph',1))
        payload,doc=self.request()
        payload['deleteBlocks']=[self.block(doc,'First body paragraph')['id']]
        editor.save(payload)
        text=self.path.read_text()
        self.assertIn('<span id="modern" data-editor-anchor="true"',text)
        self.assertIn('<span id="legacy" data-editor-anchor="true"',text)
        self.assertNotIn('Dual linked text',text)

    def test_english_image_and_caption_deletion_updates_unique_bengali_photo(self):
        sync=self.translator()
        payload,doc=self.request()
        payload['deleteImages']=[doc['images'][0]['id']]
        editor.save(payload)
        self.assertNotIn('<figure',self.path.read_text())
        self.assertNotIn('<figure',self.bn.read_text())
        self.assertNotIn('Photo caption',self.bn.read_text())
        self.assertEqual(sync.status()['reviewCount'],0)
        self.assertEqual(sync.status()['pending'],0)

    def test_ambiguous_bengali_image_is_retained_and_requires_review(self):
        self.bn.write_text(self.bn.read_text().replace('alt="Portrait">','alt="Portrait"><img src="assets/portrait.png" alt="Duplicate">',1))
        sync=self.translator()
        payload,doc=self.request()
        payload['deleteImages']=[doc['images'][0]['id']]
        editor.save(payload)
        self.assertIn('assets/portrait.png',self.bn.read_text())
        self.assertGreater(sync.status()['reviewCount'],0)
        self.assertTrue(sync.states['person-test-person'].get('image_review'))
        with self.assertRaisesRegex(ValueError,'Finish or review'):
            sync.assert_publish_ready()
        sync.accept('person-test-person')
        self.assertEqual(sync.status()['reviewCount'],0)

    def test_paired_linked_heading_deletion_preserves_ids_and_stable_other_pairs(self):
        sync=self.translator()
        payload,doc=self.request();heading=self.block(doc,'Family')
        payload['deleteBlocks']=[heading['id']]
        editor.save(payload)
        for path in (self.path,self.bn):
            self.assertNotIn('<h3 id="linked-heading">',path.read_text())
            self.assertIn('id="linked-heading" data-editor-anchor="true"',path.read_text())
        self.assertEqual(sync.status()['reviewCount'],0)
        self.assertEqual(sync.status()['pending'],0)

    def test_empty_end_insertion_creates_paired_bengali_placeholder(self):
        sync=self.translator()
        payload,doc=self.request()
        payload['deleteBlocks']=[block['id'] for block in doc['blocks']]
        payload['deleteImages']=[image['id'] for image in doc['images']]
        new=self.addition('new-paired-end',{'id':'document-end'},html='New English body.')
        new['format']={'align':'center'}
        payload['insertBlocks']=[new]
        editor.save(payload)
        self.assertIn('<p data-editor-block="new-paired-end" style="text-align: center"></p>',self.bn.read_text())
        self.assertEqual(sync.status()['pending'],1)
        self.assertEqual(sync.status()['reviewCount'],0)

    def test_manual_bengali_image_deletion_leaves_english_intact(self):
        sync=self.translator()
        before=self.path.read_bytes()
        payload,doc=self.request('bn')
        payload['deleteImages']=[doc['images'][0]['id']]
        editor.save(payload)
        self.assertEqual(self.path.read_bytes(),before)
        self.assertNotIn('<figure',self.bn.read_text())
        self.assertEqual(sync.status()['pending'],0)

    def test_failed_check_restores_image_caption_and_alignment(self):
        payload,doc=self.request()
        payload['deleteImages']=[doc['images'][0]['id']]
        payload['blockFormats']={self.block(doc,'First body')['id']:{'align':'right'}}
        original=self.path.read_bytes()
        def fail(command,**options):
            result=self.good_run(command,**options)
            if Path(command[1]).name=='check_site.py': result.returncode=1
            return result
        with patch.object(editor.subprocess,'run',side_effect=fail),self.assertRaises(editor.EditError):
            editor.save(payload)
        self.assertEqual(self.path.read_bytes(),original)

    def test_removing_summary_does_not_invent_details_label_or_hide_remaining_content(self):
        self.path.write_text(fixture.PROFILE.replace('<ul>', '<details><summary>Remove disclosure label</summary><p>Keep disclosure content</p></details><ul>',1))
        payload,doc=self.request()
        payload['deleteBlocks']=[self.block(doc,'Remove disclosure label')['id']]
        editor.save(payload)
        text=self.path.read_text()
        self.assertNotIn('Remove disclosure label',text)
        self.assertIn('<details open><summary data-editor-anchor="true" hidden></summary>',text)
        self.assertIn('Keep disclosure content',text)

    def test_override_notice_describes_actual_editing_scope(self):
        target=self.root/'content/profiles/test-person.en.json'
        target.parent.mkdir()
        target.write_text(json.dumps({'title':'Detailed title','subtitle':'Detailed subtitle','body':'Detailed body'}))
        _,doc=self.request()
        self.assertIn('collection entry',doc['editingNotice'])
        _,bengali=self.request('bn')
        self.assertEqual(bengali['editingNotice'],'')


if __name__=='__main__':
    unittest.main()
