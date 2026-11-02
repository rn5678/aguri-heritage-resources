"""Incremental local Bengali updates, using the user's signed-in Codex account."""
from __future__ import annotations
from collections import Counter
from copy import deepcopy
from datetime import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time


def module(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + '.py'))
    result = importlib.util.module_from_spec(spec)
    sys.modules[name] = result
    spec.loader.exec_module(result)
    return result


class Translator:
    def __init__(self, root, edit_lock, authored, clean_block, publisher_busy, *, start_worker=True):
        self.root, self.edit_lock = Path(root), edit_lock
        self.authored, self.clean_block, self.publisher_busy = authored, clean_block, publisher_busy
        self.mapping = module('editor_translation_state')
        self.client = module('editor_codex_translate')
        self.work = self.root / 'local-editor/translation'
        self.mutex = threading.RLock()
        self.wake = threading.Event()
        self.states = {}
        self.enabled = False
        self.running = False
        self.error = ''
        self.due = 0
        self.completed = False
        self.revision = 0
        self.usage = {'input_tokens': 0, 'output_tokens': 0, 'cached_input_tokens': 0}
        self.last_usage = {}
        self.cache = {}
        self.titles = {}
        settings = self.work / 'settings.json'
        if settings.exists():
            config = json.loads(settings.read_text())
            self.enabled = config.get('enabled') is True
        if (self.work / 'usage.json').exists():
            self.usage = json.loads((self.work / 'usage.json').read_text())
        if (self.work / 'cache.json').exists():
            self.cache = json.loads((self.work / 'cache.json').read_text())
        for path in sorted((self.work / 'pages').glob('*.json')):
            state = self.mapping.load_state(path)
            self.states[state['document_id']] = state
        if start_worker:
            threading.Thread(target=self._worker, name='bengali-updates', daemon=True).start()

    def _store(self, doc_id):
        self.mapping.store_state(self.work / 'pages' / (doc_id + '.json'), self.states[doc_id])

    def _snapshots(self, doc_id):
        results = []
        for lang in ('en', 'bn'):
            _, text, blocks, _ = self.authored(doc_id, lang)
            results.append(self.mapping.make_snapshot(text, blocks))
        return results

    def initialize(self, pages):
        # Establish a baseline once; existing prose is never translated on startup.
        with self.edit_lock, self.mutex:
            self.titles = {p['id']: p['title'] for p in pages}
            for p in pages:
                self.capture(p['id'])
            self.due = time.monotonic() + 4
        self.wake.set()

    def capture(self, doc_id):
        """Caller holds edit_lock; invoke before AND after each successful save."""
        with self.mutex:
            en, bn = self._snapshots(doc_id)
            if doc_id in self.states:
                self.states[doc_id] = self.mapping.refresh(self.states[doc_id], en, bn)
            else:
                self.states[doc_id] = self.mapping.initialise(en, bn, document_id=doc_id)
            self._store(doc_id)
            self.due = time.monotonic() + 4
            self.wake.set()

    def plan_structure(self, doc_id, lang, delete_nodes, insertions, *, capabilities):
        """Prepare paired Bengali structure; called under the editor's save lock.

        Text translation still happens after saving. Safe English additions get
        an empty Bengali paragraph at the paired location; complete deletions
        remove the matching Bengali paragraph without a model call.
        """
        with self.mutex:
            original = {language: self.authored(doc_id, language) for language in ('en', 'bn')}
            before = {language: self.mapping.make_snapshot(value[1], value[2]) for language, value in original.items()}
            state_before = deepcopy(self.states[doc_id])
            en_by_start = {b['start']: b for b in before['en']['blocks']}
            bn_nodes = {b['key']: node for b, node in zip(before['bn']['blocks'], original['bn'][2])}
            records = {r['en_key']: r for r in state_before['records'] if not r.get('tombstone')}
            bn_patches, paired_new = [], set()
            deleted_en = [en_by_start[n.start]['key'] for n in delete_nodes] if lang == 'en' else []

            def paired_node(english):
                record = records.get(en_by_start[english.start]['key'])
                if not record or record['status'] in ('conflict', 'needs_pairing'):
                    return None
                return bn_nodes.get(record.get('bn_key'))

            if lang == 'en' and self.enabled:
                bn_text = original['bn'][1]
                for node in delete_nodes:
                    target = paired_node(node)
                    if target and capabilities(bn_text, target)['canDelete']:
                        bn_patches.append((target.start, target.end, ''))
                for insertion in insertions:
                    identity = insertion['id']
                    if any(n.attrs.get('data-editor-block') == identity for n in original['bn'][2]):
                        raise ValueError('This new paragraph already exists in Bengali. Reload the page before adding it again.')
                    target = paired_node(insertion['anchor'])
                    direction = insertion['position']
                    capability = 'canInsertBefore' if direction == 'before' else 'canInsertAfter'
                    if target and capabilities(bn_text, target)[capability]:
                        offset = target.start if direction == 'before' else target.end
                        bn_patches.append((offset, offset, f'\n<p data-editor-block="{identity}"></p>\n'))
                        paired_new.add(identity)

            def finish(changes_by_lang):
                # Re-identify surviving blocks by exact source edit offsets,
                # never by a guessed new paragraph index or similar wording.
                with self.mutex:
                    current = {language: self.authored(doc_id, language) for language in ('en', 'bn')}
                    after = {language: self.mapping.make_snapshot(value[1], value[2]) for language, value in current.items()}
                    maps = {}
                    for language in ('en', 'bn'):
                        change = changes_by_lang.get(language)
                        patches = change['patches'] if change else []
                        if change and (change['before'] != original[language][1] or change['after'] != current[language][1]):
                            raise ValueError('The article changed elsewhere during saving. Check its Bengali version before publishing.')
                        by_start = {b['start']: b for b in after[language]['blocks']}
                        pairs = {}
                        for block in before[language]['blocks']:
                            if any(start <= block['start'] and end >= block['end'] and start != end for start, end, _ in patches):
                                continue
                            offset = block['start'] + sum(len(value) - (end - start) for start, end, value in patches if end <= block['start'])
                            survivor = by_start.get(offset)
                            if not survivor or survivor['tag'] != block['tag']:
                                raise ValueError('A paragraph could not be tracked after saving. Check its Bengali version before publishing.')
                            pairs[block['key']] = survivor['key']
                        maps[language] = pairs
                    new_pairs = []
                    if lang == 'en':
                        identified = {}
                        for language in ('en', 'bn'):
                            identified[language] = {node.attrs.get('data-editor-block'): block['key']
                                                    for block, node in zip(after[language]['blocks'], current[language][2])
                                                    if node.attrs.get('data-editor-block')}
                        for insertion in insertions:
                            identity = insertion['id']
                            if identity not in identified['en'] or (identity in paired_new and identity not in identified['bn']):
                                raise ValueError('The new paragraph needs a Bengali review before publishing.')
                            new_pairs.append({'en_key': identified['en'][identity],
                                              'bn_key': identified['bn'].get(identity) if identity in paired_new else None})
                    self.states[doc_id] = self.mapping.rebase_structure(
                        state_before, before['en'], before['bn'], after['en'], after['bn'],
                        maps['en'], maps['bn'], deleted_en_keys=deleted_en, new_pairs=new_pairs)
                    self._store(doc_id)
                    if bn_patches:
                        self.revision += 1
                        self.completed = True
                    self.due = time.monotonic() + 4
                    self.wake.set()
            related = []
            if bn_patches:
                related.append({'path': original['bn'][0], 'before': original['bn'][1], 'patches': bn_patches})
            return {'related': related, 'finish': finish}

    def _counts(self):
        pending, reviews = 0, []
        for doc_id, state in self.states.items():
            pending += len(self.mapping.pending_jobs(state))
            count = sum(r['status'] in ('needs_pairing', 'conflict') for r in state['records'])
            if self.error:
                count += len(self.mapping.pending_jobs(state))
            if count:
                reviews.append({'id': doc_id, 'title': self.titles.get(doc_id, doc_id), 'count': count})
        return pending, reviews

    def status(self):
        with self.mutex:
            pending, reviews = self._counts()
            phase = 'idle'
            message = 'Ready. Future English saves will update matching Bengali text.'
            if not self.enabled:
                message = 'Automatic Bengali updates are paused. You can edit both languages yourself.'
            elif self.running:
                phase, message = 'running', 'Updating the changed Bengali passages…'
            elif self.error:
                phase, message = 'error', self.error
            elif pending:
                phase, message = 'queued', f'{pending} changed passage(s) waiting for a Bengali update.'
            elif reviews:
                phase, message = 'review', 'Some passages could not be matched safely. Check their Bengali pages, then mark them reviewed.'
            elif self.completed:
                phase, message = 'success', 'Bengali updates saved locally. You can preview both languages before publishing.'
            return {'enabled': self.enabled, 'phase': phase, 'message': message,
                    'pending': pending, 'reviewCount': sum(p['count'] for p in reviews),
                    'reviewDocuments': reviews, 'usage': dict(self.usage), 'lastUsage': dict(self.last_usage) or None,
                    'model': getattr(self.client, 'MODEL', 'gpt-6-luna'), 'revision': self.revision}

    def configure(self, enabled):
        if not isinstance(enabled, bool):
            raise ValueError('Choose whether Bengali updates should be on or off.')
        with self.edit_lock, self.mutex:
            if self.publisher_busy():
                raise ValueError('Wait for publishing to finish before changing Bengali updates.')
            self.enabled = enabled
            self.mapping.store_state(self.work / 'settings.json', {'enabled': enabled})
            self.due = time.monotonic() + 4
        self.wake.set()
        return self.status()

    def retry(self):
        with self.edit_lock, self.mutex:
            for doc_id in list(self.states):
                self.capture(doc_id)
            self.error = ''
            self.due = time.monotonic()
        self.wake.set()
        return self.status()

    def accept(self, doc_id):
        with self.edit_lock, self.mutex:
            if self.running:
                raise ValueError('Wait for the current Bengali update to finish.')
            if doc_id not in self.states:
                raise ValueError('Open a page with a Bengali review notice first.')
            en, bn = self._snapshots(doc_id)
            self.states[doc_id] = self.mapping.initialise(en, bn, document_id=doc_id)
            self._store(doc_id)
            self.error = ''
        self.wake.set()
        return self.status()

    def assert_publish_ready(self):
        # The caller holds edit_lock. Catch edits made outside the browser too.
        with self.mutex:
            for doc_id in self.states:
                en, bn = self._snapshots(doc_id)
                self.states[doc_id] = self.mapping.refresh(self.states[doc_id], en, bn)
                self._store(doc_id)
        data = self.status()
        if data['enabled'] and (data['pending'] or data['reviewCount'] or data['phase'] in ('running', 'error')):
            raise ValueError('Finish or review the Bengali updates before publishing, or turn automatic updates off to publish your saved versions.')

    def _worker(self):
        while True:
            self.wake.wait(1)
            self.wake.clear()
            with self.mutex:
                ready = self.enabled and not self.error and self._counts()[0] > 0 and time.monotonic() >= self.due
            if not ready:
                continue
            try:
                if not self.publisher_busy():
                    self.run_once()
            except Exception:
                with self.mutex:
                    self.running = False
                    self.error = 'Bengali updates stopped safely. Your English edits are saved. Try again, or review Bengali manually.'

    @staticmethod
    def _cache_key(job):
        return hashlib.sha256(json.dumps([job['en_html'], job['bn_html']], ensure_ascii=False).encode()).hexdigest()

    def _mechanical(self, job):
        en = job['en_html']
        previous = job.get('previous_en_html', '')
        if not re.sub(r'<br\s*/?>|\s', '', en):
            return ''
        cite = re.compile(r'\[cite:([\w-]+)\]')
        if previous and cite.sub('', en) == cite.sub('', previous):
            removed = Counter(cite.findall(previous)) - Counter(cite.findall(en))
            if removed and not (Counter(cite.findall(en)) - Counter(cite.findall(previous))):
                def replace(match):
                    key = match[1]
                    if removed[key]:
                        removed[key] -= 1
                        return ''
                    return match[0]
                return cite.sub(replace, job['bn_html'])
        return None

    def run_once(self):
        """One bounded batch. No lock is held during the network/model request."""
        with self.edit_lock, self.mutex:
            if not self.enabled or self.running or self.publisher_busy():
                return False
            selected = None
            for doc_id in self.states:
                en, bn = self._snapshots(doc_id)
                self.states[doc_id] = self.mapping.refresh(self.states[doc_id], en, bn)
                self._store(doc_id)
                jobs = self.mapping.pending_jobs(self.states[doc_id])
                if jobs:
                    selected = doc_id
                    break
            if not selected:
                return False
            batch, size, english_size = [], 0, 0
            for job in jobs:
                length = len(job['en_html']) + len(job['bn_html'])
                if batch and (len(batch) >= 8 or size + length > 12000 or english_size + len(job['en_html']) > 6000):
                    break
                if length > 12000 or max(len(job['en_html']), len(job['bn_html'])) > 5000:
                    self.error = 'This passage is too long for a small translation batch. Update its Bengali page manually and mark it reviewed.'
                    return False
                batch.append(job)
                size += length
                english_size += len(job['en_html'])
            self.running = True
        applied_successfully = False
        try:
            translated, requests = {}, []
            for job in batch:
                result = self._mechanical(job)
                if result is None:
                    result = self.cache.get(self._cache_key(job))
                if result is None:
                    requests.append({'id': job['id'], 'english': job['en_html'], 'bengali': job['bn_html']})
                else:
                    translated[job['id']] = result
            usage = {}
            if requests:
                result = self.client.translate(requests)
                translated.update(result['translations'])
                usage = result['usage']
            # Retain validated responses before application so a version conflict
            # or build failure can be retried without paying for the same output.
            with self.mutex:
                for job in batch:
                    self.cache[self._cache_key(job)] = translated[job['id']]
                self.mapping.store_state(self.work / 'cache.json', self.cache)
                self.last_usage = usage
                for key, value in usage.items():
                    self.usage[key] = self.usage.get(key, 0) + value
                self.mapping.store_state(self.work / 'usage.json', self.usage)
            with self.edit_lock, self.mutex:
                if not self.enabled or self.publisher_busy():
                    return False
                en, bn = self._snapshots(selected)
                for job in batch:
                    self.mapping.validate_job(job, en, bn)
                applied = self._apply(selected, batch, translated)
                applied_successfully = True
                en_after, bn_after = self._snapshots(selected)
                state = self.states[selected]
                for job in batch:
                    state = self.mapping.accept_job(state, job, en_after, bn_after, applied[job['id']])
                self.states[selected] = state
                self._store(selected)
                self.completed = True
                self.revision += 1
                self.error = ''
            return True
        except self.mapping.StateConflict:
            with self.edit_lock, self.mutex:
                en, bn = self._snapshots(selected)
                self.states[selected] = self.mapping.refresh(self.states[selected], en, bn)
                self._store(selected)
                self.error = 'Bengali was saved, but its tracking record needs review. Check the Bengali page and mark it reviewed.' if applied_successfully else ''
                self.due = time.monotonic() + 4
            return False
        except Exception as exc:
            with self.mutex:
                if applied_successfully:
                    self.error = 'Bengali was saved, but its tracking record needs review. Check the Bengali page and mark it reviewed.'
                else:
                    self.error = str(exc) if isinstance(exc, (ValueError, self.client.TranslationError)) else 'Bengali could not be updated. Your English edits are saved; try again.'
            return False
        finally:
            with self.mutex:
                self.running = False

    def _apply(self, doc_id, jobs, translations):
        path, text, blocks, _ = self.authored(doc_id, 'bn')
        snapshot = self.mapping.make_snapshot(text, blocks)
        node_map = {record['key']: node for record, node in zip(snapshot['blocks'], blocks)}
        patches, applied = [], {}
        for job in jobs:
            node = node_map[job['bn_key']]
            # The English markup is the exact output contract. Existing Bengali
            # linked IDs must also remain valid before replacing its inner text.
            value = self.clean_block(translations[job['id']], job['en_html'])
            original = text[node.opening:node.close]
            ids = lambda html: Counter(re.findall(r'\bid=[\"\x27]([^\"\x27]+)', html))
            if ids(value) != ids(original):
                raise ValueError('A linked Bengali passage needs manual review before it can be replaced.')
            applied[job['id']] = value
            patches.append((node.opening, node.close, value))
        updated = text
        for start, end, value in sorted(patches, reverse=True):
            updated = updated[:start] + value + updated[end:]
        if updated == text:
            return applied
        stamp = datetime.now().strftime('%Y%m%d-%H%M%S') + '-bengali-' + secrets.token_hex(3)
        backup = self.root / 'local-editor/backups' / stamp
        relative = path.relative_to(self.root)
        (backup / relative).parent.mkdir(parents=True)
        shutil.copy2(path, backup / relative)
        history = self.root / 'content/page-history.json'
        history_before = history.read_bytes()
        (backup / 'page-history.json').write_bytes(history_before)
        (backup / 'change.json').write_text(json.dumps({'page': doc_id, 'language': 'bn', 'source': str(relative), 'savedAt': stamp}))
        try:
            temporary = path.with_suffix('.html.editor-tmp')
            temporary.write_text(updated)
            temporary.replace(path)
            for command in ('build.py', 'scripts/check_site.py'):
                run = subprocess.run([sys.executable, str(self.root / command)], cwd=self.root, capture_output=True, text=True, timeout=180)
                if run.returncode:
                    raise ValueError('The Bengali site check failed. Its previous version was restored; your English edits are saved.')
        except Exception:
            path.write_text(text)
            history.write_bytes(history_before)
            try:
                subprocess.run([sys.executable, str(self.root / 'build.py')], cwd=self.root, capture_output=True, timeout=180)
            finally:
                history.write_bytes(history_before)
            raise
        return applied
