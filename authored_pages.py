"""Shared registry for pages and page types created in the local content editor."""
from __future__ import annotations

import ast
from copy import deepcopy
import json
from pathlib import Path
import re


BUILTIN_TYPES = [
    {'id': 'article', 'name': 'Article', 'template': 'article',
     'description': 'A researched story with sections, notes and sources.'},
    {'id': 'general', 'name': 'General page', 'template': 'general',
     'description': 'An information page with headings and paragraphs.'},
    {'id': 'biography', 'name': 'Biography', 'template': 'biography',
     'description': 'A life story with background, work and sources.'},
]
SECTIONS = [
    {'id': 'history', 'name': 'History'},
    {'id': 'culture', 'name': 'Culture'},
    {'id': 'geography', 'name': 'Places'},
    {'id': 'people', 'name': 'People'},
    {'id': 'bibliography', 'name': 'Resources'},
    {'id': 'about', 'name': 'About'},
]
REGISTRY_PATH = Path('content/editor-pages.json')
KEY_PATTERN = r'[a-z0-9]+(?:-[a-z0-9]+)*'
RESERVED_IDS = {'404', 'index', 'bn', 'assets', 'api', 'preview', 'review', 'contribute',
                'robots', 'sitemap', 'sw'}
RESERVED_PREFIXES = ('person-', 'translation-', 'book-')


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate page registry field: ' + key)
        result[key] = value
    return result


def _text(value, field, limit):
    if (not isinstance(value, str) or not value.strip() or len(value) > limit or
            any(ord(char) < 32 for char in value)):
        raise ValueError(f'{field} must be text between 1 and {limit} characters.')


def _key(value, field):
    if not isinstance(value, str) or len(value) > 80 or not re.fullmatch(KEY_PATTERN, value):
        raise ValueError(f'{field} must use lowercase letters, numbers and single hyphens.')


def _existing_keys(root):
    """Read the fixed page declarations without importing the website builder."""
    path = Path(root) / 'build.py'
    if not path.is_file():
        return set()
    tree = ast.parse(path.read_text(encoding='utf-8'))
    for node in tree.body:
        if (isinstance(node, ast.Assign) and
                any(isinstance(target, ast.Name) and target.id == 'PAGES'
                    for target in node.targets)):
            return {entry[0] for entry in ast.literal_eval(node.value)}
    raise ValueError('The fixed website page list could not be read.')


def validate_registry(data, root=None):
    """Validate metadata before creating files, and return it without changing it."""
    if (not isinstance(data, dict) or data.get('version') != 1 or
            not isinstance(data.get('types'), list) or not isinstance(data.get('pages'), list)):
        raise ValueError('The page registry needs version 1, types and pages lists.')
    if len(data['types']) > 100 or len(data['pages']) > 1000:
        raise ValueError('The page registry contains too many page types or pages.')
    templates = {entry['id'] for entry in BUILTIN_TYPES}
    type_ids = set(templates)
    for entry in data['types']:
        if not isinstance(entry, dict):
            raise ValueError('Each page type needs a name and template.')
        _key(entry.get('id'), 'Page type identifier')
        if entry['id'] in type_ids:
            raise ValueError('A page type already uses this identifier: ' + entry['id'])
        _text(entry.get('name'), 'Page type name', 80)
        _text(entry.get('description'), 'Page type description', 240)
        if not isinstance(entry.get('template'), str) or entry['template'] not in templates:
            raise ValueError('Choose Article, General page or Biography as the page template.')
        type_ids.add(entry['id'])
    sections = {entry['id'] for entry in SECTIONS}
    existing = RESERVED_IDS | (_existing_keys(root) if root is not None else set())
    identifiers = set()
    for entry in data['pages']:
        if not isinstance(entry, dict):
            raise ValueError('Each page needs its type, section and edition details.')
        _key(entry.get('id'), 'Page address')
        key = entry['id']
        if key in identifiers or key in existing or key.startswith(RESERVED_PREFIXES):
            raise ValueError('A website page already uses or reserves this address: ' + key)
        identifiers.add(key)
        if not isinstance(entry.get('type'), str) or entry['type'] not in type_ids:
            raise ValueError('Choose an available page type for ' + key)
        if not isinstance(entry.get('section'), str) or entry['section'] not in sections:
            raise ValueError('Choose an available website section for ' + key)
        for lang in ('en', 'bn'):
            edition = entry.get(lang)
            if not isinstance(edition, dict):
                raise ValueError('Both English and Bengali details are required for ' + key)
            for field, limit in (('label', 120), ('title', 180), ('description', 500)):
                _text(edition.get(field), f'{lang.upper()} page {field}', limit)
    return data


def load_registry(root):
    path = Path(root) / REGISTRY_PATH
    if not path.exists():
        return {'version': 1, 'types': [], 'pages': []}
    try:
        data = json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=_unique_keys)
        return validate_registry(data, root)
    except (ValueError, TypeError) as error:
        raise ValueError(f'Invalid editor page registry: {error}') from error


def page_types(root):
    return deepcopy(BUILTIN_TYPES) + load_registry(root)['types']


def descriptors(root, lang):
    if lang not in ('en', 'bn'):
        raise ValueError('Choose English or Bengali.')
    return [(entry['id'], entry[lang]['label'], entry[lang]['title'], entry[lang]['description'])
            for entry in load_registry(root)['pages']]


def page_map(root):
    return {entry['id']: entry for entry in load_registry(root)['pages']}
