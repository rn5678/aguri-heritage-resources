"""Deleted authored blocks stay deleted in derived pages; fixtures never edit content."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import re
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import build
import culture_page
import history_hero
import people_page
import portrait_headers
import profile_pages


class EditedProfileBuild(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root/'content/bn').mkdir(parents=True)
        (self.root/'content/profiles').mkdir()
        for module in (profile_pages, portrait_headers):
            context = patch.object(module, 'ROOT', self.root)
            context.start()
            self.addCleanup(context.stop)
        context = patch.object(profile_pages, 'profile_secondary_artwork', return_value='')
        context.start()
        self.addCleanup(context.stop)
        portrait_headers.authored_portraits.cache_clear()
        self.addCleanup(portrait_headers.authored_portraits.cache_clear)

    def source(self, copy, photo='', identity=''):
        value = ('<div class="person-profiles"><article class="person-profile" '
                 'aria-labelledby="test-person"'+identity+'>'+photo+
                 '<div class="person-copy">'+copy+'</div></article></div>')
        for suffix in ('', 'bn/'):
            (self.root/'content'/f'{suffix}people.html').write_text(value)
        return value

    def test_deleted_name_and_all_body_keep_route_without_restoring_visible_copy(self):
        self.source('<span id="test-person" data-editor-anchor="true" data-editor-tag="h2" hidden></span>',
                    identity=' data-editor-title="Test Person"')
        fragments, descriptors = profile_pages.profiles('en')
        self.assertEqual(descriptors, [('person-test-person','Test Person','Test Person','Test Person')])
        fragment = fragments['person-test-person']
        self.assertIn('data-editor-title-hidden="true"', fragment)
        self.assertIn('data-editor-description-hidden="true"', fragment)
        self.assertNotIn('Life and work', fragment)
        self.assertNotIn('Test Person', profile_pages.plain(fragments['people']))
        labels = {key: label for key,label,*_ in build.PAGES}
        body, _ = build.render_page(*descriptors[0], fragment, 'en', {}, labels,
                                    SimpleNamespace(updated=lambda *args: '2026-10-01'))
        self.assertIn('<h1 hidden data-editor-generated="true">Test Person</h1>', body)
        self.assertNotIn('<h1>Test Person</h1>', body)
        self.assertNotIn('<p class="dek">Test Person</p>', body)

    def test_formatted_paragraph_survives_profile_and_collection(self):
        self.source('<h2 id="test-person" style="text-align: center">Test Person</h2>'
                    '<p style="text-align: right">Remaining biography.</p>')
        fragments, _ = profile_pages.profiles('en')
        for key in ('people','person-test-person'):
            self.assertIn('<p style="text-align: right">Remaining biography.</p>',fragments[key])
        self.assertIn('style="text-align: center">Life and work',fragments['person-test-person'])

    def test_absent_portrait_and_caption_use_text_heading(self):
        self.source('<h2 id="test-person">Test Person</h2>')
        rendered = portrait_headers.portrait_heading('person-test-person','<h1>Test Person</h1>','en')
        self.assertIn('page-heading-profile-text',rendered)
        self.assertNotIn('profile-portrait-status',rendered)
        gallery = portrait_headers._collection_heading('Title','en',{})
        self.assertNotIn('<figure',gallery)
        self.assertNotIn('<details',gallery)

    def test_name_without_heading_requires_explicit_identity(self):
        self.source('<p>Body</p>')
        with self.assertRaisesRegex(ValueError,'preserved editor identity'):
            profile_pages.profiles('en')

    def test_deleted_name_does_not_promote_remaining_section_heading(self):
        self.source('<span id="test-person" data-editor-anchor="true" hidden></span>'
                    '<h2 id="family">Family and work</h2><p>Remaining biography.</p>',
                    identity=' data-editor-title="Test Person"')
        fragments, descriptors = profile_pages.profiles('en')
        self.assertEqual(descriptors[0][2], 'Test Person')
        self.assertIn('data-editor-title-hidden="true"', fragments['person-test-person'])
        self.assertIn('<h2 id="family">Family and work</h2>', fragments['person-test-person'])
        self.assertNotIn('Life and work', fragments['person-test-person'])
        self.assertEqual(portrait_headers.authored_portraits('en')['test-person']['name'], '')

    def test_restored_explicit_name_takes_priority_over_preserved_metadata(self):
        self.source('<h2 id="family">Family</h2><h2 id="test-person">Restored Name</h2>'
                    '<p>Remaining biography.</p>', identity=' data-editor-title="Old Name"')
        fragments, descriptors = profile_pages.profiles('en')
        self.assertEqual(descriptors[0][2], 'Restored Name')
        self.assertNotIn('data-editor-title-hidden="true"', fragments['person-test-person'])
        self.assertIn('<h2 id="family">Family</h2>', fragments['person-test-person'])
        self.assertEqual(portrait_headers.authored_portraits('en')['test-person']['name'], 'Restored Name')

    def test_captionless_portrait_stays_available(self):
        photo='<figure class="person-photo"><img src="assets/photo.jpg" alt="Photo"></figure>'
        self.source('<h2 id="test-person">Test Person</h2>', photo=photo)
        self.assertEqual(portrait_headers.authored_portraits('en')['test-person']['figure'],photo)
        with patch.object(portrait_headers,'COLLECTION_SELECTION',('test-person',)):
            gallery=portrait_headers._collection_heading('Title','en',portrait_headers.authored_portraits('en'))
        self.assertIn('assets/photo.jpg',gallery)
        self.assertNotIn('people-heading-credits',gallery)


class EditedStoryBuild(unittest.TestCase):
    def card(self, key='origins', title='Original title', summary='', kicker=''):
        return ('<article class="guide-card">'+(f'<p class="guide-kicker">{kicker}</p>' if kicker else '')+
                (f'<h3><a href="{key}.html">{title}</a></h3>' if title else '')+
                (f'<p class="guide-description">{summary}</p>' if summary else '')+'</article>')

    def test_story_missing_summary_and_eyebrow_still_has_real_title(self):
        parsed=history_hero.Stories();parsed.feed(self.card())
        result=history_hero.carousel_markup(parsed.cards,'','en',history_hero.IMAGES,
                                          history_hero.LABELS['en'],'history-hero','stories')
        self.assertIn('Original title',result)
        self.assertNotIn('aria-describedby',result)
        self.assertNotIn('history-hero-summary',result)
        self.assertNotIn('history-hero-kicker',result)
        self.assertNotIn('history-hero-label',result)

    def test_deleted_story_titles_remove_derived_slides(self):
        body=('<figure class="page-artwork">Generated artwork</figure>'
              '<section aria-labelledby="explore-history-stories">'
              '<span id="explore-history-stories" data-editor-anchor="true" hidden></span>'+
              self.card(title='')+'</section>')
        result=history_hero.render_hero(body,'en')
        self.assertNotIn('history-hero-slide',result)
        self.assertNotIn('Generated artwork',result)

    def test_one_surviving_story_has_correct_count_and_collection_link(self):
        body=('<figure class="page-artwork">Art</figure><section aria-labelledby="explore-history-stories">'
              '<h2 id="explore-history-stories" style="text-align: center">Stories</h2>'+
              self.card()+'</section>')
        result=history_hero.render_hero(body,'en')
        self.assertIn('aria-label="1 / 1"',result)
        self.assertIn('All stories below',result)
        self.assertNotIn('All eight stories',result)

    def test_culture_deleted_heading_and_cards_build_without_reappearing(self):
        body=('<figure class="page-artwork">Art</figure>'
              '<span id="culture-reading-routes" data-editor-anchor="true" data-editor-tag="h2" hidden></span>'
              '<div class="guide-grid">'+self.card('aguris-today',title='')+'</div>'
              '<script src="assets/parent-guides.js" defer></script>')
        result=culture_page.render_culture(body,'en',build.ARTWORKS)
        self.assertNotIn('culture-hero-slide',result)
        self.assertNotIn('page-artwork',result)

    def test_population_note_can_be_deleted_independently(self):
        body=('<span id="people-population-source-a" data-editor-anchor="true" hidden></span>'
              '<p class="small" id="people-population-source-b">Remaining note</p>')
        self.assertEqual(people_page._population_sources_to_notes(body),body)


class IndependentHeadings(unittest.TestCase):
    def test_explicit_bengali_ids_survive_independent_deletion(self):
        bengali='<h2 id="second" style="text-align: center">দ্বিতীয়</h2>'
        self.assertEqual(build.align_headings(bengali,'<h2 id="first">First</h2><h2 id="second">Second</h2>'),bengali)

    def test_deleted_anchor_disambiguates_remaining_idless_heading(self):
        bengali='<span id="first" data-editor-anchor="true" hidden></span><h2>দ্বিতীয়</h2>'
        result=build.align_headings(bengali,'<h2 id="first">First</h2><h2 id="second">Second</h2>')
        self.assertIn('<h2 id="second">',result)

    def test_ambiguous_idless_headings_require_identity(self):
        with self.assertRaisesRegex(ValueError,'unambiguously'):
            build.align_headings('<h2>শিরোনাম</h2>','<h2 id="first">First</h2><h2 id="second">Second</h2>')

    def test_deleted_homepage_h1_gets_hidden_structure_only(self):
        fragment='<span data-editor-anchor="true" data-editor-tag="h1" hidden></span><p>Remaining home copy.</p>'
        labels={key: label for key,label,*_ in build.PAGES}
        body,_=build.render_page(*build.PAGES[0],fragment,'en',{},labels,
                                 SimpleNamespace(updated=lambda *args:'2026-10-01'))
        self.assertIn('<h1 hidden data-editor-generated="true">Aguri Heritage</h1>',body)
        self.assertNotIn('<h1>Aguri Heritage</h1>',body)


if __name__ == '__main__':
    unittest.main()
