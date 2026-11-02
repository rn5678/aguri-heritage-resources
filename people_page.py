"""Turn the existing People header selection into the shared story carousel.

Biography copy and portraits come from the authored profiles. The entire
collection, linked introduction and original clickable credits stay in place.
"""
from pathlib import Path
from html.parser import HTMLParser
import hashlib
import re

from history_hero import LABELS, carousel_markup
from portrait_headers import COLLECTION_SELECTION, PROFILE_PATTERN, authored_portraits
from profile_pages import Text
from localization import STANDALONE_PROFILE_KEYS

ROOT = Path(__file__).resolve().parent
LABEL_OVERRIDES = {
    'en': {'all': 'All biographies below', 'read': 'Read the biography',
           'previous': 'Previous biography', 'next': 'Next biography',
           'show': 'Show biography', 'controls': 'Biography controls'},
    'bn': {'all': 'নিচে সব জীবনকথা দেখুন', 'read': 'জীবনকথা পড়ুন',
           'previous': 'আগের জীবনকথা', 'next': 'পরের জীবনকথা',
           'show': 'জীবনকথা দেখুন', 'controls': 'জীবনকথা দেখার নিয়ন্ত্রণ'},
}


def plain(html):
    # Preserve punctuation around inline emphasis and links. Removing only the
    # citation markers leaves the complete cited paragraph below.
    html = re.sub(r'<sup class="citation">.*?</sup>', '', html, flags=re.S)
    text = ''.join(Text(re.sub(r'\[cite:[\w-]+\]', '', html)).parts)
    return ' '.join(text.split())


class PortraitImage(HTMLParser):
    def __init__(self, figure):
        super().__init__(convert_charrefs=True)
        self.images = []
        self.feed(figure)
        if len(self.images) != 1:
            raise ValueError('People carousel: expected one documentary portrait')

    def handle_starttag(self, tag, attrs):
        if tag == 'img':
            self.images.append(dict(attrs))


def _population_sources_to_notes(body):
    """Keep the collection's manual a/b sources in its existing notes panel."""
    source_ids = ('people-population-source-a', 'people-population-source-b')
    counts = [body.count('id="' + source_id + '"') for source_id in source_ids]
    if counts == [0, 0]:
        return body  # Older authored collections do not have the population note.
    if any(count > 1 for count in counts):
        raise ValueError('People population sources: duplicate source anchor')
    paragraphs = []
    for source_id in source_ids:
        pattern = r'<p\b[^>]*\bid="' + source_id + r'"[^>]*>.*?</p>'
        matches = list(re.finditer(pattern, body, re.S))
        if not matches:
            continue  # An editor deletion retains an inert anchor, not a paragraph.
        paragraph = matches[0].group()
        classes = re.search(r'\bclass="([^"]*)"', paragraph.split('>', 1)[0])
        if not classes or 'small' not in classes[1].split():
            raise ValueError('People population sources: expected a small source paragraph')
        paragraphs.append(paragraph)
    pattern = r'<details class="notes" aria-labelledby="notes-heading">.*?</details>'
    panels = list(re.finditer(pattern, body, re.S))
    if not paragraphs or not panels:
        return body
    if len(panels) != 1 or panels[0].group().count('</ol>') != 1:
        raise ValueError('People population sources: expected one existing numbered notes panel')
    for paragraph in paragraphs:
        body = body.replace(paragraph, '', 1)
    panels = list(re.finditer(pattern, body, re.S))
    panel = panels[0]
    replacement = panel.group().replace('</ol>', '</ol>' + ''.join(paragraphs), 1)
    return body[:panel.start()] + replacement + body[panel.end():]


