"""Safe local creation of bilingual pages and reusable content-editor page types."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import hashlib
from html import escape
import importlib.util
import json
from pathlib import Path
import re
import secrets
import subprocess
import sys
import unicodedata


REGISTRY = Path('content/editor-pages.json')
SLUG = re.compile(r'[a-z0-9]+(?:-[a-z0-9]+)*')
RESERVED_PREFIXES = ('person-', 'translation-', 'book-')


def _registry_module(editor):
    module = getattr(editor, 'authored_pages', None)
    if module is not None:
        return module
    # Load the implementation alongside this helper, not from an arbitrary
    # temporary site used by a regression test or a user-selected content root.
    spec = importlib.util.spec_from_file_location(
        'aguri_authored_pages_creation', Path(__file__).resolve().parents[1] / 'authored_pages.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _text(editor, value, field, limit):
    if (not isinstance(value, str) or not value.strip() or len(value) > limit or
            any(unicodedata.category(char) == 'Cc' for char in value)):
        raise editor.EditError(f'{field} must contain 1–{limit} characters without control characters.')
    value = value.strip()
    if '{{' in value or '}}' in value:
        raise editor.EditError(f'{field} cannot contain website template fields.')
    return value


def _load(editor, registry):
    try:
        return registry.load_registry(editor.ROOT)
    except (ValueError, TypeError) as error:
        raise editor.EditError(str(error)) from error


def _validate(editor, registry, value):
    try:
        registry.validate_registry(value, editor.ROOT)
    except (ValueError, TypeError) as error:
        raise editor.EditError(str(error)) from error


def _assert_available(editor):
    if editor.PUBLISHER is not None and editor.PUBLISHER.busy():
        raise editor.EditError('Wait for publishing checks or upload to finish before adding pages or page types.')


def _read_optional(path):
    return path.read_bytes() if path.exists() else None


def _restore(path, before):
    if before is None:
        path.unlink(missing_ok=True)
    else:
        _atomic_write(path, before)


def _atomic_write(path, data):
    temporary = path.with_name(path.name + '.editor-' + secrets.token_hex(6) + '.tmp')
    try:
        with temporary.open('xb') as stream:
            stream.write(data)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _encode(data):
    return (json.dumps(data, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def _backup(editor, kind, details, registry_before, history_before):
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + kind + '-' + secrets.token_hex(3)
    backup = editor.ROOT / 'local-editor/backups' / stamp
    backup.mkdir(parents=True)
    if registry_before is not None:
        (backup / REGISTRY).parent.mkdir(parents=True, exist_ok=True)
        (backup / REGISTRY).write_bytes(registry_before)
    if history_before is not None:
        (backup / 'page-history.json').write_bytes(history_before)
    (backup / 'change.json').write_bytes(_encode({
        'action': kind, 'savedAt': stamp, 'registryExisted': registry_before is not None,
        'historyExisted': history_before is not None, **details,
    }))
    return backup


def _safe_slug(editor, value):
    if (not isinstance(value, str) or len(value) > 80 or not SLUG.fullmatch(value) or
            value.startswith(RESERVED_PREFIXES)):
        raise editor.EditError('Use a page address of up to 80 lowercase letters, numbers and single hyphens. '
                               'Addresses starting person-, translation- or book- are reserved.')
    return value


def _assert_unused(editor, slug, data):
    existing = {row[0] for row in editor.page_specs()}
    existing.update(row['id'] for row in editor.pages()['pages'])
    existing.update(row['id'] for row in data['pages'])
    if slug in existing:
        raise editor.EditError('A page already uses this address. Choose another page address.')
    # Generated pages and stray authored fragments also reserve their addresses;
    # a page may be unavailable in the editor without being safe to overwrite.
    for folder in ('content', 'content/bn', 'site', 'site/bn'):
        path = editor.ROOT / folder / (slug + '.html')
        if path.exists() or path.is_symlink():
            raise editor.EditError('A website page already uses this address. Choose another page address.')


def _label(title):
    return title if len(title) <= 120 else title[:117].rstrip() + '…'


def _fragment(template, description, lang):
    headings = {
        'en': {
            'article': [('overview', 'Overview', 'Add an introduction to this article.'),
                        ('context', 'History and context', 'Add the researched account and its supporting references.'),
                        ('sources', 'Sources and further reading', 'Add source references and suggestions for further reading.')],
            'general': [('overview', 'Overview', 'Add the information this page should share.'),
                        ('details', 'Further information', 'Add further details and helpful links.')],
            'biography': [('life', 'Life and background', 'Add a verified account of this person’s life and background.'),
                          ('work', 'Work and contributions', 'Add verified details of their work and contributions.'),
                          ('legacy', 'Legacy and sources', 'Add their legacy and the sources supporting this biography.')],
        },
        'bn': {
            'article': [('overview', 'পরিচিতি', 'এই প্রবন্ধের ভূমিকা লিখুন।'),
                        ('context', 'ইতিহাস ও প্রেক্ষাপট', 'গবেষণালব্ধ বিবরণ এবং তার সমর্থনে উৎসের উল্লেখ যোগ করুন।'),
                        ('sources', 'উৎস ও আরও পড়ুন', 'উৎসের উল্লেখ এবং আরও পড়ার পরামর্শ যোগ করুন।')],
            'general': [('overview', 'পরিচিতি', 'এই পাতায় যে তথ্য জানাতে চান তা লিখুন।'),
                        ('details', 'আরও তথ্য', 'আরও বিবরণ এবং সহায়ক লিঙ্ক যোগ করুন।')],
            'biography': [('life', 'জীবন ও পটভূমি', 'এই ব্যক্তির জীবন ও পটভূমির যাচাইকৃত বিবরণ লিখুন।'),
                          ('work', 'কর্ম ও অবদান', 'তাঁর কর্ম ও অবদানের যাচাইকৃত বিবরণ যোগ করুন।'),
                          ('legacy', 'উত্তরাধিকার ও উৎস', 'তাঁর উত্তরাধিকার এবং এই জীবনীর সমর্থনে উৎসের উল্লেখ যোগ করুন।')],
        },
    }
    blocks = [f'<div class="prose">\n<p>{escape(description)}</p>']
    for identity, heading, paragraph in headings[lang][template]:
        blocks.append(f'<h2 id="{identity}">{escape(heading)}</h2>\n<p>{escape(paragraph)}</p>')
    return '\n'.join(blocks) + '\n</div>\n'


def create_type(editor, payload):
    """Create a reusable page type without rebuilding or changing existing pages."""
    if not isinstance(payload, dict):
        raise editor.EditError('Provide the page type details.')
    name = _text(editor, payload.get('name'), 'Page type name', 80)
    description = _text(editor, payload.get('description'), 'Page type description', 240)
    registry = _registry_module(editor)
    templates = {entry['id'] for entry in registry.BUILTIN_TYPES}
    template = payload.get('template')
    if not isinstance(template, str) or template not in templates:
        raise editor.EditError('Choose Article, General page or Biography as the starter layout.')
    normalized = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode().lower()
    identity = re.sub(r'[^a-z0-9]+', '-', normalized).strip('-')[:80].rstrip('-')
    if not identity:
        identity = 'type-' + hashlib.sha256(name.encode()).hexdigest()[:12]
    _assert_available(editor)
    with editor.LOCK:
        _assert_available(editor)
        data = _load(editor, registry)
        types = registry.BUILTIN_TYPES + data['types']
        if any(entry['id'] == identity or entry['name'].casefold() == name.casefold() for entry in types):
            raise editor.EditError('A page type already uses this name. Choose another page type name.')
        updated = deepcopy(data)
        updated['types'].append({'id': identity, 'name': name, 'template': template, 'description': description})
        _validate(editor, registry, updated)
        path = editor.ROOT / REGISTRY
        before = _read_optional(path)
        history = _read_optional(editor.ROOT / 'content/page-history.json')
        _backup(editor, 'create-type', {'type': identity}, before, history)
        try:
            _atomic_write(path, _encode(updated))
            result = editor.pages()
        except Exception:
            _restore(path, before)
            raise
        return {'ok': True, 'message': 'Page type added. Choose it when adding a page.', **result}


def create_page(editor, payload):
    """Create both language sources, verify the site, then register a new edit baseline."""
    if not isinstance(payload, dict):
        raise editor.EditError('Provide the new page details.')
    slug = _safe_slug(editor, payload.get('slug'))
    lang = payload.get('lang', 'en')
    if lang not in ('en', 'bn'):
        raise editor.EditError('Choose English or Bengali.')
    title = _text(editor, payload.get('title'), 'English page title', 180)
    description = _text(editor, payload.get('description'), 'English page description', 500)
    title_bn = _text(editor, payload.get('titleBn'), 'Bengali page title', 180)
    description_bn = _text(editor, payload.get('descriptionBn'), 'Bengali page description', 500)
    registry = _registry_module(editor)
    _assert_available(editor)
    with editor.LOCK:
        _assert_available(editor)
        data = _load(editor, registry)
        page_type = next((entry for entry in registry.BUILTIN_TYPES + data['types']
                          if entry['id'] == payload.get('type')), None)
        if page_type is None:
            raise editor.EditError('Choose an available page type.')
        if (not isinstance(payload.get('section'), str) or
                payload['section'] not in {entry['id'] for entry in registry.SECTIONS}):
            raise editor.EditError('Choose the website section where this page belongs.')
        _assert_unused(editor, slug, data)
        updated = deepcopy(data)
        updated['pages'].append({
            'id': slug, 'type': page_type['id'], 'section': payload['section'],
            'en': {'label': _label(title), 'title': title, 'description': description},
            'bn': {'label': _label(title_bn), 'title': title_bn, 'description': description_bn},
        })
        _validate(editor, registry, updated)
        registry_path = editor.ROOT / REGISTRY
        history_path = editor.ROOT / 'content/page-history.json'
        registry_before = _read_optional(registry_path)
        history_before = _read_optional(history_path)
        backup = _backup(editor, 'create-page', {'page': slug, 'language': lang}, registry_before, history_before)
        created = []
        try:
            for edition, intro in (('en', description), ('bn', description_bn)):
                path = editor.ROOT / 'content' / ('bn' if edition == 'bn' else '') / (slug + '.html')
                # Exclusive creation also protects an external file written since
                # the collision check; rollback removes only sources we created.
                with path.open('x', encoding='utf-8') as stream:
                    created.append(path)
                    stream.write(_fragment(page_type['template'], intro, edition))
            _atomic_write(registry_path, _encode(updated))
            logs = []
            for command in ('build.py', 'scripts/check_site.py'):
                run = subprocess.run([sys.executable, str(editor.ROOT / command)], cwd=editor.ROOT,
                                     capture_output=True, text=True, timeout=180)
                logs.append(run.stdout + run.stderr)
                if run.returncode:
                    raise editor.EditError('The site check found a problem. The new page was removed and the previous '
                                           'version has been restored. ' + (run.stderr or run.stdout)[-1600:])
            result = editor.pages()
            document = editor.document(slug, lang)
            (backup / 'checks.txt').write_text('\n'.join(logs), encoding='utf-8')
        except Exception:
            for path in created:
                path.unlink(missing_ok=True)
            _restore(registry_path, registry_before)
            _restore(history_path, history_before)
            for edition in ('', 'bn'):
                (editor.ROOT / 'site' / edition / (slug + '.html')).unlink(missing_ok=True)
            try:
                subprocess.run([sys.executable, str(editor.ROOT / 'build.py')], cwd=editor.ROOT,
                               capture_output=True, timeout=180)
            finally:
                _restore(history_path, history_before)
            raise
        sync_message = ''
        sync = editor.TRANSLATOR
        try:
            if sync is None and (editor.ROOT / 'local-editor/translation/settings.json').exists():
                sync = editor.translator()
            if sync is not None:
                # capture is specifically designed for callers holding LOCK.
                # initialize would reacquire the editor's non-reentrant lock.
                with sync.mutex:
                    sync.titles[slug] = title
                    sync.capture(slug)
        except Exception:
            if sync is not None:
                sync.error = 'The new page is saved. Bengali tracking needs a retry before publishing.'
            sync_message = ' Bengali tracking needs attention.'
        return {'ok': True, 'message': 'Page added in English and Bengali. Site checks passed.' + sync_message,
                **result, 'document': document}
