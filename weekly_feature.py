"""Choose and render a bilingual featured carousel from editorial updates.

The current selection is locked for the week in India. Each build also prepares
next Monday's selection so the homepage can switch without a scheduled rebuild.
Only already published content can be included in that prepared selection.
"""
from datetime import date, datetime, timedelta
from html import escape
from pathlib import Path
from asset_paths import is_local_asset
from tempfile import NamedTemporaryFile
from zoneinfo import ZoneInfo
import json
import os
import re

from localization import display_date, num
from portrait_headers import PROFILE_PATTERN, PHOTO_PATTERN

INDIA = ZoneInfo('Asia/Kolkata')
EDITIONS = ('en', 'bn')
EXCLUDED = {
    'index', 'people', 'archives', 'translations', 'bibliography', 'research',
    'about', 'contribute', 'review', 'rights', 'contributor-terms', '404',
}
KEY_PATTERN = r'[a-z0-9]+(?:-[a-z0-9]+)*'


def _day(value):
    if isinstance(value, datetime):
        return value.astimezone(INDIA).date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


def _week(day):
    return (day - timedelta(days=day.weekday())).isoformat()


def _descriptors(items):
    if isinstance(items, dict):
        return {key: tuple(value) for key, value in items.items()}
    return {key: (label, title, description)
            for key, label, title, description in items}


def _read_config(root):
    config = json.loads((root / 'content/weekly-feature.json').read_text(encoding='utf-8'))
    if config.get('version') != 1:
        raise ValueError('Weekly feature configuration must use version 1')
    excluded = config.get('excluded_keys', [])
    if not isinstance(excluded, list) or any(not isinstance(key, str) for key in excluded):
        raise ValueError('Weekly feature excluded_keys must be a list of page keys')
    carousel = config.get('carousel', {})
    if not isinstance(carousel, dict):
        raise ValueError('Weekly feature carousel must be an object')
    limit = carousel.get('limit', 5)
    interval = carousel.get('interval_ms', 7000)
    if type(limit) is not int or not 1 <= limit <= 8:
        raise ValueError('Weekly feature carousel limit must be between 1 and 8')
    if type(interval) is not int or not 5000 <= interval <= 60000:
        raise ValueError('Weekly feature carousel interval_ms must be between 5000 and 60000')
    additional = carousel.get('additional_keys', [])
    if not isinstance(additional, list) or any(
            not isinstance(key, str) or not re.fullmatch(KEY_PATTERN, key) for key in additional):
        raise ValueError('Weekly feature carousel additional_keys must be a list of page keys')
    override = config.get('override')
    if override:
        if not re.fullmatch(KEY_PATTERN, override.get('key', '')):
            raise ValueError('Invalid weekly feature override key')
        through = _day(override['through'])
        if override.get('from') and _day(override['from']) > through:
            raise ValueError('Weekly feature override ends before it begins')
    return config


def _read_state(path):
    if not path.exists():
        return None
    state = json.loads(path.read_text(encoding='utf-8'))
    if state.get('version') != 1:
        raise ValueError('Weekly feature state must use version 1')
    for part in ('current', 'next'):
        value = state.get(part, {})
        if not re.fullmatch(KEY_PATTERN, value.get('key', '')):
            raise ValueError('Invalid weekly feature state page key')
        day = _day(value['week'])
        if day.weekday() != 0:
            raise ValueError('Weekly feature state must start on a Monday')
    if _day(state['next']['week']) != _day(state['current']['week']) + timedelta(days=7):
        raise ValueError('Weekly feature state must contain consecutive weeks')
    return state


def _override(config, day, candidates):
    override = config.get('override')
    if (override and override['key'] in candidates and
            day <= _day(override['through']) and
            (not override.get('from') or day >= _day(override['from']))):
        return override['key']
    return None


def _newest(candidates, dates, preferred=None):
    newest = max(dates[key] for key in candidates)
    tied = sorted(key for key in candidates if dates[key] == newest)
    return preferred if preferred in tied else tied[0]


def _portrait(root, key, lang):
    if not key.startswith('person-'):
        return None
    source = root / 'content' / ('bn' if lang == 'bn' else '') / 'people.html'
    if not source.exists():
        return None
    slug = key.removeprefix('person-')
    for candidate, body in re.findall(PROFILE_PATTERN, source.read_text(encoding='utf-8'), re.S):
        if candidate != slug:
            continue
        match = re.search(PHOTO_PATTERN, body, re.S)
        if match and '<img ' in match[0]:
            # Keep the complete authored caption, source links and licence notes.
            return match[0].replace('class="person-photo"',
                                    'class="weekly-feature-media weekly-feature-portrait"', 1)
    return None


