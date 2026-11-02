#!/usr/bin/env python3
"""Exercise persistent editorial dates without touching the real site history."""
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import os
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from page_history import PageHistory


class PageHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.content = self.root / 'content'
        self.content.mkdir()
        (self.content / 'bn').mkdir()
        # 18:45 UTC is already the next calendar date in India.
        self.authored('history.html', '2026-09-30T18:45:00+00:00')
        self.authored('bn/history.html', '2026-09-28T12:00:00+00:00')

    def authored(self, name, timestamp, text='Original text'):
        path = self.content / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
        epoch = datetime.fromisoformat(timestamp).timestamp()
        os.utime(path, (epoch, epoch))
        return path

    def update(self, history, html='<p>Original text</p>', lang='en', key='history'):
        return history.updated(key, lang, 'Title', 'Description', html)

    def test_baseline_uses_localized_source_date_and_preserves_evidence(self):
        history = PageHistory(self.root)
        self.assertEqual(self.update(history), '2026-10-01')
        self.assertEqual(self.update(history, lang='bn'), '2026-09-28')
        history.save()
        baseline = json.loads(history.path.read_text())['pages']['en/history']['baseline']
        self.assertEqual(baseline['sources'][0]['path'], 'content/history.html')
        self.assertTrue(baseline['sources'][0]['modified'].endswith('+05:30'))

    def test_unchanged_build_keeps_date_and_does_not_rewrite_registry(self):
        history = PageHistory(self.root)
        self.update(history)
        history.save()
        before = (history.path.read_bytes(), history.path.stat().st_mtime_ns)
        # An unrelated rebuild, source touch and visual class edit are not a new edition.
        os.utime(self.content / 'history.html', None)
        with patch('page_history._today', return_value='2026-10-09'):
            rebuilt = PageHistory(self.root)
            self.assertEqual(self.update(rebuilt, '<p class="new-style"> Original  text </p>'),
                             '2026-10-01')
            rebuilt.save()
        self.assertEqual(before, (history.path.read_bytes(), history.path.stat().st_mtime_ns))

    def test_editorial_change_advances_only_changed_edition(self):
        history = PageHistory(self.root)
        self.update(history)
        self.update(history, lang='bn')
        history.save()
        with patch('page_history._today', return_value='2026-10-09'):
            rebuilt = PageHistory(self.root)
            self.assertEqual(self.update(rebuilt, '<p>Revised text</p>'), '2026-10-09')
            self.assertEqual(self.update(rebuilt, lang='bn'), '2026-09-28')
            rebuilt.save()
        self.assertEqual(rebuilt.data['pages']['en/history']['baseline']['date'], '2026-10-01')

    def test_generated_pages_use_their_authored_inputs(self):
        self.authored('people.html', '2026-09-25T12:00:00+00:00')
        self.authored('translations/example.json', '2026-09-13T12:00:00+00:00',
                      json.dumps({'slug': 'example'}))
        self.authored('bn/readings.json', '2026-09-15T12:00:00+00:00', '{}')
        history = PageHistory(self.root)
        self.assertEqual(self.update(history, key='person-example'), '2026-09-25')
        self.assertEqual(self.update(history, key='translation-example'), '2026-09-13')
        self.assertEqual(self.update(history, key='translation-example', lang='bn'), '2026-09-15')
        self.assertEqual(self.update(history, key='translations'), '2026-09-13')

    def test_corrected_source_link_counts_as_an_editorial_update(self):
        history = PageHistory(self.root)
        self.update(history, '<p>Text</p><a href="https://example.org/old">Source</a>')
        history.save()
        with patch('page_history._today', return_value='2026-10-09'):
            self.assertEqual(self.update(history,
                             '<p>Text</p><a href="https://example.org/corrected">Source</a>'),
                             '2026-10-09')

    def test_archive_reader_content_changes_count_but_touches_do_not(self):
        for name in ('archives.html', 'bn/archives.html'):
            self.authored(name, '2026-09-30T18:45:00+00:00')
        assets = self.root / 'assets'
        assets.mkdir()
        for name in ('reading-notes.js', 'reading-notes-bn.js', 'ocr-data.js',
                     'translation-links.js', 'translation-links-bn.js'):
            asset = assets / name
            asset.write_text('Original reader content', encoding='utf-8')
            epoch = datetime.fromisoformat('2026-09-30T18:45:00+00:00').timestamp()
            os.utime(asset, (epoch, epoch))
        history = PageHistory(self.root)
        self.assertEqual(self.update(history, key='archives'), '2026-10-01')
        self.assertEqual(self.update(history, key='archives', lang='bn'), '2026-10-01')
        history.save()
        before = (history.path.read_bytes(), history.path.stat().st_mtime_ns)
        notes = assets / 'reading-notes.js'
        os.utime(notes, None)
        with patch('page_history._today', return_value='2026-10-09'):
            rebuilt = PageHistory(self.root)
            self.assertEqual(self.update(rebuilt, key='archives'), '2026-10-01')
            rebuilt.save()
            self.assertEqual(before, (history.path.read_bytes(), history.path.stat().st_mtime_ns))
            notes.write_text('Corrected reader content', encoding='utf-8')
            self.assertEqual(self.update(rebuilt, key='archives'), '2026-10-09')
            self.assertEqual(self.update(rebuilt, key='archives', lang='bn'), '2026-10-01')
            rebuilt.save()
        self.assertEqual(PageHistory(self.root).data['pages']['en/archives']['updated'], '2026-10-09')

    def test_corrupt_registry_fails_clearly(self):
        history = PageHistory(self.root)
        self.update(history)
        history.save()
        data = json.loads(history.path.read_text())
        data['pages']['en/history']['updated'] = '2026-02-30'
        history.path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'Invalid page history'):
            PageHistory(self.root)


if __name__ == '__main__':
    unittest.main()
