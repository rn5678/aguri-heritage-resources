#!/usr/bin/env python3
"""Content editor regression checks; every save uses an isolated temporary site."""
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).with_name('content_editor.py')
SPEC = importlib.util.spec_from_file_location('content_editor', SCRIPT)
editor = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = editor
SPEC.loader.exec_module(editor)
ACTUAL_ROOT = editor.ROOT

PROFILE = '''<div class="person-profiles">
<article class="person-profile" aria-labelledby="test-person">
 <figure class="person-photo"><a class="family-photo" href="assets/people/original.png"><img src="assets/people/original.png" alt="Original portrait" width="10" height="20" loading="lazy"></a><figcaption>Original <em>photograph</em>. <a href="https://example.org/credit">Source</a>.</figcaption></figure>
 <div class="person-copy"><p class="eyebrow">Literature</p><h2 id="test-person">Test Person</h2><p class="person-dates">1900–1980</p>
 <p>Original life story with <em>emphasis</em>.[cite:source-one][cite:source-one]</p>
 <h3 id="linked-section">Family and work</h3><blockquote><p>A remembered phrase.[cite:source-two]</p></blockquote>
 <div class="data-table"><table><caption>Selected works</caption><tbody><tr><th scope="row">Work</th><td><span lang="bn">বই</span> · Book</td></tr></tbody></table></div>
 </div>
</article>
<article class="person-profile" aria-labelledby="other-person"><figure class="person-photo"><img src="assets/people/other.png" alt="Other portrait" width="10" height="20"><figcaption>Other source.</figcaption></figure><div class="person-copy"><h2 id="other-person">Other Person</h2><p>Keep this biography.[cite:source-two]</p></div></article>
<h2 id="community-connections">Community connections</h2><p>Collection introduction.</p>
</div>'''


def png(width=320, height=480):
    return b'\x89PNG\r\n\x1a\n' + struct.pack('>I', 13) + b'IHDR' + struct.pack('>II', width, height) + b'\x08\x02\x00\x00\x00'


