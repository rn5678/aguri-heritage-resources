"""Conservative, local EN/BN paragraph pairing and incremental translation queue.

No translation service is called here and no authored HTML is modified. A first
snapshot records the existing bilingual baseline; it does not certify that the
two editions are accurate translations. State is one JSON object per document.

The editor changes block interiors, leaving outer structure intact. A pair is
therefore retained only while its anchored structural group remains intact.
Initial pairing requires a shared unique explicit ID, an anchored group with
matching relative child structure/tags/citations, or unique nonempty citation
signatures within the same anchor whose proposed matches do not cross. Ambiguous
groups remain visible as unpaired; their later English changes need review.

Integration: make_snapshot on both editions, initialise once, then refresh
before and after editor saves. Persist with store_state under the caller's edit
lock. pending_jobs contains only safe changed pairs plus their baseline text.
Call validate_job with fresh snapshots immediately before applying a result.
After source saving AND site checks succeed, call accept_job with the exact
sanitized translated HTML and fresh snapshots, then persist the returned state.
Do not refresh the just-written Bengali draft before accepting its queued job:
that would correctly treat the independent Bengali change as a conflict.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import uuid

SCHEMA = 1
CITATION = re.compile(r'\[cite:([\w-]+)\]')


class StateConflict(ValueError):
    """The saved pairing or a queued job no longer matches the source files."""


def content_hash(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def _digest(value):
    return content_hash(json.dumps(value, ensure_ascii=False, sort_keys=True))


def make_snapshot(text, nodes, version=None):
    """Snapshot original HTML blocks from content_editor.authored() Node objects.

    ``version`` is the source file version used by the editor; when omitted it
    is the SHA-256 of the entire source text. Character offsets are informational
    and may move. ``key`` is a structural path, never a character offset.
    """
    nodes = sorted(nodes, key=lambda node: node.start)
    roots = {}
    for node in nodes:
        root = node
        while root.parent is not None:
            root = root.parent
        roots[id(root)] = root
    root_order = {id(node): index for index, node in enumerate(sorted(roots.values(), key=lambda node: node.start))}

    def location(node):
        parts = []
        current = node
        while current.parent is not None:
            position = next(i for i, child in enumerate(current.parent.children) if child is current)
            parts.append(f'{current.tag}:{position}')
            current = current.parent
        parts.append(f'{current.tag}:root{root_order[id(current)]}')
        return '/'.join(reversed(parts))

    headings = {}
    heading_counts = Counter()
    blocks = []
    for node in nodes:
        if re.fullmatch(r'h[1-6]', node.tag):
            level = int(node.tag[1])
            headings = {key: value for key, value in headings.items() if key < level}
            heading_counts[level] += 1
            headings[level] = (f'{node.tag}#{node.attrs["id"]}' if node.attrs.get('id')
                               else f'{node.tag}@{heading_counts[level]}')
        anchor = '/'.join(headings[level] for level in sorted(headings)) or 'preamble'
        html = text[node.opening:node.close]
        blocks.append({'key': location(node), 'tag': node.tag, 'anchor': anchor,
                       'explicit_id': node.attrs.get('id'), 'html': html,
                       'hash': content_hash(html),
                       'citations': sorted(Counter(CITATION.findall(html)).items()),
                       'start': node.start, 'opening': node.opening,
                       'close': node.close, 'end': node.end})
    groups = defaultdict(list)
    for block in blocks:
        groups[block['anchor']].append((block['key'], block['tag']))
    return {'version': version or content_hash(text), 'blocks': blocks,
            'structure': _digest([(b['key'], b['tag'], b['anchor']) for b in blocks]),
            'groups': {key: _digest(shape) for key, shape in groups.items()}}


def _index(snapshot):
    blocks = snapshot['blocks']
    result = {block['key']: block for block in blocks}
    if len(result) != len(blocks):
        raise StateConflict('Duplicate structural block keys in this document.')
    return result


def _pair_blocks(en, bn):
    """Return pairs keyed by English structural location, with evidence labels."""
    pairs = {}
    used_bn = set()
    en_ids = defaultdict(list)
    bn_ids = defaultdict(list)
    for block in en['blocks']:
        if block.get('explicit_id'):
            en_ids[block['explicit_id']].append(block)
    for block in bn['blocks']:
        if block.get('explicit_id'):
            bn_ids[block['explicit_id']].append(block)
    for identity, english in en_ids.items():
        bengali = bn_ids.get(identity, [])
        if len(english) == len(bengali) == 1:
            left, right = english[0], bengali[0]
            if left['tag'] == right['tag'] and left['citations'] == right['citations']:
                pairs[left['key']] = (right, 'shared_id')
                used_bn.add(right['key'])

    en_groups = defaultdict(list)
    bn_groups = defaultdict(list)
    for block in en['blocks']:
        en_groups[block['anchor']].append(block)
    for block in bn['blocks']:
        bn_groups[block['anchor']].append(block)
    signature = lambda blocks: [(b['key'], b['tag'], b['explicit_id'], b['citations']) for b in blocks]
    for anchor, english in en_groups.items():
        bengali = bn_groups.get(anchor, [])
        same_absolute = signature(english) == signature(bengali)
        # An extra paragraph in an earlier section shifts later child indexes.
        # A shared anchored section with the same complete relative shape and
        # citations can still be paired without treating its old offset as ID.
        same_relative = ('#' in anchor and bengali and
                         _relative_signature(english) == _relative_signature(bengali))
        if same_absolute or same_relative:
            for left, right in zip(english, bengali):
                if left['key'] not in pairs and right['key'] not in used_bn:
                    evidence = 'structure_and_citations' if same_absolute else 'anchored_relative_structure'
                    pairs[left['key']] = (right, evidence)
                    used_bn.add(right['key'])
            continue
        if '#' not in anchor:
            continue
        # In a divergent section, only unique nonempty citation signatures
        # offer additional evidence. Repeated-source paragraphs remain unpaired.
        en_cites, bn_cites = defaultdict(list), defaultdict(list)
        cite_key = lambda block: (block['tag'], tuple(tuple(item) for item in block['citations']))
        for block in english:
            if block['citations']:
                en_cites[cite_key(block)].append(block)
        for block in bengali:
            if block['citations']:
                bn_cites[cite_key(block)].append(block)
        candidates = []
        for citation, lefts in en_cites.items():
            rights = bn_cites.get(citation, [])
            if len(lefts) == len(rights) == 1:
                left, right = lefts[0], rights[0]
                if (left['key'] not in pairs and right['key'] not in used_bn and
                        not (left['explicit_id'] and right['explicit_id'] and left['explicit_id'] != right['explicit_id'])):
                    candidates.append((left, right))
        en_order = {block['key']: index for index, block in enumerate(english)}
        bn_order = {block['key']: index for index, block in enumerate(bengali)}
        proposed = [(en_order[left['key']], bn_order[right['key']]) for left, right in candidates]
        proposed += [(en_order[key], bn_order[right['key']]) for key, (right, _) in pairs.items()
                     if key in en_order and right['key'] in bn_order]
        ordered = sorted(proposed)
        if any(left[1] >= right[1] for left, right in zip(ordered, ordered[1:])):
            continue
        for left, right in candidates:
            pairs[left['key']] = (right, 'unique_anchored_citations')
            used_bn.add(right['key'])
    return pairs


def _relative_signature(blocks):
    """Keep child/tag shape, normalising only the first shared sibling offset."""
    if not blocks:
        return []
    paths = [block['key'].split('/') for block in blocks]
    common = 0
    while all(len(path) > common for path in paths) and len({path[common] for path in paths}) == 1:
        common += 1
    tails = [path[common:] for path in paths]
    indexes = [int(tail[0].rsplit(':', 1)[1]) for tail in tails
               if tail and re.fullmatch(r'[^:]+:\d+', tail[0])]
    offset = min(indexes) if indexes else 0
    result = []
    for block, tail in zip(blocks, tails):
        if tail and re.fullmatch(r'[^:]+:\d+', tail[0]):
            tag, index = tail[0].rsplit(':', 1)
            tail = [f'{tag}:{int(index)-offset}', *tail[1:]]
        result.append((tail, block['tag'], block['explicit_id'], block['citations']))
    return result


def _record(english, bengali, en, bn, evidence=None, baseline=True):
    return {'id': str(uuid.uuid4()), 'en_key': english['key'],
            'bn_key': bengali['key'] if bengali else None,
            'baseline_en_hash': english['hash'] if baseline else None,
            'baseline_bn_hash': bengali['hash'] if bengali else None,
            'baseline_en_html': english['html'] if baseline else None,
            'baseline_bn_html': bengali['html'] if bengali else None,
            'en_anchor': english['anchor'], 'bn_anchor': bengali['anchor'] if bengali else None,
            'en_group_shape': en['groups'][english['anchor']],
            'bn_group_shape': bn['groups'][bengali['anchor']] if bengali else None,
            'pairing_evidence': evidence, 'manual_bengali': False,
            'en': deepcopy(english), 'bn': deepcopy(bengali),
            'status': ('unchanged' if bengali else 'unpaired') if baseline else 'needs_pairing',
            'reason': None if bengali else 'No unambiguous Bengali block match.'}


def initialise(en, bn, document_id=''):
    """Record all existing English blocks, including those that cannot be paired."""
    _index(en)
    _index(bn)
    pairs = _pair_blocks(en, bn)
    records = []
    for english in en['blocks']:
        bengali, evidence = pairs.get(english['key'], (None, None))
        records.append(_record(english, bengali, en, bn, evidence))
    return {'schema': SCHEMA, 'document_id': document_id, 'baseline_only': True,
            'en_version': en['version'], 'bn_version': bn['version'], 'records': records}


def refresh(state, en, bn):
    """Return updated queue state without modifying the supplied state or files.

    Bengali-only edits are adopted as the new Bengali baseline. If English is
    already changed as well, a Bengali change becomes a conflict: it is never
    overwritten automatically. New/ambiguous English changes remain visible.
    """
    if state.get('schema') != SCHEMA:
        raise StateConflict('Unsupported translation state version.')
    result = deepcopy(state)
    current_en, current_bn = _index(en), _index(bn)
    known = set()
    for record in result['records']:
        if record.get('tombstone'):
            # An approved English deletion without a safely deleted Bengali
            # counterpart remains a review item across saves and restarts.
            record['en'] = None
            record['bn'] = deepcopy(current_bn.get(record.get('bn_key')))
            continue
        key = record['en_key']
        known.add(key)
        english = current_en.get(key)
        bengali = current_bn.get(record['bn_key']) if record['bn_key'] else None
        record['en'], record['bn'] = deepcopy(english), deepcopy(bengali)
        if record.get('review_required'):
            record['status'] = 'conflict'
            continue
        if (english is None or english['anchor'] != record['en_anchor'] or
                en['groups'].get(record['en_anchor']) != record['en_group_shape']):
            record['status'], record['reason'] = 'conflict', 'English block structure changed; its pairing needs review.'
            continue
        changed = english['hash'] != record['baseline_en_hash']
        if record['bn_key'] is None:
            record['status'] = 'needs_pairing' if changed else 'unpaired'
            record['reason'] = 'This changed English block needs a Bengali match.' if changed else 'No unambiguous Bengali block match.'
            continue
        if (bengali is None or bengali['anchor'] != record['bn_anchor'] or
                bn['groups'].get(record['bn_anchor']) != record['bn_group_shape']):
            record['status'], record['reason'] = 'conflict', 'Bengali block structure changed; its pairing needs review.'
            continue
        bengali_changed = bengali['hash'] != record['baseline_bn_hash']
        if changed and bengali_changed:
            record['status'], record['reason'] = 'conflict', 'English and Bengali both changed; keep the Bengali edit for review.'
        elif changed:
            record['status'], record['reason'] = 'pending', None
        else:
            if bengali_changed:
                record['baseline_bn_hash'] = bengali['hash']
                record['baseline_bn_html'] = bengali['html']
                record['manual_bengali'] = True
            record['status'], record['reason'] = 'unchanged', None
    for key, english in current_en.items():
        if key not in known:
            result['records'].append(_record(english, None, en, bn, baseline=False))
    result['en_version'], result['bn_version'] = en['version'], bn['version']
    return result


def rebase_structure(state, before_en, before_bn, after_en, after_bn,
                     en_key_map, bn_key_map, deleted_en_keys=None, new_pairs=None):
    """Rebase exact identities after an approved paragraph addition/deletion.

    The caller holds the edit lock and supplies proven old-key -> new-key maps
    from its own source patches. This helper never infers identities by position.
    Every surviving old English block must be mapped; every new English block
    must appear in ``new_pairs`` as ``{'en_key': ..., 'bn_key': ... or None}``.
    Maps must be one-to-one. A paired new Bengali block must be an empty
    placeholder. Bengali blocks not mapped are considered explicitly removed.

    Survivors retain UUIDs and baselines even when later structural paths move.
    Pre-existing conflicts remain sticky until the caller's explicit review.
    A paired English + Bengali deletion removes the pair. Any English deletion
    lacking a proven Bengali removal leaves a persistent review tombstone.
    The returned state can be persisted only after source/build checks succeed.
    """
    old_en, old_bn = _index(before_en), _index(before_bn)
    new_en, new_bn = _index(after_en), _index(after_bn)
    deleted = set(deleted_en_keys or [])
    additions = list(new_pairs or [])
    if not isinstance(en_key_map, dict) or not isinstance(bn_key_map, dict):
        raise StateConflict('Structural edits need explicit English and Bengali identity maps.')
    if not deleted.issubset(old_en) or deleted.intersection(en_key_map):
        raise StateConflict('An English deletion conflicts with the surviving identity map.')

    def check_map(mapping, before, after, language):
        if (set(mapping) - set(before) or set(mapping.values()) - set(after) or
                len(set(mapping.values())) != len(mapping)):
            raise StateConflict(f'The {language} structural identity map is incomplete or ambiguous.')
        for old_key, new_key in mapping.items():
            previous, current = before[old_key], after[new_key]
            if (previous['tag'] != current['tag'] or
                    previous.get('explicit_id') != current.get('explicit_id')):
                raise StateConflict(f'The {language} structural identity map changes a block identity.')

    check_map(en_key_map, old_en, new_en, 'English')
    check_map(bn_key_map, old_bn, new_bn, 'Bengali')
    if set(en_key_map) != set(old_en) - deleted:
        raise StateConflict('Map every surviving English block and explicitly identify each deletion.')
    added_en, added_bn = set(), set()
    for addition in additions:
        if not isinstance(addition, dict) or set(addition) != {'en_key', 'bn_key'}:
            raise StateConflict('Each new paragraph needs an English key and an optional Bengali key.')
        en_key, bn_key = addition['en_key'], addition['bn_key']
        if en_key not in new_en or en_key in en_key_map.values() or en_key in added_en:
            raise StateConflict('A new English paragraph overlaps an existing or duplicate identity.')
        added_en.add(en_key)
        if bn_key is not None:
            if bn_key not in new_bn or bn_key in bn_key_map.values() or bn_key in added_bn:
                raise StateConflict('A new Bengali paragraph overlaps an existing or duplicate identity.')
            if new_en[en_key]['tag'] != new_bn[bn_key]['tag'] or new_bn[bn_key]['html'] != '':
                raise StateConflict('A new paired Bengali paragraph must be an empty matching placeholder.')
            added_bn.add(bn_key)
    if (set(en_key_map.values()) | added_en) != set(new_en):
        raise StateConflict('Identify every newly added English block explicitly.')

    base = refresh(state, before_en, before_bn)
    prior_conflicts = {r['id']: r.get('reason') for r in state['records'] if r['status'] == 'conflict'}
    result = deepcopy(base)
    result['records'] = []

    def update_target(record, english, bengali):
        record['en'], record['bn'] = deepcopy(english), deepcopy(bengali)
        if english:
            record['en_key'], record['en_anchor'] = english['key'], english['anchor']
            record['en_group_shape'] = after_en['groups'][english['anchor']]
        if bengali:
            record['bn_key'], record['bn_anchor'] = bengali['key'], bengali['anchor']
            record['bn_group_shape'] = after_bn['groups'][bengali['anchor']]

    for record in result_from_base(base):
        if record.get('tombstone'):
            old_target = record.get('bn_key')
            record['bn_key'] = bn_key_map.get(old_target) if old_target else None
            update_target(record, None, new_bn.get(record['bn_key']))
            result['records'].append(record)
            continue
        old_key, old_target = record['en_key'], record['bn_key']
        was_conflict = record['status'] == 'conflict' or record['id'] in prior_conflicts
        if old_key in deleted:
            if old_target is not None and old_target in old_bn and old_target not in bn_key_map:
                continue
            record.update(tombstone=True, en_key=None, en=None, deleted_en_key=old_key,
                          deleted_en_html=old_en[old_key]['html'], status='needs_pairing',
                          reason='An English paragraph was deleted. Review its Bengali counterpart manually.')
            record['bn_key'] = bn_key_map.get(old_target) if old_target else None
            update_target(record, None, new_bn.get(record['bn_key']))
            result['records'].append(record)
            continue
        if old_key not in en_key_map:
            # An already orphaned state record is never silently dropped by an
            # unrelated approved edit; the user must review it explicitly.
            record.update(tombstone=True, en_key=None, en=None, deleted_en_key=old_key,
                          status='conflict', reason=record.get('reason') or 'A previous structural conflict still needs review.')
            result['records'].append(record)
            continue
        english = new_en[en_key_map[old_key]]
        bengali = new_bn.get(bn_key_map.get(old_target)) if old_target else None
        if old_target and bengali is None:
            record['bn_key'] = None
            if record['status'] in ('pending', 'conflict') or english['hash'] != record['baseline_en_hash']:
                record['review_required'] = True
                record['reason'] = 'A paired Bengali paragraph was removed while English had changes; review it manually.'
            else:
                # Manual Bengali structural edits do not undo the English
                # author's work or reinsert the deliberately removed paragraph.
                record.update(baseline_bn_html=None, baseline_bn_hash=None,
                              bn_anchor=None, bn_group_shape=None,
                              pairing_evidence='manual_bengali_deletion')
        if was_conflict:
            record['review_required'] = True
            record['reason'] = prior_conflicts.get(record['id']) or record.get('reason') or 'A previous change still needs review.'
        update_target(record, english, bengali)
        result['records'].append(record)
    for addition in additions:
        english = new_en[addition['en_key']]
        bengali = new_bn.get(addition['bn_key']) if addition['bn_key'] else None
        record = _record(english, bengali, after_en, after_bn, 'approved_structural_edit', baseline=False)
        record.update(baseline_en_html='', baseline_en_hash=content_hash(''))
        if bengali:
            record.update(baseline_bn_html='', baseline_bn_hash=content_hash(''))
        result['records'].append(record)
    result['en_version'], result['bn_version'] = after_en['version'], after_bn['version']
    return refresh(result, after_en, after_bn)


def result_from_base(base):
    """Yield detached records so structural rebasing never mutates its input."""
    return (deepcopy(record) for record in base['records'])


def pending_jobs(state):
    """Return only safely paired changed English blocks, not unchanged content."""
    return [{'id': record['id'], 'document_id': state['document_id'],
             'en_key': record['en_key'], 'bn_key': record['bn_key'],
             'en_hash': record['en']['hash'], 'bn_hash': record['bn']['hash'],
             'en_html': record['en']['html'], 'bn_html': record['bn']['html'],
             'previous_en_html': record['baseline_en_html'],
             'previous_bn_html': record['baseline_bn_html'],
             'en_version': state['en_version'], 'bn_version': state['bn_version']}
            for record in state['records'] if record['status'] == 'pending']


def validate_job(job, en, bn):
    """Call immediately before applying a result; any source-file drift rejects it."""
    if en['version'] != job['en_version'] or bn['version'] != job['bn_version']:
        raise StateConflict('A source file changed after this translation was queued.')
    english = _index(en).get(job['en_key'])
    bengali = _index(bn).get(job['bn_key'])
    if (english is None or bengali is None or english['hash'] != job['en_hash']
            or bengali['hash'] != job['bn_hash']):
        raise StateConflict('A queued translation block changed or is missing.')
    return english, bengali


def accept_job(state, job, en, bn, translated_html):
    """Advance baseline AFTER a validated result has been saved successfully.

    The caller validates the job before writing, then passes fresh snapshots and
    the exact sanitized HTML it wrote. This does not itself apply translation.
    """
    if en['version'] != job['en_version']:
        raise StateConflict('English changed before the translated result was accepted.')
    english = _index(en).get(job['en_key'])
    bengali = _index(bn).get(job['bn_key'])
    if (english is None or bengali is None or english['hash'] != job['en_hash'] or
            bengali['hash'] != content_hash(translated_html)):
        raise StateConflict('Saved Bengali content does not match this translation result.')
    result = deepcopy(state)
    record = next((r for r in result['records'] if r['id'] == job['id']), None)
    if (record is None or record['en_key'] != job['en_key'] or record['bn_key'] != job['bn_key']
            or record['status'] != 'pending'):
        raise StateConflict('This translation job is no longer pending.')
    record.update(baseline_en_hash=english['hash'], baseline_bn_hash=bengali['hash'],
                  baseline_en_html=english['html'], baseline_bn_html=bengali['html'],
                  en=deepcopy(english), bn=deepcopy(bengali), status='unchanged', reason=None,
                  en_anchor=english['anchor'], bn_anchor=bengali['anchor'],
                  en_group_shape=en['groups'][english['anchor']], bn_group_shape=bn['groups'][bengali['anchor']])
    result['en_version'], result['bn_version'] = en['version'], bn['version']
    result['baseline_only'] = False
    return result


def load_state(path):
    path = Path(path)
    if not path.exists():
        return None
    state = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(state, dict) or state.get('schema') != SCHEMA or not isinstance(state.get('records'), list):
        raise StateConflict('The saved translation state needs review.')
    return state


def store_state(path, state):
    """Atomically persist metadata only; never write an authored source file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=path.name+'.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(handle, 'w', encoding='utf-8') as output:
            json.dump(state, output, ensure_ascii=False, indent=2)
            output.write('\n')
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def coverage_report():
    """Read-only pairing report against the current editor pages; write no state."""
    import content_editor
    result = []
    for page in content_editor.pages()['pages']:
        snapshots = []
        for lang in ('en', 'bn'):
            _, text, blocks, _ = content_editor.authored(page['id'], lang)
            snapshots.append(make_snapshot(text, blocks))
        state = initialise(*snapshots, document_id=page['id'])
        statuses = Counter(record['status'] for record in state['records'])
        result.append({'id': page['id'], 'english_blocks': len(state['records']),
                       'paired': statuses['unchanged'], 'unpaired': statuses['unpaired']})
    return result


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', action='store_true', help='Print read-only pairing coverage for current content')
    args = parser.parse_args()
    if args.report:
        print(json.dumps(coverage_report(), ensure_ascii=False, indent=2))
    else:
        parser.print_help()
