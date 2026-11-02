"""Culture's two-article carousel, using the existing History presentation.

The authored English and Bengali cards and article artwork catalog remain the
editorial authority. The original cards stay readable below and in print.
"""
from pathlib import Path
import hashlib
import re

from history_hero import LABELS, Stories, carousel_markup, replace_artwork

ROOT = Path(__file__).resolve().parent
STORY_KEYS = ('aguris-today', 'food-and-village-life')
COLLECTION_ID = 'culture-reading-routes'
LABEL_OVERRIDES = {
    'en': {'all': 'Both articles below', 'read': 'Read the article',
           'previous': 'Previous article', 'next': 'Next article',
           'show': 'Show article', 'controls': 'Article controls'},
    'bn': {'all': 'নিচে দুটি প্রবন্ধ দেখুন', 'read': 'প্রবন্ধটি পড়ুন',
           'previous': 'আগের প্রবন্ধ', 'next': 'পরের প্রবন্ধ',
           'show': 'প্রবন্ধ দেখুন', 'controls': 'প্রবন্ধ দেখার নিয়ন্ত্রণ'},
}


class CultureStories(Stories):
    def handle_starttag(self, tag, attrs):
        # Culture's existing cards use a plain paragraph for their description.
        # Normalize it for the parser only; do not change the authored HTML.
        if self.current is not None and tag == 'p' and not dict(attrs).get('class'):
            attrs = [*attrs, ('class', 'guide-description')]
        super().handle_starttag(tag, attrs)


def render_culture(body, lang, catalog):
    collection = re.search(
        r'<h2 id="culture-reading-routes">.*?</h2>\s*<div class="guide-grid">.*?</div>',
        body, re.S)
    if not collection:
        raise ValueError('Culture carousel: the two-article collection was not found')
    parsed = CultureStories()
    parsed.feed(collection.group(0))
    if tuple(card['link']['href'] for card in parsed.cards) != tuple(key + '.html' for key in STORY_KEYS):
        raise ValueError('Culture carousel: review the two-article inventory before changing it')
    images = {}
    for key in STORY_KEYS:
        images[key] = {**catalog[key], 'image_fit': 'cover'}
        images[key].setdefault('caption_en', 'A contemporary topic illustration')
        images[key].setdefault('caption_bn', 'বিষয়ভিত্তিক কল্পিত চিত্র')
    labels = {**LABELS[lang], **LABEL_OVERRIDES[lang]}
    hero = carousel_markup(parsed.cards, ''.join(parsed.heading).strip(), lang,
                           images, labels, 'culture-hero', COLLECTION_ID)
    body = replace_artwork(body, hero)
    assets = '../assets/' if lang == 'bn' else 'assets/'
    anchor = f'<script src="{assets}parent-guides.js" defer></script>'
    if body.count(anchor) != 1:
        raise ValueError('Culture carousel: expected the parent guide assets once')
    extra = ''
    for filename in ('history-hero.css', 'culture-carousel.css', 'history-hero.js'):
        version = hashlib.sha256((ROOT / 'assets' / filename).read_bytes()).hexdigest()[:12]
        url = f'{assets}{filename}?v={version}'
        extra += (f'<script src="{url}" defer></script>' if filename.endswith('.js') else
                  f'<link rel="stylesheet" href="{url}">')
    return body.replace(anchor, anchor + extra)
