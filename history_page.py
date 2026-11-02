"""History page shell for the chronology-first public-history design (13 October 2026).

The editorial body stays in content/history.html and content/bn/history.html. build.py
still supplies metadata, search, citations, notes, sharing and page counts; this module
swaps in the homepage header and footer so History matches Home, sets the title in the
homepage's two-tone style and adds the page's own stylesheet and script. The layout is
the approved "Option B — Through time" design; see the README section of the same date.
"""
from pathlib import Path
import hashlib
import re

from homepage import CHROME
from history_hero import render_hero

ROOT = Path(__file__).resolve().parent
# The part of each title set in the accent colour, matching the homepage hero.
TITLES = {
    'en': ('The Aguris through history', '<span class="title-line">The Aguris</span> <em>through history</em>'),
    'bn': ('ইতিহাসের পথে আগুরীরা', '<em>ইতিহাসের পথে</em> <span class="title-line">আগুরীরা</span>'),
}
LANGUAGE_LINKS = {
    'en': (('data-language-switch href="index.html?lang=en"', 'data-language-switch href="history.html"'),
           ('data-language-switch href="bn/index.html"', 'data-language-switch href="bn/history.html"')),
    'bn': (('data-language-switch href="../index.html?lang=en"', 'data-language-switch href="../history.html"'),
           ('data-language-switch href="index.html"', 'data-language-switch href="history.html"')),
}


def _version(name):
    return hashlib.sha256((ROOT / 'assets' / name).read_bytes()).hexdigest()[:12]


def _replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f'History page shell: expected exactly one {old!r}')
    return text.replace(old, new)


def chrome(lang):
    """The homepage header and footer, pointed at the History page in each edition."""
    header, footer = CHROME[lang]
    for old, new in LANGUAGE_LINKS[lang]:
        header = _replace_once(header, old, new)
    header = _replace_once(header, '<a href="history.html">', '<a href="history.html" aria-current="page">')
    return header, footer


def render_history(body, lang):
    """Apply the homepage shell while retaining every shared service from build.py."""
    assets = '../assets/' if lang == 'bn' else 'assets/'
    header, footer = chrome(lang)
    notification = re.search(r'<section class="notify".*?</section>', body, re.S).group(0)
    footer = footer.replace('<!-- homepage-notifications -->', notification)
    body, headers = re.subn(r'<a class="skip-link" href="#main">.*?</header>', lambda _: header, body, count=1, flags=re.S)
    body, footers = re.subn(r'<footer class="site-footer">.*?</footer>', lambda _: footer, body, count=1, flags=re.S)
    if headers != 1 or footers != 1:
        raise ValueError('History page shell: shared header or footer not found')
    plain, styled = TITLES[lang]
    # A retitled page keeps a plain heading rather than failing the build.
    body = body.replace(f'<h1>{plain}</h1>', f'<h1>{styled}</h1>', 1)
    body = render_hero(body, lang)
    anchor = f'<script src="{assets}parent-guides.js" defer></script>'
    extra = (f'<link rel="stylesheet" href="{assets}history-page.css?v={_version("history-page.css")}">'
             f'<script src="{assets}history-page.js?v={_version("history-page.js")}" defer></script>'
             f'<link rel="stylesheet" href="{assets}history-hero.css?v={_version("history-hero.css")}">'
             f'<script src="{assets}history-hero.js?v={_version("history-hero.js")}" defer></script>')
    return _replace_once(body, anchor, anchor + extra)
