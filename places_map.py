"""A source-grounded schematic orientation for the Places page."""
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def places_heading(key, copy, lang):
    """Render the Places heading; return None for all other pages."""
    if key != 'geography':
        return None
    if lang not in ('en', 'bn'):
        raise ValueError(f'Unsupported map language: {lang}')
    asset = f'assets/maps/bardhaman-orientation-{lang}.svg'
    svg = (ROOT / asset).read_text()
    if lang == 'bn':
        title = 'নদীর সূত্রে, স্থানের পরিচয়'
        caption = 'জেলার সরকারি মানচিত্র অনুসারে সরলীকৃত বিন্যাস। নির্দিষ্ট মাপে আঁকা নয়; প্রশাসনিক বা সমাজের বসতির সীমানা দেখানো হয়নি।'
        open_map = 'বড় করে মানচিত্র দেখুন'
        source = 'সরকারি মানচিত্র'
    else:
        title = 'A landscape connected by rivers'
        caption = 'A simplified orientation drawn from official district maps. Not to scale; no administrative or community settlement boundaries are shown.'
        open_map = 'Open full-size map'
        source = 'Official district maps'
    return (
        '<div class="page-heading page-heading-map"><div class="page-heading-copy">'
        f'{copy}</div><figure class="places-map">{svg}'
        f'<figcaption><strong>{escape(title)}</strong><span>{escape(caption)}</span>'
        '<div class="places-map-links">'
        f'<a href="{asset}">{escape(open_map)} ↗</a>'
        f'<a href="https://purbabardhaman.nic.in/map-of-district/">{escape(source)} ↗</a>'
        '</div></figcaption></figure></div>'
    )