class TemporarySite(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='aguri-editor-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.root_patch = patch.object(editor, 'ROOT', self.root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)
        for folder in ('content/bn', 'assets/people', 'site/assets/uploads', 'scripts'):
            (self.root/folder).mkdir(parents=True, exist_ok=True)
        (self.root/'build.py').write_text("PAGES = [('people','People','Lives','Description'),('history','History','History','Description'),('translations','Translations','Translations','Description'),('review','Review','Review','Description')]\n")
        (self.root/'scripts/check_site.py').write_text('')
        self.path = self.root/'content/people.html'
        self.path.write_text(PROFILE)
        (self.root/'content/bn/people.html').write_text(PROFILE.replace('Test Person', 'বাংলা পরিচয়'))
        for folder in ('content', 'content/bn'):
            (self.root/folder/'history.html').write_text('<div class="prose"><h2 id="history">History</h2><p>A story.[cite:source-one]</p></div>')
            (self.root/folder/'sources.json').write_text(json.dumps({'source-one': {'title': 'First source'}, 'source-two': {'title': 'Second source'}}))
        self.history = self.root/'content/page-history.json'
        self.history.write_text('{"pages":{"en/people":{"updated":"2026-10-01"}}}\n')
        (self.root/'assets/people/original.png').write_bytes(png(10, 20))
        (self.root/'assets/people/other.png').write_bytes(png(10, 20))

    def request(self):
        doc = editor.document('person-test-person', 'en')
        return {'id': doc['id'], 'lang': doc['lang'], 'version': doc['version'], 'blocks': {}, 'images': {}}, doc

    def story_edit(self):
        payload, doc = self.request()
        block = next(b for b in doc['blocks'] if 'Original life story' in b['html'])
        payload['blocks'][block['id']] = block['html'].replace('Original life story', 'Revised life story')
        return payload

    @staticmethod
    def successful_run(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 0, 'PASS\n', '')

    def test_profile_blocks_are_scoped_and_keep_tables_and_nested_quotes(self):
        _, doc = self.request()
        tags = [b['tag'] for b in doc['blocks']]
        self.assertIn('td', tags)
        self.assertIn('th', tags)
        self.assertIn('caption', tags)
        self.assertNotIn('blockquote', tags)
        self.assertTrue(any('A remembered phrase.' in b['html'] for b in doc['blocks']))
        self.assertFalse(any('Other Person' in b['html'] for b in doc['blocks']))
        self.assertEqual(len(doc['images']), 1)
        self.assertEqual(doc['preview'], '/preview/person-test-person.html')
        self.assertTrue(any('data-cite="source-one"' in b['html'] for b in doc['blocks']))

    def test_collection_editor_excludes_individual_biographies(self):
        doc = editor.document('people', 'en')
        self.assertEqual([b['tag'] for b in doc['blocks']], ['h2', 'p'])
        self.assertEqual(doc['images'], [])

    def test_generated_and_private_pages_are_not_offered(self):
        ids = [p['id'] for p in editor.pages()['pages']]
        self.assertIn('person-test-person', ids)
        self.assertIn('history', ids)
        self.assertNotIn('translations', ids)
        self.assertNotIn('review', ids)
        with self.assertRaises(editor.EditError):
            editor.document('translations', 'en')

    def test_save_patches_only_edited_span_and_preserves_bengali(self):
        before = self.path.read_bytes()
        bengali = (self.root/'content/bn/people.html').read_bytes()
        history = self.history.read_bytes()
        payload = self.story_edit()
        with patch.object(editor.subprocess, 'run', side_effect=self.successful_run) as run:
            response = editor.save(payload)
        self.assertTrue(response['ok'])
        self.assertEqual(self.path.read_bytes(), before.replace(b'Original life story', b'Revised life story'))
        self.assertEqual((self.root/'content/bn/people.html').read_bytes(), bengali)
        self.assertEqual([Path(call.args[0][-1]).name for call in run.call_args_list], ['build.py', 'check_site.py'])
        backups = list((self.root/'local-editor/backups').iterdir())
        self.assertEqual(len(backups), 1)
        self.assertEqual((backups[0]/'content/people.html').read_bytes(), before)
        self.assertEqual((backups[0]/'page-history.json').read_bytes(), history)
        self.assertNotEqual(response['document']['version'], payload['version'])

    def test_bengali_save_leaves_english_unchanged(self):
        english = self.path.read_bytes()
        doc = editor.document('person-test-person', 'bn')
        heading = next(b for b in doc['blocks'] if b['tag'] == 'h2')
        payload = {'id': doc['id'], 'lang': 'bn', 'version': doc['version'], 'blocks': {heading['id']: 'সংশোধিত বাংলা পরিচয়'}}
        with patch.object(editor.subprocess, 'run', side_effect=self.successful_run):
            editor.save(payload)
        self.assertEqual(self.path.read_bytes(), english)
        self.assertIn('<h2 id="test-person">সংশোধিত বাংলা পরিচয়</h2>', (self.root/'content/bn/people.html').read_text())

    def test_delete_cited_paragraph_saves_and_renumbers_remaining_citations(self):
        for lang in ('en', 'bn'):
            with self.subTest(language=lang):
                doc = editor.document('person-test-person', lang)
                block = next(b for b in doc['blocks'] if 'Original life story' in b['html'])
                path = self.root/'content'/('bn' if lang == 'bn' else '')/'people.html'
                before = path.read_text()
                payload = {'id':doc['id'], 'lang':lang, 'version':doc['version'], 'blocks':{block['id']:''}}
                with patch.object(editor.subprocess, 'run', side_effect=self.successful_run):
                    response = editor.save(payload)
                removed = 'Original life story with <em>emphasis</em>.[cite:source-one][cite:source-one]'
                self.assertEqual(path.read_text(), before.replace(removed, ''))
                remaining = next(b for b in response['document']['blocks'] if 'A remembered phrase' in b['html'])
                self.assertIn('>[1]</span>', remaining['html'])
                self.assertNotIn('source-one', ''.join(b['html'] for b in response['document']['blocks']))
                backups = list((self.root/'local-editor/backups').glob('*/'+str(path.relative_to(self.root))))
                self.assertTrue(any(p.read_text() == before for p in backups))

    def test_stale_or_unknown_blocks_cannot_write(self):
        payload = self.story_edit()
        self.path.write_text(PROFILE + '\n<!-- External edit -->')
        before = self.path.read_bytes()
        with patch.object(editor.subprocess, 'run') as run:
            with self.assertRaisesRegex(editor.EditError, 'changed elsewhere'):
                editor.save(payload)
            run.assert_not_called()
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse((self.root/'local-editor/backups').exists())
        payload, _ = self.request()
        payload['blocks'] = {'999999': 'Unexpected edit'}
        with self.assertRaisesRegex(editor.EditError, 'Reload'):
            editor.save(payload)

    def test_unchanged_document_creates_no_backup_and_does_not_build(self):
        payload, _ = self.request()
        with patch.object(editor.subprocess, 'run') as run:
            result = editor.save(payload)
            run.assert_not_called()
        self.assertIn('No changes', result['message'])
        self.assertFalse((self.root/'local-editor/backups').exists())

    def test_photo_replacement_updates_link_and_retains_original(self):
        payload, doc = self.request()
        data = png(320, 480)
        payload['images'][doc['images'][0]['id']] = {'dataUrl': 'data:image/png;base64,'+base64.b64encode(data).decode(), 'alt': 'A "portrait" <description>'}
        with patch.object(editor.subprocess, 'run', side_effect=self.successful_run):
            editor.save(payload)
        text = self.path.read_text()
        tree = editor.Tree(text)
        image = next(n for n in tree.nodes if n.tag == 'img')
        self.assertEqual(image.attrs['width'], '320')
        self.assertEqual(image.attrs['height'], '480')
        self.assertEqual(image.attrs['alt'], 'A "portrait" <description>')
        self.assertEqual(image.parent.attrs['href'], image.attrs['src'])
        self.assertEqual((self.root/image.attrs['src']).read_bytes(), data)
        self.assertTrue((self.root/'assets/people/original.png').is_file())
        self.assertIn('Original <em>photograph</em>.', text)
        self.assertIn('Keep this biography.[cite:source-two]', text)

    def test_invalid_photo_is_rejected_before_any_write(self):
        for data in (b'<svg><script>bad()</script></svg>', png(0, 480), png(40000, 1)):
            with self.subTest(data=data):
                payload, doc = self.request()
                payload['images'][doc['images'][0]['id']] = {'dataUrl':'data:image/png;base64,'+base64.b64encode(data).decode()}
                with self.assertRaises(editor.EditError):
                    editor.save(payload)
                self.assertEqual(self.path.read_text(), PROFILE)
        self.assertFalse((self.root/'local-editor/backups').exists())

    def test_failed_build_or_check_restores_source_history_and_new_assets(self):
        for failed_step in (0, 1):
            with self.subTest(failed_step=failed_step):
                before = self.path.read_bytes()
                history = self.history.read_bytes()
                payload, doc = self.request()
                payload.update(blocks=self.story_edit()['blocks'])
                payload['images'][doc['images'][0]['id']] = {'dataUrl':'data:image/png;base64,'+base64.b64encode(png()).decode()}
                calls = []
                def run(command, **kwargs):
                    calls.append(command)
                    self.history.write_text('changed by build')
                    for image in (self.root/'assets/uploads').glob('*'):
                        (self.root/'site/assets/uploads'/image.name).write_bytes(image.read_bytes())
                    return subprocess.CompletedProcess(command, int(len(calls)-1 == failed_step), '', 'Deliberate test failure' if len(calls)-1 == failed_step else '')
                with patch.object(editor.subprocess, 'run', side_effect=run):
                    with self.assertRaisesRegex(editor.EditError, 'previous version has been restored'):
                        editor.save(payload)
                self.assertEqual(self.path.read_bytes(), before)
                self.assertEqual(self.history.read_bytes(), history)
                self.assertFalse(list((self.root/'assets/uploads').glob('*')))
                self.assertFalse(list((self.root/'site/assets/uploads').glob('*')))
                self.assertEqual(Path(calls[-1][-1]).name, 'build.py')

    def test_failed_recovery_build_still_restores_history(self):
        before = self.path.read_bytes()
        history = self.history.read_bytes()
        calls = []
        def run(command, **kwargs):
            calls.append(command)
            self.history.write_text('changed history')
            if len(calls) == 1:
                return subprocess.CompletedProcess(command, 1, '', 'Initial build failed')
            raise subprocess.TimeoutExpired(command, 180)
        with patch.object(editor.subprocess, 'run', side_effect=run):
            with self.assertRaises(subprocess.TimeoutExpired):
                editor.save(self.story_edit())
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.history.read_bytes(), history)