def _media(root, key, lang):
    portrait = _portrait(root, key, lang)
    if portrait:
        return portrait
    catalog_path = root / 'assets/page-artworks/catalog.json'
    catalog = json.loads(catalog_path.read_text(encoding='utf-8')) if catalog_path.exists() else {}
    item = catalog.get(key)
    if not item:
        return ''
    if not is_local_asset(root, item['file']):
        raise ValueError('Missing or invalid weekly feature image: ' + key)
    caption = item.get('caption_' + lang) or (
        'বিষয়ভিত্তিক কল্পিত চিত্র' if lang == 'bn' else 'A contemporary topic illustration')
    return (
        '<figure class="weekly-feature-media weekly-feature-artwork">'
        f'<img src="{escape(item["file"], quote=True)}" '
        f'alt="{escape(item["alt_" + lang], quote=True)}" '
        f'width="{int(item["width"])}" height="{int(item["height"])}" loading="lazy" decoding="async">'
        f'<figcaption><strong>{escape(item["title_" + lang])}</strong> '
        f'{escape(caption)}</figcaption></figure>')


def _intro(value):
    # Curated teasers may italicize titles, but cannot introduce active markup.
    escaped = escape(value)
    for tag in ('em', 'strong'):
        escaped = escaped.replace('&lt;' + tag + '&gt;', '<' + tag + '>')
        escaped = escaped.replace('&lt;/' + tag + '&gt;', '</' + tag + '>')
    return escaped


def _selection(lead, candidates, dates, config):
    """Keep the weekly lead, then editorial variety, then newest eligible reads."""
    carousel = config.get('carousel', {})
    ordered = [lead] + carousel.get('additional_keys', [])
    ordered += sorted(candidates, key=lambda key: (-dates[key].toordinal(), key))
    selected = []
    for key in ordered:
        if key in candidates and key not in selected:
            selected.append(key)
        if len(selected) == carousel.get('limit', 5):
            break
    return selected


def _slide_id(upcoming, index):
    return f'weekly-slide-{"next" if upcoming else "current"}-{index}'


def _render_slide(root, key, index, count, lang, descriptors, history, config, upcoming):
    label, title, description = descriptors[lang][key]
    copy = config.get('articles', {}).get(key, {}).get(lang, {})
    title = copy.get('title') or title
    category = copy.get('category') or (
        ('ব্যক্তিত্ব' if lang == 'bn' else 'People') if key.startswith('person-') else
        ('পাঠ ও অনুবাদ' if lang == 'bn' else 'Translations') if key.startswith('translation-') else label)
    link_label = copy.get('link_label') or (
        ('জীবনকথা পড়ুন' if lang == 'bn' else 'Read the story') if key.startswith('person-') else
        ('লেখাটি পড়ুন' if lang == 'bn' else 'Read the article'))
    updated_label = 'হালনাগাদ' if lang == 'bn' else 'Updated'
    updated = history[f'{lang}/{key}']['updated']
    media = _media(root, key, lang)
    if media and copy.get('image_credit'):
        # A short homepage credit links to the article's complete source caption.
        credit = (f'<figcaption><a href="{key}.html">'
                  f'{escape(copy["image_credit"])}</a></figcaption>')
        media = re.sub(r'<figcaption>.*?</figcaption>', lambda _: credit,
                       media, count=1, flags=re.S)
    no_media = ' weekly-feature-no-media' if not media else ''
    position = (f'{num(count, lang)}টির মধ্যে {num(index + 1, lang)}' if lang == 'bn'
                else f'{index + 1} of {count}')
    hidden = ' hidden' if index else ''
    return (
        f'<article class="weekly-feature-slide{no_media}" data-feature-slide '
        f'data-feature-key="{key}" id="{_slide_id(upcoming, index)}" role="group" '
        f'aria-roledescription="slide" aria-label="{escape(position + " — " + title, quote=True)}"{hidden}>'
        f'<p class="weekly-feature-updated">{updated_label} '
        f'<time datetime="{updated}">{display_date(updated, lang)}</time></p>'
        f'<div class="weekly-feature-grid">{media}<div class="weekly-feature-copy">'
        f'<p class="weekly-feature-category">{escape(category)}</p>'
        f'<h3 class="weekly-feature-title"><a href="{key}.html">{escape(title)}</a></h3>'
        f'<p class="weekly-feature-intro">{_intro(copy.get("intro_html", description))}</p>'
        f'<a class="weekly-feature-link button" href="{key}.html">{escape(link_label)} '
        '<span aria-hidden="true">→</span></a></div></div></article>')


