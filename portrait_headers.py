"""Documentary biography headings drawn from the authored, credited profiles."""
from functools import lru_cache
from html import escape, unescape
from pathlib import Path
import json
import re
from localization import STANDALONE_PROFILE_KEYS

ROOT = Path(__file__).resolve().parent
PROFILE_PATTERN = r'<article class="person-profile" aria-labelledby="([^"]+)">(.*?)</article>'
PHOTO_PATTERN = r'<figure class="person-photo">.*?</figure>'
COLLECTION_SELECTION = (
    'ajit-kumar-panja', 'shakti-samanta', 'ramapada-chowdhury',
    'jadabendra-nath-panja', 'ganapati-panja', 'hare-krishna-konar',
    'satya-kinkar-sahana',
)


@lru_cache(maxsize=2)
def authored_portraits(lang):
    """Keep the authored alt text, full captions, links and qualifications intact."""
    if lang not in ('en', 'bn'):
        raise ValueError(f'Unsupported portrait language: {lang}')
    source = ROOT / 'content' / ('bn' if lang == 'bn' else '') / 'people.html'
    entries = {}
    for slug, body in re.findall(PROFILE_PATTERN, source.read_text(), re.S):
        photo = re.search(PHOTO_PATTERN, body, re.S)
        name = re.search(r'<h2[^>]*>(.*?)</h2>', body, re.S)
        if not photo or not name:
            raise ValueError(f'Incomplete authored profile: {lang}/{slug}')
        entries[slug] = {'figure': photo.group(), 'name': name.group(1)}
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
        item = entries[slug]
        image = re.search(r'<img\b[^>]*>', item['figure']).group()
        caption = re.search(r'<figcaption>(.*?)</figcaption>', item['figure'], re.S).group(1)
        gallery.append(
            f'<figure class="people-heading-portrait"><a href="person-{slug}.html">'
            f'<span class="people-heading-mount">{_eager_image(image)}</span></a>'
            f'<figcaption>{item["name"]}</figcaption></figure>')
        credits.append(f'<p><strong>{item["name"]}.</strong> {caption}</p>')
    label = 'ছবির উৎস ও কৃতিত্ব' if lang == 'bn' else 'Photograph sources & credits'
    return (
        '<div class="page-heading page-heading-portraits page-heading-people">'
        f'<div class="page-heading-copy">{copy}</div><div class="people-heading-gallery">'
        f'<div class="people-heading-portraits">{"".join(gallery)}</div>'
        f'<details class="people-heading-credits"><summary>{label}</summary>'
        f'{"".join(credits)}</details></div></div>')


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
        status = re.search(r'<span class="portrait-status">(.*?)</span>', figure, re.S).group(1)
        caption = re.search(r'<figcaption>(.*?)</figcaption>', figure, re.S).group(1)
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