class InlineValidation(unittest.TestCase):
    def test_source_chips_are_round_tripped_with_multiplicity(self):
        original = 'Text.[cite:one][cite:one]'
        chip = '<span class="editor-citation" contenteditable="false" data-cite="one">[1]</span>'
        self.assertEqual(editor.clean_block('New text.'+chip+chip, original), 'New text.[cite:one][cite:one]')
        self.assertEqual(editor.clean_block('Text.'+chip, original), 'Text.[cite:one]')
        self.assertEqual(editor.clean_block('Text.', original), 'Text.')
        self.assertEqual(editor.clean_block('', original), '')
        self.assertEqual(editor.clean_block('<br>', original), '<br>')
        for invalid in ('Text.[cite:one][cite:two]', 'Text.'+chip+chip+chip):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(editor.EditError, 'source references'):
                editor.clean_block(invalid, original)

    def test_citation_removal_controls_do_not_enter_saved_content(self):
        chip = '<span class="editor-citation" contenteditable="false" data-cite="one">[1]<button type="button" aria-label="Remove citation 1">×</button></span>'
        self.assertEqual(editor.clean_block('Text.'+chip, 'Text.[cite:one]'), 'Text.[cite:one]')

    def test_blocks_scripts_and_dangerous_links_are_rejected(self):
        for value in ('<script>alert(1)</script>', '<img src=x onerror=alert(1)>', '<iframe src="https://example.org"></iframe>', '<table><tr><td>bad</td></tr></table>', '<a href="javascript:alert(1)">bad</a>', '<a href="java&#x09;script:alert(1)">bad</a>', '<a href="data:text/html,bad">bad</a>', '<a href="//example.org">bad</a>'):
            with self.subTest(value=value), self.assertRaises(editor.EditError):
                editor.clean_block(value, 'Text')
        self.assertEqual(editor.clean_block('<span onclick="bad()" style="color:red">Safe</span>', 'Text'), '<span>Safe</span>')

    def test_original_inline_ids_and_generated_fields_are_protected(self):
        original = '<span id="named-link">Text</span> {{source_count}}'
        edited = '<span id="named-link">New text</span> {{source_count}}'
        self.assertEqual(editor.clean_block(edited, original), edited)
        for invalid in ('<span>Text</span> {{source_count}}', '<span id="named-link">Text</span>', '<span id="new-name">Text</span> {{source_count}}'):
            with self.subTest(invalid=invalid), self.assertRaises(editor.EditError):
                editor.clean_block(invalid, original)

    def test_valid_links_and_unicode_survive(self):
        value = '<a href="history.html#linked-section" title="A &amp; B">বাংলা <span aria-hidden="true">→</span></a> <em>text</em><br><a href="mailto:test@example.org">Email</a>'
        self.assertEqual(editor.clean_block(value, value), value)

    def test_supported_image_header_variants(self):
        jpeg = b'\xff\xd8\xff\xc0' + struct.pack('>H', 11) + b'\x08' + struct.pack('>HH', 480, 320) + b'\x01\x01\x11\x00'
        webp_x = b'RIFF'+b'\x00'*4+b'WEBPVP8X'+struct.pack('<I', 10)+b'\x00'*4+(319).to_bytes(3,'little')+(479).to_bytes(3,'little')
        webp_lossy = b'RIFF'+b'\x00'*4+b'WEBPVP8 '+struct.pack('<I', 10)+b'\x00'*3+b'\x9d\x01\x2a'+struct.pack('<HH', 320, 480)
        packed = (319 | (479 << 14)).to_bytes(4, 'little')
        webp_lossless = b'RIFF'+b'\x00'*4+b'WEBPVP8L'+struct.pack('<I', 5)+b'\x2f'+packed
        for data, extension in ((png(),'png'), (jpeg,'jpg'), (webp_x,'webp'), (webp_lossy,'webp'), (webp_lossless,'webp')):
            with self.subTest(extension=extension, data=data[:16]):
                self.assertEqual(editor.image_info(data), (extension, 320, 480))


