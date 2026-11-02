#!/usr/bin/env python3
"""Page creation regression checks; all writes use isolated temporary sites."""
from contextlib import contextmanager
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch


HERE = Path(__file__).resolve().parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


creation = load('aguri_page_creation_test', HERE / 'editor_page_creation.py')
editor = load('aguri_content_editor_creation_test', HERE / 'content_editor.py')
registry = load('aguri_authored_pages_creation_test', HERE.parent / 'authored_pages.py')


class TemporarySite(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='aguri-page-creation-test-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for folder in ('content/bn', 'scripts', 'site/bn'):
            (self.root / folder).mkdir(parents=True, exist_ok=True)
        (self.root / 'build.py').write_text(
            "PAGES = [('people','People','Lives','Description'),"
            "('history','History','History','Description'),('review','Review','Review','Description')]\n")
        (self.root / 'scripts/check_site.py').write_text('')
        for folder in ('content', 'content/bn'):
            for name in ('people', 'history'):
                (self.root / folder / (name + '.html')).write_text(
                    '<div class="prose"><h2 id="intro">Introduction</h2><p>Existing content.</p></div>')
            (self.root / folder / 'sources.json').write_text('{}\n')
        self.history = self.root / 'content/page-history.json'
        self.history.write_text('{"pages":{"en/history":{"updated":"2026-10-01"}}}\n')
        self.path = self.root / 'content/editor-pages.json'
        for name, value in (('ROOT', self.root), ('PUBLISHER', None), ('TRANSLATOR', None),
                            ('LOCK', threading.Lock()), ('authored_pages', registry)):
            current = patch.object(editor, name, value, create=True)
            current.start()
            self.addCleanup(current.stop)

    def payload(self, **changes):
        return {'type': 'article', 'slug': 'community-memories', 'title': 'Community memories',
                'description': 'Memories shared by the community.', 'titleBn': 'সম্প্রদায়ের স্মৃতি',
                'descriptionBn': 'সম্প্রদায়ের ভাগ করে নেওয়া স্মৃতি।', 'section': 'history',
                'lang': 'en', **changes}

    @staticmethod
    def successful_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, 'PASS\n', '')

    @contextmanager
    def verified(self):
        with patch.object(creation.subprocess, 'run', side_effect=self.successful_run) as run:
            yield run

    def assert_no_creation(self):
        self.assertFalse(self.path.exists())
        self.assertFalse((self.root / 'local-editor/backups').exists())
        self.assertFalse((self.root / 'content/community-memories.html').exists())

    def test_bilingual_page_is_persisted_and_available_for_editing(self):
        history = self.history.read_bytes()
        with self.verified() as run:
            result = creation.create_page(editor, self.payload(lang='bn'))
        self.assertTrue(result['ok'])
        self.assertEqual(result['document']['id'], 'community-memories')
        self.assertEqual(result['document']['lang'], 'bn')
        self.assertIn('community-memories', {page['id'] for page in result['pages']})
        self.assertEqual([Path(call.args[0][-1]).name for call in run.call_args_list],
                         ['build.py', 'check_site.py'])
        persisted = registry.load_registry(self.root)['pages'][0]
        self.assertEqual(persisted['type'], 'article')
        self.assertEqual(persisted['section'], 'history')
        self.assertEqual(persisted['en']['title'], 'Community memories')
        self.assertEqual(persisted['bn']['title'], 'সম্প্রদায়ের স্মৃতি')
        for lang, description in (('en', self.payload()['description']), ('bn', self.payload()['descriptionBn'])):
            doc = editor.document('community-memories', lang)
            self.assertTrue(any(description in block['html'] for block in doc['blocks']))
            self.assertTrue(any(block['canDelete'] for block in doc['blocks']))
        backup = next((self.root / 'local-editor/backups').iterdir())
        self.assertEqual((backup / 'page-history.json').read_bytes(), history)
        self.assertFalse(json.loads((backup / 'change.json').read_text())['registryExisted'])

    def test_created_page_saves_through_existing_editor_without_changing_other_language(self):
        with self.verified():
            creation.create_page(editor, self.payload())
        bengali = (self.root / 'content/bn/community-memories.html').read_bytes()
        doc = editor.document('community-memories', 'en')
        block = next(block for block in doc['blocks'] if 'Memories shared' in block['html'])
        with self.verified():
            result = editor.save({'id': doc['id'], 'lang': 'en', 'version': doc['version'],
                                  'blocks': {block['id']: 'A revised introduction.'}})
        self.assertTrue(result['ok'])
        self.assertIn('A revised introduction.', (self.root / 'content/community-memories.html').read_text())
        self.assertEqual((self.root / 'content/bn/community-memories.html').read_bytes(), bengali)

    def test_each_builtin_template_has_matching_bilingual_headings(self):
        expected = {'article': ['overview', 'context', 'sources'], 'general': ['overview', 'details'],
                    'biography': ['life', 'work', 'legacy']}
        for template, identities in expected.items():
            with self.subTest(template=template), self.verified():
                creation.create_page(editor, self.payload(slug='example-' + template, type=template))
                headings = []
                for lang in ('en', 'bn'):
                    _, text, blocks, _ = editor.authored('example-' + template, lang)
                    headings.append([block.attrs['id'] for block in blocks if block.tag == 'h2'])
                    self.assertEqual(headings[-1], identities)
                self.assertEqual(*headings)

    def test_custom_type_preserves_existing_registry_and_controls_page_template(self):
        with self.verified():
            creation.create_page(editor, self.payload())
        before = registry.load_registry(self.root)
        history = self.history.read_bytes()
        with patch.object(creation.subprocess, 'run') as run:
            result = creation.create_type(editor, {'name': 'Village profile', 'template': 'general',
                                                   'description': 'Local information and village memories.'})
            run.assert_not_called()
        self.assertTrue(result['ok'])
        after = registry.load_registry(self.root)
        self.assertEqual(after['pages'], before['pages'])
        self.assertEqual(after['types'][0]['id'], 'village-profile')
        self.assertEqual(self.history.read_bytes(), history)
        with self.verified():
            creation.create_page(editor, self.payload(type='village-profile', slug='my-village'))
        self.assertIn('<h2 id="details">Further information</h2>',
                      (self.root / 'content/my-village.html').read_text())
        self.assertNotIn('History and context', (self.root / 'content/my-village.html').read_text())
        backups = list((self.root / 'local-editor/backups').glob('*/content/editor-pages.json'))
        self.assertTrue(any(json.loads(path.read_text()) == before for path in backups))

    def test_non_ascii_type_name_gets_safe_stable_identifier(self):
        creation.create_type(editor, {'name': 'গ্রামের কথা', 'template': 'article', 'description': 'গ্রামের ইতিহাস।'})
        entry = registry.load_registry(self.root)['types'][0]
        self.assertRegex(entry['id'], r'^type-[a-f0-9]{12}$')
        before = self.path.read_bytes()
        with self.assertRaisesRegex(editor.EditError, 'already uses'):
            creation.create_type(editor, {'name': 'গ্রামের কথা', 'template': 'general', 'description': 'গ্রামের কথা।'})
        self.assertEqual(self.path.read_bytes(), before)

    def test_duplicate_page_source_generated_and_builtin_addresses_are_rejected(self):
        for folder, slug in (('content', 'authored-but-unlisted'), ('content/bn', 'bengali-only'),
                             ('site', 'generated-only'), ('site/bn', 'generated-bengali')):
            (self.root / folder / (slug + '.html')).write_text('Keep this file.')
        for slug in ('history', 'review', 'index', 'authored-but-unlisted', 'bengali-only',
                     'generated-only', 'generated-bengali'):
            with self.subTest(slug=slug), patch.object(creation.subprocess, 'run') as run:
                with self.assertRaises(editor.EditError):
                    creation.create_page(editor, self.payload(slug=slug))
                run.assert_not_called()
        self.assert_no_creation()
        with self.verified():
            creation.create_page(editor, self.payload())
        before = self.path.read_bytes()
        source = (self.root / 'content/community-memories.html').read_bytes()
        with self.assertRaisesRegex(editor.EditError, 'already uses'):
            creation.create_page(editor, self.payload(title='Do not replace the page'))
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual((self.root / 'content/community-memories.html').read_bytes(), source)

    def test_unsafe_addresses_and_invalid_metadata_never_write(self):
        for slug in ('../outside', '/outside', 'x/y', 'a%2fb', 'UPPER', 'a--b', '-a', 'a-', 'a' * 81,
                     'person-new-person', 'translation-new-work', 'book-new-book', '', None):
            with self.subTest(slug=slug), self.assertRaises(editor.EditError):
                creation.create_page(editor, self.payload(slug=slug))
        for fields in ({'titleBn': ''}, {'descriptionBn': None}, {'description': 'x' * 501},
                       {'title': 'A\x00title'}, {'title': 'A\x7ftitle'}, {'description': '{{source_count}}'},
                       {'section': []}, {'section': 'unknown'}, {'type': 'unknown'}, {'lang': 'fr'}):
            with self.subTest(fields=fields), self.assertRaises(editor.EditError):
                creation.create_page(editor, self.payload(**fields))
        self.assert_no_creation()

    def test_html_in_descriptions_is_escaped_and_long_title_has_short_menu_label(self):
        description = '<script>alert("unsafe")</script> & text'
        with self.verified():
            creation.create_page(editor, self.payload(description=description, title='T' * 180))
        source = (self.root / 'content/community-memories.html').read_text()
        self.assertNotIn('<script>', source)
        self.assertIn('&lt;script&gt;', source)
        self.assertIn('&amp; text', source)
        metadata = registry.load_registry(self.root)['pages'][0]['en']
        self.assertEqual(metadata['description'], description)
        self.assertEqual(metadata['title'], 'T' * 180)
        self.assertLessEqual(len(metadata['label']), 120)

    def test_invalid_type_or_duplicate_name_never_replaces_registry(self):
        for fields in ({'name': ''}, {'name': 'x' * 81}, {'name': 'New\nname'}, {'name': 'Bad\x7fname'},
                       {'template': 'custom'}, {'template': []}, {'description': ''}, {'description': 'x' * 241},
                       {'name': 'Article'}, {'name': 'General'}):
            # "General" normalizes to the built-in id even though its name is
            # "General page", and must be rejected as well.
            with self.subTest(fields=fields), self.assertRaises(editor.EditError):
                creation.create_type(editor, {'name': 'Village profile', 'template': 'general',
                                              'description': 'Village information.', **fields})
        self.assert_no_creation()

    def test_publishing_blocks_both_operations_without_creating_backups(self):
        class BusyPublisher:
            def busy(self):
                return True
        with patch.object(editor, 'PUBLISHER', BusyPublisher()):
            with self.assertRaisesRegex(editor.EditError, 'publishing'):
                creation.create_page(editor, self.payload())
            with self.assertRaisesRegex(editor.EditError, 'publishing'):
                creation.create_type(editor, {'name': 'New type', 'template': 'article', 'description': 'New layout.'})
        self.assert_no_creation()

    def test_failed_build_and_check_restore_registry_sources_history_and_generated_pages(self):
        creation.create_type(editor, {'name': 'Village profile', 'template': 'general', 'description': 'Village details.'})
        before = self.path.read_bytes()
        history = self.history.read_bytes()
        for failed_step in (0, 1):
            calls = []
            def run(command, **kwargs):
                calls.append(command)
                self.history.write_text('changed by a build')
                for edition in ('', 'bn'):
                    (self.root / 'site' / edition / 'community-memories.html').write_text('Generated new page')
                # Recovery rebuild should not emit a now-unregistered page.
                if len(calls) > failed_step + 1:
                    for edition in ('', 'bn'):
                        (self.root / 'site' / edition / 'community-memories.html').unlink(missing_ok=True)
                return subprocess.CompletedProcess(command, int(len(calls) - 1 == failed_step), '', 'Test failure')
            with self.subTest(failed_step=failed_step), patch.object(creation.subprocess, 'run', side_effect=run):
                with self.assertRaisesRegex(editor.EditError, 'previous version has been restored'):
                    creation.create_page(editor, self.payload())
            self.assertEqual(self.path.read_bytes(), before)
            self.assertEqual(self.history.read_bytes(), history)
            for folder in ('content', 'content/bn', 'site', 'site/bn'):
                self.assertFalse((self.root / folder / 'community-memories.html').exists())
            self.assertEqual(Path(calls[-1][-1]).name, 'build.py')

    def test_failed_first_page_restores_absent_registry_and_history_even_if_recovery_times_out(self):
        self.history.unlink()
        calls = []
        def run(command, **kwargs):
            calls.append(command)
            self.history.write_text('build created history')
            if len(calls) == 1:
                return subprocess.CompletedProcess(command, 1, '', 'Build failed')
            raise subprocess.TimeoutExpired(command, 180)
        with patch.object(creation.subprocess, 'run', side_effect=run):
            with self.assertRaises(subprocess.TimeoutExpired):
                creation.create_page(editor, self.payload())
        self.assertFalse(self.path.exists())
        self.assertFalse(self.history.exists())
        self.assertFalse((self.root / 'content/community-memories.html').exists())
        self.assertFalse((self.root / 'content/bn/community-memories.html').exists())

    def test_new_page_captures_only_its_translation_baseline_without_model_calls(self):
        class TranslationBaseline:
            def __init__(self):
                self.mutex = threading.RLock()
                self.titles = {'history': 'History'}
                self.captured = []
                self.running = True
                self.error = ''
            def capture(sync, doc_id):
                self.assertTrue(editor.LOCK.locked())
                for lang in ('en', 'bn'):
                    self.assertTrue(editor.document(doc_id, lang)['blocks'])
                sync.captured.append(doc_id)
            def initialize(sync, pages):
                self.fail('initialize must not reacquire the editor lock or refresh unrelated pages')
        sync = TranslationBaseline()
        with patch.object(editor, 'TRANSLATOR', sync), self.verified():
            creation.create_page(editor, self.payload())
        self.assertEqual(sync.captured, ['community-memories'])
        self.assertEqual(sync.titles, {'history': 'History', 'community-memories': 'Community memories'})
        self.assertEqual(sync.error, '')

    def test_translation_setup_failure_reports_saved_page_with_tracking_warning(self):
        settings = self.root / 'local-editor/translation/settings.json'
        settings.parent.mkdir(parents=True)
        settings.write_text('{"enabled":true}')
        with patch.object(editor, 'translator', side_effect=ValueError('Unreadable translation settings')), self.verified():
            result = creation.create_page(editor, self.payload())
        self.assertTrue(result['ok'])
        self.assertIn('tracking needs attention', result['message'])
        self.assertTrue((self.root / 'content/community-memories.html').exists())
        self.assertTrue((self.root / 'content/bn/community-memories.html').exists())
        self.assertEqual(registry.load_registry(self.root)['pages'][0]['id'], 'community-memories')

    def test_real_translation_baseline_queues_only_future_english_edits(self):
        translation = load('aguri_creation_translation_test', HERE / 'editor_translation.py')
        settings = self.root / 'local-editor/translation/settings.json'
        settings.parent.mkdir(parents=True)
        settings.write_text('{"enabled":true}')
        sync = translation.Translator(self.root, editor.LOCK, editor.authored, editor.clean_block,
                                      lambda: False, start_worker=False)
        with patch.object(editor, 'TRANSLATOR', sync), self.verified():
            creation.create_page(editor, self.payload())
            self.assertEqual(set(sync.states), {'community-memories'})
            self.assertEqual(sync.mapping.pending_jobs(sync.states['community-memories']), [])
            with patch.object(sync.client, 'translate') as model:
                self.assertFalse(sync.run_once())
                model.assert_not_called()
            doc = editor.document('community-memories', 'en')
            block = next(block for block in doc['blocks'] if 'Memories shared' in block['html'])
            editor.save({'id': doc['id'], 'lang': 'en', 'version': doc['version'],
                         'blocks': {block['id']: 'A future English revision.'}})
        pending = sync.mapping.pending_jobs(sync.states['community-memories'])
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]['en_html'], 'A future English revision.')


if __name__ == '__main__':
    unittest.main()