def render_people(body, lang):
    body = _population_sources_to_notes(body)
    source = (ROOT / 'content' / ('bn' if lang == 'bn' else '') / 'people.html').read_text()
    profiles = dict(re.findall(PROFILE_PATTERN, source, re.S))
    portraits = authored_portraits(lang)
    cards = []
    images = {}
    for slug in COLLECTION_SELECTION:
        profile = profiles.get(slug)
        portrait = portraits.get(slug)
        if not profile or not portrait or not portrait['name'] or not re.search(r'<img\b',portrait['figure']):
            continue
        copy = re.search(r'<div\b[^>]*class="person-copy"[^>]*>(.*)</div>\s*$', profile, re.S).group(1)
        summary = re.search(r'<p\b(?![^>]*\bclass=)[^>]*>(.*?)</p>', copy, re.S)
        kicker = re.search(r'<p\b[^>]*class="eyebrow"[^>]*>(.*?)</p>', copy, re.S)
        key = 'person-' + slug
        cards.append({'title': plain(portrait['name']), 'kicker': plain(kicker.group(1)) if kicker else '',
                      'summary': plain(summary.group(1)) if summary else '', 'link': {'href': key + '.html'}})
        figure = portraits[slug]['figure']
        image = PortraitImage(figure).images[0]
        caption_match = re.search(r'<figcaption\b[^>]*>(.*?)</figcaption>', figure, re.S)
        caption = caption_match.group(1) if caption_match else ''
        asset = image['src']
        # Some Bengali profiles already use edition-relative asset URLs.
        # The shared carousel validates a project-relative path and adds its
        # own Bengali prefix, so normalize only that established local form.
        if lang == 'bn' and asset.startswith('../assets/'):
            asset = asset[3:]
        images[key] = {'file': asset, 'width': int(image['width']),
                       'height': int(image['height']), 'image_fit': 'contain',
                       'alt_' + lang: image['alt'], 'caption_' + lang: plain(caption)}
    label = 'Explore the biographies' if lang == 'en' else 'জীবনকথা পড়ুন'
    hero = carousel_markup(cards, label, lang, images,
                           {**LABELS[lang], **LABEL_OVERRIDES[lang]},
                           'people-hero', 'people-biographies')
    # The existing gallery's source/rights disclosure is a sibling of the
    # carousel, so its links remain clickable without nested biography links.
    body, count = re.subn(r'<div class="people-heading-portraits">.*?</div>',
                         lambda _: hero, body, count=1, flags=re.S)
    if count != 1:
        raise ValueError('People carousel: expected the existing featured portrait gallery')
    collection = '<div class="person-profiles">'
    if body.count(collection) != 1 or 'id="people-biographies"' in body:
        raise ValueError('People carousel: expected one unambiguous biography collection')
    summaries = []
    if lang in ('en', 'bn'):
        for key in sorted(STANDALONE_PROFILE_KEYS):
            slug = key.removeprefix('person-')
            suffix = '.summary.bn.html' if lang == 'bn' else '.summary.html'
            path = ROOT / 'content/profiles' / (slug + suffix)
            if not path.is_file():
                continue
            summary = path.read_text().strip()
            pattern = r'<article class="person-profile" aria-labelledby="' + re.escape(slug) + r'">.*?</article>'
            if (not re.fullmatch(pattern, summary, re.S) or
                    summary.count('<h2 id="' + slug + '">') != 1 or
                    summary.count('href="' + key + '.html"') != 1 or
                    'id="' + slug + '"' in body):
                raise ValueError('People collection: invalid ' + lang + ' standalone summary for ' + key)
            summaries.append(summary)
    body = body.replace(collection, '<div class="person-profiles" id="people-biographies">', 1)
    if summaries:
        existing = list(re.finditer(PROFILE_PATTERN, body, re.S))
        if not existing or existing[-1].start() < body.index('id="people-biographies"'):
            raise ValueError('People collection: expected existing biographies before summaries')
        position = existing[-1].end()
        body = body[:position] + ''.join(summaries) + body[position:]
    assets = '../assets/' if lang == 'bn' else 'assets/'
    extra = ''
    for filename in ('history-hero.css', 'people-carousel.css', 'history-hero.js'):
        version = hashlib.sha256((ROOT / 'assets' / filename).read_bytes()).hexdigest()[:12]
        url = f'{assets}{filename}?v={version}'
        extra += (f'<script src="{url}" defer></script>' if filename.endswith('.js') else
                  f'<link rel="stylesheet" href="{url}">')
    if body.count('</head>') != 1:
        raise ValueError('People carousel: expected one document head')
    return body.replace('</head>', extra + '</head>', 1)