class ExistingSourcesReadOnly(unittest.TestCase):
    def test_every_offered_page_loads_and_preserves_all_source_chips(self):
        """Exercise every real source without saving or rebuilding any real file."""
        with patch.object(editor, 'ROOT', ACTUAL_ROOT):
            for page in editor.pages()['pages']:
                for lang in ('en', 'bn'):
                    with self.subTest(page=page['id'], lang=lang):
                        path, text, blocks, _ = editor.authored(page['id'], lang)
                        doc = editor.document(page['id'], lang)
                        self.assertEqual(doc['version'], hashlib.sha256(path.read_bytes()).hexdigest())
                        originals = {str(n.start): text[n.opening:n.close] for n in blocks}
                        for block in doc['blocks']:
                            original = originals[block['id']]
                            cleaned = editor.clean_block(block['html'], original)
                            self.assertEqual(editor.Counter(editor.CITE.findall(cleaned)), editor.Counter(editor.CITE.findall(original)))


class PublicCitationRendering(unittest.TestCase):
    """Render actual public-note markup in memory, without a site build or writes."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(ACTUAL_ROOT))
        try:
            spec = importlib.util.spec_from_file_location('content_editor_public_render_test', ACTUAL_ROOT/'build.py')
            cls.build = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.build)
        finally:
            sys.path.pop(0)

    def render(self, paragraphs, lang):
        sources = {
            key: {'title': title, 'status': 'Verified source' if lang == 'en' else 'যাচাইকৃত উৎস',
                  'url': 'https://example.org/'+key}
            for key, title in [('one', 'First source' if lang == 'en' else 'প্রথম উৎস'),
                               ('two', 'Second source' if lang == 'en' else 'দ্বিতীয় উৎস'),
                               ('three', 'Third source' if lang == 'en' else 'তৃতীয় উৎস')]
        }
        sources_before = json.dumps(sources, ensure_ascii=False)

        class ReadOnlyHistory:
            def updated(self, *args):
                return '2026-10-11'

        fragment = '<div class="prose">'+''.join('<p>'+p+'</p>' for p in paragraphs)+'</div>'
        html, _ = self.build.render_page('rights', 'Rights', 'Test article', 'Description', fragment, lang,
                                         sources, {p[0]: p[1] for p in self.build.PAGES}, ReadOnlyHistory())
        self.assertEqual(json.dumps(sources, ensure_ascii=False), sources_before)
        self.assertNotIn('[cite:', html)
        references = re.findall(r'<sup class="citation"><a id="(ref-[^"]+)" href="#note-(\d+)"[^>]*>\[([^]]+)\]</a></sup>', html)
        notes = re.findall(r'<li id="note-(\d+)"><a href="https://example.org/([^"/]+)">([^<]+)</a>', html)
        self.assertEqual(len({ref[0] for ref in references}), len(references))
        self.assertTrue({ref[1] for ref in references}.issubset({note[0] for note in notes}))
        return html, references, notes

    def test_removing_unused_first_source_renumbers_public_notes_in_both_languages(self):
        for lang in ('en', 'bn'):
            with self.subTest(lang=lang):
                before = ['First.[cite:one]', 'Second.[cite:two]', 'Third.[cite:three]']
                _, _, before_notes = self.render(before, lang)
                self.assertEqual([(n[0], n[1]) for n in before_notes], [('1', 'one'), ('2', 'two'), ('3', 'three')])
                after = [editor.clean_block('First.', before[0]), *before[1:]]
                html, references, notes = self.render(after, lang)
                self.assertEqual([(n[0], n[1]) for n in notes], [('1', 'two'), ('2', 'three')])
                self.assertEqual([ref[1] for ref in references], ['1', '2'])
                self.assertEqual([ref[2] for ref in references], ['১', '২'] if lang == 'bn' else ['1', '2'])
                self.assertNotIn('https://example.org/one', html)
                self.assertNotIn('bibliography.html#source-one', html)

    def test_reused_source_remains_and_follows_surviving_first_occurrence(self):
        for lang in ('en', 'bn'):
            with self.subTest(lang=lang):
                before = ['First.[cite:one]', 'Second.[cite:two]', 'Reused.[cite:one]', 'Repeated.[cite:two]', 'Third.[cite:three]']
                after = [editor.clean_block('', before[0]), *before[1:]]
                _, references, notes = self.render(after, lang)
                self.assertEqual([(n[0], n[1]) for n in notes], [('1', 'two'), ('2', 'one'), ('3', 'three')])
                self.assertEqual([ref[1] for ref in references], ['1', '2', '1', '3'])
                self.assertEqual([ref[2] for ref in references], ['১', '২', '১', '৩'] if lang == 'bn' else ['1', '2', '1', '3'])
                self.assertEqual(sum(n[1] == 'one' for n in notes), 1)
                self.assertEqual(sum(n[1] == 'two' for n in notes), 1)

    def test_removing_all_citations_omits_public_notes(self):
        for lang in ('en', 'bn'):
            with self.subTest(lang=lang):
                cleaned = editor.clean_block('Remaining text.', 'Original text.[cite:one][cite:two]')
                html, references, notes = self.render([cleaned], lang)
                self.assertEqual(references, [])
                self.assertEqual(notes, [])
                self.assertNotIn('id="notes-heading"', html)
                self.assertNotIn('class="notes"', html)


if __name__ == '__main__':
    unittest.main()
