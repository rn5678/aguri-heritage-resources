#!/usr/bin/env python3
"""Translation queue tests; only temporary metadata is written, never site content."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import editor_translation_state as state

SPEC = importlib.util.spec_from_file_location('translation_state_editor_fixture', Path(__file__).with_name('content_editor.py'))
editor = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = editor
SPEC.loader.exec_module(editor)


def snapshot(text):
    tree = editor.Tree(text)
    blocks = [node for node in tree.nodes if node.tag in {'h2', 'h3', 'p'}]
    return state.make_snapshot(text, blocks)


EN = '<div><h2 id="life">Life</h2><p>First life fact.[cite:one]</p><p>Second fact.[cite:two]</p><h2 id="work">Work</h2><p>Work story.[cite:three]</p></div>'
BN = '<div><h2 id="life">জীবন</h2><p>জীবনের প্রথম তথ্য।[cite:one]</p><p>দ্বিতীয় তথ্য।[cite:two]</p><h2 id="work">কর্ম</h2><p>কর্মের বিবরণ।[cite:three]</p></div>'


class PairingTests(unittest.TestCase):
    def test_initial_baseline_queues_nothing_and_has_stable_offsets(self):
        en, bn = snapshot(EN), snapshot(BN)
        initial = state.initialise(en, bn, 'test')
        self.assertTrue(initial['baseline_only'])
        self.assertEqual(len(initial['records']), 5)
        self.assertTrue(all(r['status'] == 'unchanged' for r in initial['records']))
        self.assertEqual(state.pending_jobs(initial), [])
        for record in initial['records']:
            self.assertEqual(record['baseline_en_html'], record['en']['html'])
            self.assertEqual(record['baseline_bn_html'], record['bn']['html'])
            self.assertEqual(EN[record['en']['opening']:record['en']['close']], record['en']['html'])
        self.assertEqual(en['version'], state.content_hash(EN))

    def test_differing_citation_order_prevents_repeated_paragraph_guessing(self):
        bn = BN.replace('[cite:one]', '[cite:swap]').replace('[cite:two]', '[cite:one]').replace('[cite:swap]', '[cite:two]')
        initial = state.initialise(snapshot(EN), snapshot(bn))
        life = [r for r in initial['records'] if r['en']['anchor'] == 'h2#life']
        self.assertEqual([r['status'] for r in life], ['unchanged', 'unpaired', 'unpaired'])
        self.assertEqual(initial['records'][-1]['status'], 'unchanged')

    def test_differing_group_counts_do_not_pair_paragraphs_by_position(self):
        en = EN.replace('[cite:one]', '').replace('[cite:two]', '')
        bn = BN.replace('<p>দ্বিতীয় তথ্য।[cite:two]</p>', '').replace('[cite:one]', '')
        initial = state.initialise(snapshot(en), snapshot(bn))
        first = next(r for r in initial['records'] if 'First life' in r['en']['html'])
        self.assertEqual(first['status'], 'unpaired')
        self.assertTrue(all(r['status'] == 'unpaired' for r in initial['records'] if r['en']['tag'] == 'p' and r['en']['anchor'] == 'h2#life'))
        self.assertTrue(all(r['pairing_evidence'] == 'shared_id' for r in initial['records'] if r['en']['tag'] == 'h2'))

    def test_later_anchored_section_survives_earlier_sibling_offset_change(self):
        bn = BN.replace('<p>দ্বিতীয় তথ্য।[cite:two]</p>', '')
        initial = state.initialise(snapshot(EN), snapshot(bn))
        work = next(r for r in initial['records'] if 'Work story' in r['en']['html'])
        self.assertEqual(work['status'], 'unchanged')
        self.assertEqual(work['pairing_evidence'], 'anchored_relative_structure')

    def test_unique_citations_match_divergent_section_without_filling_missing_blocks(self):
        bn = BN.replace('<p>দ্বিতীয় তথ্য।[cite:two]</p>', '')
        initial = state.initialise(snapshot(EN), snapshot(bn))
        first = next(r for r in initial['records'] if 'First life' in r['en']['html'])
        missing = next(r for r in initial['records'] if 'Second fact' in r['en']['html'])
        self.assertEqual(first['pairing_evidence'], 'unique_anchored_citations')
        self.assertEqual(missing['status'], 'unpaired')

    def test_repeated_citation_signatures_remain_ambiguous_when_counts_differ(self):
        en = EN.replace('[cite:two]', '[cite:one]')
        bn = BN.replace('<p>দ্বিতীয় তথ্য।[cite:two]</p>', '')
        initial = state.initialise(snapshot(en), snapshot(bn))
        life = [r for r in initial['records'] if r['en']['tag'] == 'p' and r['en']['anchor'] == 'h2#life']
        self.assertTrue(all(r['status'] == 'unpaired' for r in life))

    def test_unique_shared_id_can_pair_across_structure_difference(self):
        en = EN.replace('<p>First life', '<p id="first-fact">First life')
        bn = BN.replace('<p>জীবনের প্রথম', '<p id="first-fact">জীবনের প্রথম').replace('<h2 id="life">', '<p>অতিরিক্ত অনুচ্ছেদ।</p><h2 id="life">')
        initial = state.initialise(snapshot(en), snapshot(bn))
        first = next(r for r in initial['records'] if 'First life' in r['en']['html'])
        self.assertEqual(first['status'], 'unchanged')
        self.assertEqual(first['pairing_evidence'], 'shared_id')

    def test_duplicate_explicit_ids_do_not_provide_pairing_evidence(self):
        en = '<div><p id="same">One.[cite:one]</p><p id="same">Two.[cite:two]</p></div>'
        bn = '<div><p id="same">দুই।[cite:two]</p><p id="same">এক।[cite:one]</p></div>'
        initial = state.initialise(snapshot(en), snapshot(bn))
        self.assertTrue(all(r['status'] == 'unpaired' for r in initial['records']))


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.en, self.bn = snapshot(EN), snapshot(BN)
        self.initial = state.initialise(self.en, self.bn, 'example')
        self.changed_text = EN.replace('First life fact.', 'Revised first life fact with more detail.')
        self.changed = snapshot(self.changed_text)

    def test_only_changed_english_block_is_queued_despite_shifted_offsets(self):
        updated = state.refresh(self.initial, self.changed, self.bn)
        jobs = state.pending_jobs(updated)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]['previous_en_html'], 'First life fact.[cite:one]')
        self.assertEqual(jobs[0]['en_html'], 'Revised first life fact with more detail.[cite:one]')
        self.assertEqual([r['id'] for r in updated['records']], [r['id'] for r in self.initial['records']])
        self.assertEqual(updated['records'][-1]['status'], 'unchanged')
        self.assertNotEqual(updated['records'][-1]['en']['opening'], self.initial['records'][-1]['en']['opening'])
        self.assertEqual(state.pending_jobs(self.initial), [])

    def test_unpaired_changes_are_visible_but_unchanged_unpaired_blocks_do_not_queue(self):
        divergent = snapshot(BN.replace('[cite:one]', '[cite:other]'))
        initial = state.initialise(self.en, divergent)
        self.assertEqual(state.pending_jobs(initial), [])
        updated = state.refresh(initial, self.changed, divergent)
        changed = next(r for r in updated['records'] if 'Revised first' in r['en']['html'])
        self.assertEqual(changed['status'], 'needs_pairing')
        self.assertEqual(state.pending_jobs(updated), [])
        self.assertEqual(next(r for r in updated['records'] if 'Second fact' in r['en']['html'])['status'], 'unchanged')

    def test_manual_bengali_edit_is_adopted_without_translation(self):
        manual = snapshot(BN.replace('জীবনের প্রথম তথ্য।', 'সম্পাদিত বাংলা তথ্য।'))
        updated = state.refresh(self.initial, self.en, manual)
        self.assertEqual(state.pending_jobs(updated), [])
        target = next(r for r in updated['records'] if 'First life' in r['en']['html'])
        self.assertTrue(target['manual_bengali'])
        self.assertEqual(target['baseline_bn_html'], 'সম্পাদিত বাংলা তথ্য।[cite:one]')
        later = state.refresh(updated, self.changed, manual)
        self.assertEqual(state.pending_jobs(later)[0]['previous_bn_html'], 'সম্পাদিত বাংলা তথ্য।[cite:one]')

    def test_manual_bengali_edit_during_pending_english_change_is_conflict(self):
        pending = state.refresh(self.initial, self.changed, self.bn)
        manual = snapshot(BN.replace('জীবনের প্রথম তথ্য।', 'সম্পাদিত বাংলা তথ্য।'))
        conflicted = state.refresh(pending, self.changed, manual)
        self.assertEqual(state.pending_jobs(conflicted), [])
        target = next(r for r in conflicted['records'] if 'Revised first' in r['en']['html'])
        self.assertEqual(target['status'], 'conflict')
        self.assertEqual(target['baseline_bn_html'], 'জীবনের প্রথম তথ্য।[cite:one]')

    def test_reverting_english_cancels_pending_change(self):
        pending = state.refresh(self.initial, self.changed, self.bn)
        reverted = state.refresh(pending, self.en, self.bn)
        self.assertEqual(state.pending_jobs(reverted), [])
        self.assertTrue(all(r['status'] == 'unchanged' for r in reverted['records']))

    def test_outer_structure_change_surfaces_conflict_instead_of_wrong_target(self):
        inserted = snapshot(EN.replace('<p>First life', '<p>Inserted paragraph.</p><p>First life'))
        updated = state.refresh(self.initial, inserted, self.bn)
        self.assertEqual(state.pending_jobs(updated), [])
        self.assertTrue(any(r['status'] == 'conflict' for r in updated['records']))
        self.assertTrue(any(r['status'] == 'needs_pairing' for r in updated['records']))

    def test_stale_full_file_or_block_versions_reject_translation(self):
        pending = state.refresh(self.initial, self.changed, self.bn)
        job = state.pending_jobs(pending)[0]
        state.validate_job(job, self.changed, self.bn)
        for en, bn in ((snapshot(self.changed_text+'\n'), self.bn), (self.changed, snapshot(BN+'\n'))):
            with self.subTest(en=en['version'], bn=bn['version']), self.assertRaises(state.StateConflict):
                state.validate_job(job, en, bn)
        altered = deepcopy(self.changed)
        altered['blocks'][1]['hash'] = state.content_hash('different')
        with self.assertRaises(state.StateConflict):
            state.validate_job(job, altered, self.bn)

    def test_successful_saved_result_advances_baseline_once(self):
        pending = state.refresh(self.initial, self.changed, self.bn)
        job = state.pending_jobs(pending)[0]
        translation = 'নতুন অনুবাদ।[cite:one]'
        translated = snapshot(BN.replace('জীবনের প্রথম তথ্য।[cite:one]', translation))
        accepted = state.accept_job(pending, job, self.changed, translated, translation)
        self.assertEqual(state.pending_jobs(accepted), [])
        target = next(r for r in accepted['records'] if r['id'] == job['id'])
        self.assertEqual(target['baseline_bn_html'], translation)
        self.assertEqual(target['baseline_en_html'], job['en_html'])
        self.assertFalse(accepted['baseline_only'])
        with self.assertRaises(state.StateConflict):
            state.accept_job(accepted, job, self.changed, translated, translation)
        with self.assertRaises(state.StateConflict):
            state.accept_job(pending, job, self.changed, translated, 'Unexpected result')

    def test_metadata_persistence_preserves_pending_pairs_and_baseline_text(self):
        pending = state.refresh(self.initial, self.changed, self.bn)
        with tempfile.TemporaryDirectory(prefix='translation-state-test-') as temporary:
            path = Path(temporary)/'metadata/state.json'
            self.assertIsNone(state.load_state(path))
            state.store_state(path, pending)
            loaded = state.load_state(path)
            refreshed = state.refresh(loaded, self.changed, self.bn)
            self.assertEqual(state.pending_jobs(refreshed), state.pending_jobs(pending))
            self.assertEqual(len(list(path.parent.iterdir())), 1)
            path.write_text('{"schema":99,"records":[]}', encoding='utf-8')
            with self.assertRaises(state.StateConflict):
                state.load_state(path)


class StructuralRebaseTests(unittest.TestCase):
    @staticmethod
    def key_map(before, after, indexes):
        return {block['key']: after['blocks'][new_index]['key']
                for block, new_index in zip(before['blocks'], indexes) if new_index is not None}

    def setUp(self):
        self.en, self.bn = snapshot(EN), snapshot(BN)
        self.initial = state.initialise(self.en, self.bn, 'structural-example')

    def insert(self, initial=None, before_en=None, before_bn=None):
        before_en, before_bn = before_en or self.en, before_bn or self.bn
        english_text = EN.replace('<p>Second fact.', '<p data-editor-block="new-1">A newly added fact.</p><p>Second fact.')
        bengali_text = BN.replace('<p>দ্বিতীয় তথ্য।', '<p data-editor-block="new-1"></p><p>দ্বিতীয় তথ্য।')
        if before_en['blocks'][1]['html'] != self.en['blocks'][1]['html']:
            english_text = english_text.replace(self.en['blocks'][1]['html'], before_en['blocks'][1]['html'])
        if before_bn['blocks'][1]['html'] != self.bn['blocks'][1]['html']:
            bengali_text = bengali_text.replace(self.bn['blocks'][1]['html'], before_bn['blocks'][1]['html'])
        after_en, after_bn = snapshot(english_text), snapshot(bengali_text)
        rebased = state.rebase_structure(initial or self.initial, before_en, before_bn, after_en, after_bn,
                                         self.key_map(before_en, after_en, [0, 1, 3, 4, 5]),
                                         self.key_map(before_bn, after_bn, [0, 1, 3, 4, 5]),
                                         new_pairs=[{'en_key': after_en['blocks'][2]['key'], 'bn_key': after_bn['blocks'][2]['key']}])
        return rebased, after_en, after_bn

    def test_paired_insertion_preserves_survivors_and_queues_only_new_text(self):
        rebased, after_en, after_bn = self.insert()
        originals = {record['id']: record for record in self.initial['records']}
        for record in rebased['records']:
            if record['id'] in originals:
                self.assertEqual(record['baseline_en_html'], originals[record['id']]['baseline_en_html'])
                self.assertEqual(record['baseline_bn_hash'], originals[record['id']]['baseline_bn_hash'])
                self.assertEqual(record['status'], 'unchanged')
        jobs = state.pending_jobs(rebased)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]['en_html'], 'A newly added fact.')
        self.assertEqual(jobs[0]['bn_html'], '')
        self.assertEqual(jobs[0]['previous_en_html'], '')
        self.assertEqual(jobs[0]['previous_bn_html'], '')
        state.validate_job(jobs[0], after_en, after_bn)
        self.assertEqual(len(state.refresh(rebased, after_en, after_bn)['records']), 6)
        self.assertEqual(len(self.initial['records']), 5)

    def test_existing_pending_change_and_manual_baseline_survive_insertion(self):
        manual = snapshot(BN.replace('জীবনের প্রথম তথ্য।', 'মানুষের সম্পাদিত তথ্য।'))
        adopted = state.refresh(self.initial, self.en, manual)
        changed = snapshot(EN.replace('First life fact.', 'Changed English fact.'))
        pending = state.refresh(adopted, changed, manual)
        rebased, _, _ = self.insert(pending, changed, manual)
        jobs = state.pending_jobs(rebased)
        self.assertEqual(len(jobs), 2)
        existing = next(job for job in jobs if 'Changed English' in job['en_html'])
        self.assertEqual(existing['previous_en_html'], 'First life fact.[cite:one]')
        self.assertEqual(existing['previous_bn_html'], 'মানুষের সম্পাদিত তথ্য।[cite:one]')

    def test_paired_deletion_removes_pair_without_reclassifying_following_blocks(self):
        after_en = snapshot(EN.replace('<p>First life fact.[cite:one]</p>', ''))
        after_bn = snapshot(BN.replace('<p>জীবনের প্রথম তথ্য।[cite:one]</p>', ''))
        deleted_key = self.en['blocks'][1]['key']
        rebased = state.rebase_structure(self.initial, self.en, self.bn, after_en, after_bn,
                                         self.key_map(self.en, after_en, [0, None, 1, 2, 3]),
                                         self.key_map(self.bn, after_bn, [0, None, 1, 2, 3]),
                                         deleted_en_keys=[deleted_key])
        removed_id = self.initial['records'][1]['id']
        self.assertNotIn(removed_id, [r['id'] for r in rebased['records']])
        self.assertEqual(len(rebased['records']), 4)
        self.assertTrue(all(r['status'] == 'unchanged' for r in rebased['records']))
        self.assertEqual(state.pending_jobs(rebased), [])

    def test_unpaired_english_deletion_leaves_persistent_review_tombstone(self):
        divergent_bn = snapshot(BN.replace('[cite:one]', '[cite:other]'))
        initial = state.initialise(self.en, divergent_bn)
        after_en = snapshot(EN.replace('<p>First life fact.[cite:one]</p>', ''))
        rebased = state.rebase_structure(initial, self.en, divergent_bn, after_en, divergent_bn,
                                         self.key_map(self.en, after_en, [0, None, 1, 2, 3]),
                                         self.key_map(divergent_bn, divergent_bn, [0, 1, 2, 3, 4]),
                                         deleted_en_keys=[self.en['blocks'][1]['key']])
        tombstone = next(r for r in rebased['records'] if r.get('tombstone'))
        self.assertEqual(tombstone['status'], 'needs_pairing')
        self.assertIsNone(tombstone['en_key'])
        self.assertEqual(tombstone['deleted_en_html'], 'First life fact.[cite:one]')
        with tempfile.TemporaryDirectory(prefix='translation-tombstone-test-') as temporary:
            path = Path(temporary)/'state.json'
            state.store_state(path, rebased)
            refreshed = state.refresh(state.load_state(path), after_en, divergent_bn)
            self.assertEqual(next(r for r in refreshed['records'] if r.get('tombstone'))['status'], 'needs_pairing')
            self.assertEqual(state.pending_jobs(refreshed), [])

    def test_deleted_english_with_surviving_bengali_is_not_silently_dropped(self):
        after_en = snapshot(EN.replace('<p>First life fact.[cite:one]</p>', ''))
        rebased = state.rebase_structure(self.initial, self.en, self.bn, after_en, self.bn,
                                         self.key_map(self.en, after_en, [0, None, 1, 2, 3]),
                                         self.key_map(self.bn, self.bn, [0, 1, 2, 3, 4]),
                                         deleted_en_keys=[self.en['blocks'][1]['key']])
        tombstone = next(r for r in rebased['records'] if r.get('tombstone'))
        self.assertEqual(tombstone['bn']['html'], 'জীবনের প্রথম তথ্য।[cite:one]')
        self.assertEqual(tombstone['status'], 'needs_pairing')

    def test_manual_bengali_deletion_is_respected_until_english_changes(self):
        after_bn = snapshot(BN.replace('<p>জীবনের প্রথম তথ্য।[cite:one]</p>', ''))
        rebased = state.rebase_structure(self.initial, self.en, self.bn, self.en, after_bn,
                                         self.key_map(self.en, self.en, [0, 1, 2, 3, 4]),
                                         self.key_map(self.bn, after_bn, [0, None, 1, 2, 3]))
        target = next(r for r in rebased['records'] if r['id'] == self.initial['records'][1]['id'])
        self.assertEqual(target['status'], 'unpaired')
        self.assertIsNone(target['bn_key'])
        self.assertEqual(state.pending_jobs(rebased), [])
        changed = snapshot(EN.replace('First life fact.', 'Later English edit.'))
        refreshed = state.refresh(rebased, changed, after_bn)
        self.assertEqual(next(r for r in refreshed['records'] if r['id'] == target['id'])['status'], 'needs_pairing')

    def test_manual_bengali_deletion_while_english_pending_requires_review(self):
        changed = snapshot(EN.replace('First life fact.', 'Pending English edit.'))
        pending = state.refresh(self.initial, changed, self.bn)
        after_bn = snapshot(BN.replace('<p>জীবনের প্রথম তথ্য।[cite:one]</p>', ''))
        rebased = state.rebase_structure(pending, changed, self.bn, changed, after_bn,
                                         self.key_map(changed, changed, [0, 1, 2, 3, 4]),
                                         self.key_map(self.bn, after_bn, [0, None, 1, 2, 3]))
        target = next(r for r in rebased['records'] if r['id'] == self.initial['records'][1]['id'])
        self.assertEqual(target['status'], 'conflict')
        self.assertTrue(target['review_required'])
        self.assertEqual(state.pending_jobs(state.refresh(rebased, changed, after_bn)), [])

    def test_preexisting_conflict_stays_sticky_through_structural_edit(self):
        changed = snapshot(EN.replace('First life fact.', 'Changed English fact.'))
        manual = snapshot(BN.replace('জীবনের প্রথম তথ্য।', 'স্বাধীন বাংলা সম্পাদনা।'))
        conflicted = state.refresh(self.initial, changed, manual)
        rebased, after_en, after_bn = self.insert(conflicted, changed, manual)
        target_id = self.initial['records'][1]['id']
        target = next(r for r in rebased['records'] if r['id'] == target_id)
        self.assertEqual(target['status'], 'conflict')
        self.assertTrue(target['review_required'])
        refreshed = state.refresh(rebased, after_en, after_bn)
        self.assertEqual(next(r for r in refreshed['records'] if r['id'] == target_id)['status'], 'conflict')

    def test_unpaired_new_english_needs_review_and_new_bengali_alone_does_not_queue(self):
        after_en = snapshot(EN.replace('<p>Second fact.', '<p>New unmatched English.</p><p>Second fact.'))
        rebased = state.rebase_structure(self.initial, self.en, self.bn, after_en, self.bn,
                                         self.key_map(self.en, after_en, [0, 1, 3, 4, 5]),
                                         self.key_map(self.bn, self.bn, [0, 1, 2, 3, 4]),
                                         new_pairs=[{'en_key': after_en['blocks'][2]['key'], 'bn_key': None}])
        self.assertEqual(next(r for r in rebased['records'] if r['en']['html'] == 'New unmatched English.')['status'], 'needs_pairing')
        after_bn = snapshot(BN.replace('<p>দ্বিতীয় তথ্য।', '<p>নতুন বাংলা অনুচ্ছেদ।</p><p>দ্বিতীয় তথ্য।'))
        bn_only = state.rebase_structure(self.initial, self.en, self.bn, self.en, after_bn,
                                         self.key_map(self.en, self.en, [0, 1, 2, 3, 4]),
                                         self.key_map(self.bn, after_bn, [0, 1, 3, 4, 5]))
        self.assertEqual(len(bn_only['records']), 5)
        self.assertTrue(all(r['status'] == 'unchanged' for r in bn_only['records']))

    def test_ambiguous_or_incomplete_maps_are_rejected(self):
        en_map = self.key_map(self.en, self.en, [0, 1, 2, 3, 4])
        bn_map = self.key_map(self.bn, self.bn, [0, 1, 2, 3, 4])
        for invalid in ({}, {**en_map, self.en['blocks'][2]['key']: self.en['blocks'][1]['key']},
                        {**en_map, self.en['blocks'][1]['key']: self.en['blocks'][0]['key']}):
            with self.subTest(mapping=invalid), self.assertRaises(state.StateConflict):
                state.rebase_structure(self.initial, self.en, self.bn, self.en, self.bn, invalid, bn_map)
        with self.assertRaises(state.StateConflict):
            state.rebase_structure(self.initial, self.en, self.bn, self.en, self.bn, en_map, bn_map,
                                   deleted_en_keys=[self.en['blocks'][1]['key']])


if __name__ == '__main__':
    unittest.main()
