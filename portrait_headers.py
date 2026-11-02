"""Documentary biography headings drawn from the authored, credited profiles."""
from functools import lru_cache
from html import escape, unescape
from pathlib import Path
import json
import re
from localization import STANDALONE_PROFILE_KEYS

ROOT = Path(__file__).resolve().parent
PROFILE_PATTERN = r'<article\b(?=[^>]*\bclass="person-profile")(?=[^>]*\baria-labelledby="([^"]+)")[^>]*>(.*?)</article>'
PHOTO_PATTERN = r'<figure\b(?=[^>]*\bclass="person-photo")[^>]*>.*?</figure>'
COLLECTION_SELECTION = (
    'ajit-kumar-panja', 'shakti-samanta', 'ramapada-chowdhury',
    'jadabendra-nath-panja', 'ganapati-panja', 'hare-krishna-konar',
    'satya-kinkar-sahana',
)


def profile_name_heading(slug, body, opening=''):
    """A remaining section heading cannot replace a deliberately removed name."""
    explicit = re.search(r'<h2\b(?=[^>]*\bid="' + re.escape(slug) + r'")[^>]*>(.*?)</h2>', body, re.S)
    if explicit or re.search(r'\bdata-editor-title="[^"]+"', opening):
        return explicit
    return re.search(r'<h2\b[^>]*>(.*?)</h2>', body, re.S)


@lru_cache(maxsize=2)
def authored_portraits(lang):
    """Keep the authored alt text, full captions, links and qualifications intact."""
    if lang not in ('en', 'bn'):
        raise ValueError(f'Unsupported portrait language: {lang}')
    source = ROOT / 'content' / ('bn' if lang == 'bn' else '') / 'people.html'
    entries = {}
    for match in re.finditer(PROFILE_PATTERN, source.read_text(), re.S):
        slug, body = match.group(1, 2)
        photo = re.search(PHOTO_PATTERN, body, re.S)
        name = profile_name_heading(slug, body, match.group(0).split('>', 1)[0])
        entries[slug] = {'figure': photo.group() if photo else '',
                         'name': name.group(1) if name else ''}
    return entries


def _eager_image(figure):
    def image(match):
        tag = re.sub(r'\s+(?:loading|decoding|fetchpriority)="[^"]*"', '', match.group())
        return tag[:-1] + ' loading="eager" decoding="async">'
    return re.sub(r'<img\b[^>]*>', image, figure)


def _collection_heading(copy, lang, entries):
    gallery = []
    credits = []
    for slug in COLLECTION_SELECTION:
        item = entries.get(slug)
        if not item or not item['name']:
            continue
        image = re.search(r'<img\b[^>]*>', item['figure'])
        if not image:
            continue
        image = image.group()
        caption_match = re.search(r'<figcaption\b[^>]*>(.*?)</figcaption>', item['figure'], re.S)
        caption = caption_match.group(1) if caption_match else ''
        gallery.append(
            f'<figure class="people-heading-portrait"><a href="person-{slug}.html">'
            f'<span class="people-heading-mount">{_eager_image(image)}</span></a>'
            f'<figcaption>{item["name"]}</figcaption></figure>')
        if caption:
            credits.append(f'<p><strong>{item["name"]}.</strong> {caption}</p>')
    label = 'ছবির উৎস ও কৃতিত্ব' if lang == 'bn' else 'Photograph sources & credits'
    disclosure = (f'<details class="people-heading-credits"><summary>{label}</summary>'
                  f'{"".join(credits)}</details>') if credits else ''
    return (
        '<div class="page-heading page-heading-portraits page-heading-people">'
        f'<div class="page-heading-copy">{copy}</div><div class="people-heading-gallery">'
        f'<div class="people-heading-portraits">{"".join(gallery)}</div>'
        f'{disclosure}</div></div>')


def portrait_heading(key, copy, lang):
    """Return a portrait-led heading for People/profiles, otherwise None."""
    if key != 'people' and not key.startswith('person-'):
        return None
    entries = authored_portraits(lang)
    if key == 'people':
        return _collection_heading(copy, lang, entries)
    slug = key.removeprefix('person-')
    if slug not in entries:
        if key in STANDALONE_PROFILE_KEYS:
            if key in _artworks():
                return None
            return '<div class="page-heading page-heading-profile-text">' + copy + '</div>'
        raise ValueError(f'No authored portrait record for {lang}/{key}')
    figure = entries[slug]['figure']
    if '<img ' not in figure:
        status_match = re.search(r'<span\b[^>]*class="portrait-status"[^>]*>(.*?)</span>', figure, re.S)
        caption_match = re.search(r'<figcaption\b[^>]*>(.*?)</figcaption>', figure, re.S)
        status = status_match.group(1) if status_match else ''
        caption = caption_match.group(1) if caption_match else ''
        separator = '। ' if lang == 'bn' else '. '
        parts = [part for part in (status, caption)
                 if re.sub(r'<[^>]*>', '', unescape(part)).strip()]
        note = f'<p class="profile-portrait-status">{separator.join(parts)}</p>' if parts else ''
        return (
            '<div class="page-heading page-heading-profile-text">'
            f'{copy}{note}</div>')
    return (
        '<div class="page-heading page-heading-portraits page-heading-profile">'
        f'<div class="page-heading-copy">{copy}</div>'
        f'<div class="profile-heading-document">{_eager_image(figure)}</div></div>')


@lru_cache(maxsize=1)
def _artworks():
    return json.loads((ROOT / 'assets/page-artworks/catalog.json').read_text())


def profile_secondary_artwork(key, lang):
    """Retain the existing symbolic painting below the documentary biography."""
    item = _artworks().get(key)
    if not item:
        return ''
    caption = item.get('caption_' + lang) or (
        'জীবন ও কর্মের অনুপ্রেরণায় কল্পিত চিত্র' if lang == 'bn' else
        'An illustration inspired by this life and work')
    return (
        '<figure class="profile-secondary-artwork">'
        f'<img src="{escape(item["file"], quote=True)}" alt="" '
        f'width="{item["width"]}" height="{item["height"]}" loading="lazy" decoding="async">'
        f'<figcaption><strong>{escape(item["title_" + lang])}</strong>'
        f'<span>{escape(caption)}</span></figcaption></figure>')
