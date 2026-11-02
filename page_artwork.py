"""Render page headers using portraits, original documents, maps and topic artwork."""
from html import escape
from pathlib import Path
from asset_paths import is_local_asset
import json
from document_headers import document_heading
from portrait_headers import portrait_heading
from places_map import places_heading

ROOT = Path(__file__).resolve().parent
CATALOG_PATH = ROOT / 'assets/page-artworks/catalog.json'


def load_catalog():
    catalog = json.loads(CATALOG_PATH.read_text())
    for key, item in catalog.items():
        for field in ('file', 'title_en', 'title_bn', 'alt_en', 'alt_bn', 'width', 'height'):
            if not item.get(field):
                raise ValueError(f'Artwork {key} is missing {field}')
        if not is_local_asset(ROOT, item['file']):
            raise ValueError(f'Artwork {key} has a missing or invalid asset')
    return catalog


def page_heading(key, copy, lang, catalog):
    for render in (portrait_heading, document_heading, places_heading):
        heading = render(key, copy, lang)
        if heading is not None:
            return heading
    item = catalog.get(key)
    if not item:
        raise ValueError(f'No topic artwork for {key}')
    title = escape(item['title_' + lang])
    alt = escape(item['alt_' + lang], quote=True)
    caption = item.get('caption_' + lang)
    if not caption:
        caption = ('জীবন ও কর্মের অনুপ্রেরণায় কল্পিত চিত্র' if lang == 'bn' else
                   'An illustration inspired by this life and work') if key.startswith('person-') else (
                   'বিষয়ভিত্তিক কল্পিত চিত্র' if lang == 'bn' else 'A contemporary topic illustration')
    figure = (f'<figure class="page-artwork"><img src="{escape(item["file"], quote=True)}" '
              f'alt="{alt}" width="{item["width"]}" height="{item["height"]}" '
              f'fetchpriority="high" decoding="async"><figcaption><strong>{title}</strong>'
              f'<span>{escape(caption)}</span></figcaption></figure>')
    return (f'<div class="page-heading page-heading-illustrated"><div class="page-heading-copy">'
            f'{copy}</div>{figure}</div>')
