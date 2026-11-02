#!/usr/bin/env python3
"""Exercise weekly selection across publication dates and language editions."""
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from weekly_feature import prepare_weekly_feature


class FeatureParser(HTMLParser):
    def __init__(self, markup):
        super().__init__()
        self.features = []
        self.ids = []
        self.buttons = []
        self.feed(markup)

    def handle_starttag(self, tag, pairs):
        attrs = dict(pairs)
        if 'id' in attrs:
            self.ids.append(attrs['id'])
        if tag == 'section' and 'data-weekly-feature-key' in attrs:
            self.features.append({'attrs': attrs, 'slides': [], 'controls': []})
        if tag == 'article' and 'data-feature-slide' in attrs:
            self.features[-1]['slides'].append(attrs)
        if 'data-feature-controls' in attrs:
            self.features[-1]['controls'].append(attrs)
        if tag == 'button':
            self.buttons.append(attrs)


class WeeklyFeatureTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'content/bn').mkdir(parents=True)
        self.config = {'version': 1, 'excluded_keys': [], 'articles': {}}
        self.history = {}
        self.descriptors = {'en': [], 'bn': []}
        self.article('history', '2026-10-04')
        self.article('origins', '2026-10-03')
        self.article('index', '2026-10-11')

    def article(self, key, updated, bn_updated=None):
        for lang in ('en', 'bn'):
            self.descriptors[lang] = [item for item in self.descriptors[lang] if item[0] != key]
            self.descriptors[lang].append((key, 'Label', lang + ' ' + key, 'A factual description.'))
            self.history[f'{lang}/{key}'] = {'updated': bn_updated if lang == 'bn' and bn_updated else updated}

    def prepare(self, day):
        (self.root / 'content/weekly-feature.json').write_text(json.dumps(self.config))
        return prepare_weekly_feature(self.root, self.history, self.descriptors, day)

    def state(self):
        return json.loads((self.root / 'content/weekly-feature-state.json').read_text())

    def test_current_week_is_locked_while_next_tracks_new_editorial_update(self):
        self.prepare('2026-10-05')
        self.article('origins', '2026-10-07')
        self.prepare('2026-10-08')
        self.assertEqual(self.state()['current'], {'week': '2026-10-05', 'key': 'history'})
        self.assertEqual(self.state()['next'], {'week': '2026-10-12', 'key': 'origins'})
        # Another build with no selection change must leave generated state untouched.
        before = (self.root / 'content/weekly-feature-state.json').stat().st_mtime_ns
        self.prepare('2026-10-09')
        self.assertEqual(before, (self.root / 'content/weekly-feature-state.json').stat().st_mtime_ns)

    def test_monday_preserves_the_already_published_plan(self):
        self.prepare('2026-10-05')
        self.article('origins', '2026-10-08')
        self.prepare('2026-10-09')
        self.article('history', '2026-10-12')
        self.prepare('2026-10-12')
        self.assertEqual(self.state()['current']['key'], 'origins')
        self.assertEqual(self.state()['next']['key'], 'history')

    def test_late_rebuild_preserves_the_selection_visitors_already_saw(self):
        self.prepare('2026-10-05')
        self.article('origins', '2026-10-08')
        self.prepare('2026-10-09')
        self.article('history', '2026-10-24')
        self.prepare('2026-10-26')
        self.assertEqual(self.state()['current'], {'week': '2026-10-26', 'key': 'origins'})
        self.assertEqual(self.state()['next'], {'week': '2026-11-02', 'key': 'history'})

    def test_removed_article_and_editorial_exclusion_have_valid_fallback(self):
        self.prepare('2026-10-05')
        self.descriptors['bn'] = [item for item in self.descriptors['bn'] if item[0] != 'history']
        self.prepare('2026-10-06')
        self.assertEqual(self.state()['current']['key'], 'origins')
        self.article('history', '2026-10-07')
        self.config['excluded_keys'] = ['origins']
        self.prepare('2026-10-07')
        self.assertEqual(self.state()['current']['key'], 'history')

    def test_tied_updates_keep_the_current_choice(self):
        self.article('origins', '2026-10-05')
        self.prepare('2026-10-05')
        self.article('history', '2026-10-05')
        self.prepare('2026-10-06')
        self.assertEqual(self.state()['next']['key'], 'origins')

    def test_override_expires_before_next_week(self):
        self.config['override'] = {'key': 'origins', 'through': '2026-10-11'}
        self.prepare('2026-10-11')
        self.assertEqual(self.state()['current']['key'], 'origins')
        self.assertEqual(self.state()['next']['key'], 'history')
        self.prepare('2026-10-12')
        self.assertEqual(self.state()['current']['key'], 'history')

    def test_bengali_update_can_select_shared_article_with_edition_specific_dates(self):
        self.article('origins', '2026-10-03', '2026-10-10')
        markup = self.prepare('2026-10-11')
        self.assertEqual(self.state()['current']['key'], 'origins')
        self.assertIn('href="origins.html"', markup['bn'])
        self.assertIn('datetime="2026-10-03">3 October 2026', markup['en'])
        self.assertIn('datetime="2026-10-10">১০ অক্টোবর ২০২৬', markup['bn'])
        for lang in ('en', 'bn'):
            self.assertEqual(markup[lang].count('id="weekly-feature-heading"'), 1)
            self.assertEqual(markup[lang].count('id="weekly-feature-next-heading"'), 1)
            self.assertIn('data-weekly-feature-next="2026-10-12"', markup[lang])

    def test_week_uses_india_timezone(self):
        self.prepare(datetime(2026, 10, 11, 19, 0, tzinfo=timezone.utc))
        self.assertEqual(self.state()['current']['week'], '2026-10-12')

    def test_portrait_preserves_attribution_and_does_not_execute_teaser_html(self):
        self.article('person-example', '2026-10-11')
        for lang in ('en', 'bn'):
            path = self.root / 'content' / ('bn' if lang == 'bn' else '') / 'people.html'
            path.write_text('<article class="person-profile" aria-labelledby="example">'
                            '<h2>Example</h2><figure class="person-photo">'
                            '<img src="assets/people/example.jpg" alt="Portrait">'
                            '<figcaption>Photo credit. <a href="https://example.org/licence">Licence</a>'
                            '</figcaption></figure></article>')
        self.config['articles']['person-example'] = {
            'en': {'intro_html': 'A <em>title</em> <script>bad()</script>'}}
        markup = self.prepare('2026-10-11')['en']
        self.assertIn('Photo credit. <a href="https://example.org/licence">Licence</a>', markup)
        self.assertIn('A <em>title</em> &lt;script&gt;bad()&lt;/script&gt;', markup)
        self.assertNotIn('<script>', markup)

    def test_carousel_keeps_weekly_lead_and_fills_with_newest_distinct_articles(self):
        self.prepare('2026-10-05')
        for key, day in [('culture', '2026-10-06'), ('geography', '2026-10-07'),
                         ('person-example', '2026-10-08'), ('surnames', '2026-10-09'),
                         ('translation-example', '2026-10-10')]:
            self.article(key, day)
        parsed = FeatureParser(self.prepare('2026-10-11')['en'])
        current, upcoming = parsed.features
        self.assertEqual([slide['data-feature-key'] for slide in current['slides']],
                         ['history', 'translation-example', 'surnames', 'person-example', 'geography'])
        self.assertEqual(upcoming['slides'][0]['data-feature-key'], 'translation-example')
        for feature in parsed.features:
            keys = [slide['data-feature-key'] for slide in feature['slides']]
            self.assertEqual(len(keys), 5)
            self.assertEqual(len(keys), len(set(keys)))
            self.assertNotIn('index', keys)
            self.assertEqual(feature['attrs']['data-carousel-interval'], '7000')

    def test_editorial_variety_precedes_recency_fill_and_respects_configured_limit(self):
        self.article('person-example', '2026-10-10')
        self.article('aguris-today', '2026-10-02')
        self.article('culture', '2026-10-09')
        self.config['carousel'] = {'limit': 4, 'interval_ms': 9000,
                                  'additional_keys': ['origins', 'origins', 'aguris-today',
                                                      'person-example', 'missing']}
        parsed = FeatureParser(self.prepare('2026-10-11')['en'])
        self.assertEqual([slide['data-feature-key'] for slide in parsed.features[0]['slides']],
                         ['person-example', 'origins', 'aguris-today', 'culture'])
        self.assertEqual(parsed.features[0]['attrs']['data-carousel-interval'], '9000')
        self.config['carousel']['limit'] = 2
        parsed = FeatureParser(self.prepare('2026-10-11')['en'])
        self.assertEqual([slide['data-feature-key'] for slide in parsed.features[0]['slides']],
                         ['person-example', 'origins'])

    def test_carousel_excludes_unpublished_missing_translation_and_excluded_articles(self):
        self.article('culture', '2026-10-09')
        self.article('geography', '2026-10-09')
        self.article('surnames', '2026-10-12')
        self.article('person-example', '2026-10-09')
        self.descriptors['bn'] = [item for item in self.descriptors['bn'] if item[0] != 'geography']
        del self.history['bn/person-example']
        self.config['excluded_keys'] = ['culture']
        self.config['carousel'] = {'additional_keys': ['index', 'culture', 'surnames',
                                                      'geography', 'person-example', 'missing']}
        parsed = FeatureParser(self.prepare('2026-10-11')['en'])
        for feature in parsed.features:
            self.assertEqual([slide['data-feature-key'] for slide in feature['slides']],
                             ['history', 'origins'])

    def test_language_editions_share_order_and_use_localized_controls(self):
        self.article('culture', '2026-10-09')
        self.article('person-example', '2026-10-08', '2026-10-10')
        markup = self.prepare('2026-10-11')
        editions = {lang: FeatureParser(html) for lang, html in markup.items()}
        for en_feature, bn_feature in zip(editions['en'].features, editions['bn'].features):
            self.assertEqual([slide['data-feature-key'] for slide in en_feature['slides']],
                             [slide['data-feature-key'] for slide in bn_feature['slides']])
        self.assertIn('data-feature-counter>১ / ৪</span>', markup['bn'])
        self.assertIn('aria-label="আগের লেখা"', markup['bn'])
        self.assertNotIn('data-feature-toggle', markup['bn'])
        self.assertNotIn('data-feature-toggle', markup['en'])
        self.assertIn('aria-label="৪টির মধ্যে ১ — bn person-example"', markup['bn'])

    def test_progressive_markup_has_unique_ids_and_only_first_slide_visible(self):
        parsed = FeatureParser(self.prepare('2026-10-11')['en'])
        self.assertEqual(len(parsed.ids), len(set(parsed.ids)))
        for feature in parsed.features:
            self.assertNotIn('hidden', feature['slides'][0])
            self.assertTrue(all('hidden' in slide for slide in feature['slides'][1:]))
            self.assertIn('hidden', feature['controls'][0])
        for button in parsed.buttons:
            self.assertEqual(button['type'], 'button')
            if 'data-feature-dot' in button:
                self.assertIn(button['aria-controls'], parsed.ids)
                self.assertEqual(button['aria-pressed'],
                                 'true' if button['data-feature-dot'] == '0' else 'false')

    def test_single_eligible_article_still_has_readable_static_fallback(self):
        self.config['excluded_keys'] = ['origins']
        markup = self.prepare('2026-10-11')['en']
        parsed = FeatureParser(markup)
        for feature in parsed.features:
            self.assertEqual(len(feature['slides']), 1)
            self.assertNotIn('hidden', feature['slides'][0])
            self.assertEqual(feature['slides'][0]['data-feature-key'], 'history')
            self.assertIn('hidden', feature['controls'][0])
        self.assertIn('href="history.html"', markup)

    def test_invalid_carousel_configuration_is_rejected(self):
        for carousel in ({'limit': 0}, {'limit': 9}, {'limit': True},
                         {'interval_ms': 1000}, {'interval_ms': '7000'},
                         {'additional_keys': 'history'}, {'additional_keys': ['../index']}):
            with self.subTest(carousel=carousel):
                self.config['carousel'] = carousel
                with self.assertRaises(ValueError):
                    self.prepare('2026-10-11')


if __name__ == '__main__':
    unittest.main()