def _render_controls(keys, lang, descriptors, config, upcoming):
    previous = 'আগের লেখা' if lang == 'bn' else 'Previous article'
    following = 'পরের লেখা' if lang == 'bn' else 'Next article'
    dots = []
    for index, key in enumerate(keys):
        title = (config.get('articles', {}).get(key, {}).get(lang, {}).get('title')
                 or descriptors[lang][key][1])
        label = title + ' দেখুন' if lang == 'bn' else 'Show ' + title
        selected = 'true' if index == 0 else 'false'
        dots.append(
            '<button class="weekly-feature-dot" type="button" '
            f'data-feature-dot="{index}" aria-label="{escape(label, quote=True)}" '
            f'aria-controls="{_slide_id(upcoming, index)}" aria-pressed="{selected}">'
            f'<span class="sr-only">{num(index + 1, lang)}</span></button>')
    return (
        '<div class="weekly-feature-controls" data-feature-controls hidden>'
        '<button class="weekly-feature-control" type="button" data-feature-prev '
        f'aria-label="{previous}"><span aria-hidden="true">←</span></button>'
        f'<div class="weekly-feature-dots">{"".join(dots)}</div>'
        f'<span class="weekly-feature-counter" data-feature-counter>{num(1, lang)} / {num(len(keys), lang)}</span>'
        '<button class="weekly-feature-control" type="button" data-feature-next '
        f'aria-label="{following}"><span aria-hidden="true">→</span></button>'
        '<span class="sr-only weekly-feature-status" data-feature-status role="status" aria-live="polite"></span></div>')


def _render(root, keys, week, lang, descriptors, history, config, upcoming=False):
    heading = 'weekly-feature-next-heading' if upcoming else 'weekly-feature-heading'
    section_label = 'এই সপ্তাহের নির্বাচিত পাঠ' if lang == 'bn' else 'Featured this week'
    carousel_label = 'নির্বাচিত লেখা' if lang == 'bn' else 'Featured articles'
    interval = config.get('carousel', {}).get('interval_ms', 7000)
    slides = ''.join(_render_slide(root, key, index, len(keys), lang, descriptors,
                                   history, config, upcoming)
                     for index, key in enumerate(keys))
    return (
        f'<section class="weekly-feature" aria-labelledby="{heading}" '
        f'data-weekly-feature-key="{keys[0]}" data-weekly-feature-week="{week}" '
        f'data-carousel-interval="{interval}" data-carousel-label="{carousel_label}">'
        '<header class="weekly-feature-topline">'
        f'<h2 class="weekly-feature-label" id="{heading}">{section_label}</h2></header>'
        f'<div class="weekly-feature-slides" data-feature-slides>{slides}</div>'
        f'{_render_controls(keys, lang, descriptors, config, upcoming)}</section>')


def _save_state(path, state):
    text = json.dumps(state, ensure_ascii=False, indent=2) + '\n'
    if path.exists() and path.read_text(encoding='utf-8') == text:
        return
    temporary = None
    try:
        with NamedTemporaryFile('w', encoding='utf-8', dir=path.parent,
                                prefix='.weekly-feature-', suffix='.json', delete=False) as output:
            temporary = Path(output.name)
            output.write(text)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def prepare_weekly_feature(root, history_pages, descriptors_by_lang, today=None):
    """Return {en: HTML, bn: HTML}; save current/next selections atomically.

    Pass PageHistory.data['pages'] after updating all article dates and bilingual
    descriptor lists of (key, label, title, description). A key-to-three-tuple
    descriptor mapping is also accepted. `today` is injectable for date tests.
    """
    root = Path(root).resolve()
    today = _day(today) if today is not None else datetime.now(INDIA).date()
    week = _week(today)
    next_day = _day(week) + timedelta(days=7)
    config = _read_config(root)
    descriptors = {lang: _descriptors(descriptors_by_lang[lang]) for lang in EDITIONS}
    excluded = EXCLUDED | set(config.get('excluded_keys', []))
    candidates = (set(descriptors['en']) & set(descriptors['bn'])) - excluded
    candidates = {key for key in candidates if re.fullmatch(KEY_PATTERN, key) and
                  all(f'{lang}/{key}' in history_pages for lang in EDITIONS)}
    dates = {key: max(_day(history_pages[f'{lang}/{key}']['updated']) for lang in EDITIONS)
             for key in candidates}
    candidates = {key for key in candidates if dates[key] <= today}
    if not candidates:
        raise ValueError('No eligible bilingual articles for the weekly feature')
    state_path = root / 'content/weekly-feature-state.json'
    previous = _read_state(state_path)
    if previous and previous['current']['week'] > week:
        raise ValueError('Current date precedes the recorded weekly feature')
    current = _override(config, today, candidates)
    if current is None and previous:
        effective = previous['next'] if previous['next']['week'] <= week else previous['current']
        if effective['key'] in candidates:
            current = effective['key']
    if current is None:
        current = _newest(candidates, dates)
    upcoming = _override(config, next_day, candidates) or _newest(candidates, dates, current)
    state = {'version': 1, 'current': {'week': week, 'key': current},
             'next': {'week': next_day.isoformat(), 'key': upcoming}}
    current_keys = _selection(current, candidates, dates, config)
    upcoming_keys = _selection(upcoming, candidates, dates, config)
    result = {}
    for lang in EDITIONS:
        result[lang] = (
            _render(root, current_keys, week, lang, descriptors, history_pages, config) +
            f'<template data-weekly-feature-next="{next_day.isoformat()}">' +
            _render(root, upcoming_keys, next_day.isoformat(), lang, descriptors,
                    history_pages, config, upcoming=True) + '</template>')
    _save_state(state_path, state)
    return result
