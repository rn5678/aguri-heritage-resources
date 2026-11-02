"""Production homepage shell for the approved bilingual public-history design.

The editable editorial body stays in content/index.html and content/bn/index.html.
Shared metadata, search, attribution, notifications and page counts are supplied by
build.py; this module changes only the homepage presentation.
"""
from pathlib import Path
import hashlib
import re

ROOT = Path(__file__).resolve().parent

CHROME = {
    'en': (
        '''<a class="skip" href="#main">Skip to content</a>
<div class="edition"><div class="wrap"><span class="edition-text">An independent community heritage project</span><div class="languages"><a lang="en" hreflang="en" data-language-switch href="index.html?lang=en" aria-current="page">English</a><span aria-hidden="true">/</span><a lang="bn" hreflang="bn" data-language-switch href="bn/index.html">বাংলা</a></div></div></div>
<header class="header"><div class="wrap header-inner"><a class="brand" href="index.html"><span class="brand-mark" aria-hidden="true">অ</span><span><span class="brand-name">Aguri Heritage</span><small>Ugra Kshatriya · West Bengal</small></span></a><div class="home-header-actions"><button type="button" class="search-open" aria-label="Search" aria-haspopup="dialog"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="10" cy="10" r="6.5"/><path d="m15 15 6 6"/></svg><span>Search</span></button><button type="button" class="menu" aria-expanded="false" aria-controls="navigation">Menu ☰</button></div><nav class="nav" id="navigation" aria-label="Main navigation"><a href="history.html">History</a><a href="culture.html">Culture</a><a href="geography.html">Places</a><a href="people.html">People</a><a href="surnames.html">Surnames</a><a href="bibliography.html">Resources</a><a class="contribute-nav" href="contribute.html">Contribute ↗</a></nav></div></header>''',
        '''<footer class="footer"><div class="wrap"><div class="footer-top"><div><a class="footer-brand" href="index.html">Aguri Heritage</a><p>People, families and the places they call home.</p></div><nav class="footer-links" aria-label="Footer"><a href="about.html">About the project</a><a href="archives.html">The archive</a><a href="contact.html">Contact Us</a><a href="contribute.html">Contribute</a><a href="about.html#editorial">Editorial approach</a><a href="contributor-terms.html">Contributor terms</a></nav></div><!-- homepage-notifications --><div class="footer-bottom"><span>© 2026 Aguri Heritage. Original project material: all rights reserved.</span><a href="rights.html">Rights & reuse · Individual items retain their own rights</a></div></div></footer>''',
    ),
    'bn': (
        '''<a class="skip" href="#main">মূল লেখায় যান</a>
<div class="edition"><div class="wrap"><span class="edition-text">একটি স্বতন্ত্র সমাজের ঐতিহ্য সংরক্ষণ উদ্যোগ</span><div class="languages"><a lang="en" hreflang="en" data-language-switch href="../index.html?lang=en">English</a><span aria-hidden="true">/</span><a lang="bn" hreflang="bn" data-language-switch href="index.html" aria-current="page">বাংলা</a></div></div></div>
<header class="header"><div class="wrap header-inner"><a class="brand" href="index.html"><span class="brand-mark" aria-hidden="true">অ</span><span><span class="brand-name">আগুরী ঐতিহ্য</span><small>উগ্রক্ষত্রিয় · পশ্চিমবঙ্গ</small></span></a><div class="home-header-actions"><button type="button" class="search-open" aria-label="অনুসন্ধান" aria-haspopup="dialog"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="10" cy="10" r="6.5"/><path d="m15 15 6 6"/></svg><span>অনুসন্ধান</span></button><button type="button" class="menu" aria-expanded="false" aria-controls="navigation">মেনু ☰</button></div><nav class="nav" id="navigation" aria-label="প্রধান নেভিগেশন"><a href="history.html">ইতিহাস</a><a href="culture.html">সংস্কৃতি</a><a href="geography.html">স্থান</a><a href="people.html">মানুষ</a><a href="surnames.html">পদবি</a><a href="bibliography.html">তথ্যসূত্র</a><a class="contribute-nav" href="contribute.html">অংশ নিন ↗</a></nav></div></header>''',
        '''<footer class="footer"><div class="wrap"><div class="footer-top"><div><a class="footer-brand" href="index.html">আগুরী ঐতিহ্য</a><p>মানুষ, পরিবার আর তাদের আপন স্থানের গল্প।</p></div><nav class="footer-links" aria-label="পাদলেখ"><a href="about.html">আমাদের কথা</a><a href="archives.html">পত্রিকা সংগ্রহ</a><a href="contact.html">যোগাযোগ করুন</a><a href="contribute.html">অংশ নিন</a><a href="about.html#editorial">সম্পাদনার দৃষ্টিভঙ্গি</a><a href="contributor-terms.html">সহযোগিতার শর্ত</a></nav></div><!-- homepage-notifications --><div class="footer-bottom"><span>© ২০২৬ আগুরী ঐতিহ্য। নিজস্ব প্রকল্পের লেখার সর্বস্বত্ব সংরক্ষিত।</span><a href="rights.html">স্বত্ব ও পুনর্ব্যবহার · পৃথক উপকরণের নিজস্ব অধিকার প্রযোজ্য</a></div></div></footer>''',
    ),
}

def render_homepage(body, fragment, page_tools, correction, page_views, updated_markup, lang):
    """Retain the shared services while applying the dedicated homepage shell."""
    assets = '../assets/' if lang == 'bn' else 'assets/'
    head = re.search(r'<head>(.*?)</head>', body, re.S).group(1)
    sheets = []
    for name in ('homepage-public-history.css', 'homepage-carousel.css', 'homepage-services.css'):
        version = hashlib.sha256((ROOT / 'assets' / name).read_bytes()).hexdigest()[:12]
        sheets.append(f'<link rel="stylesheet" href="{assets}{name}?v={version}">')
    head = head.replace(f'<link rel="stylesheet" href="{assets}style.css">', ''.join(sheets))
    version = hashlib.sha256((ROOT / 'assets/homepage-carousel.js').read_bytes()).hexdigest()[:12]
    head += f'<script src="{assets}homepage-carousel.js?v={version}" defer></script>'
    notification = re.search(r'<section class="notify".*?</section>', body, re.S).group(0)
    dialog = re.search(r'<dialog id="search-dialog".*?</dialog>', body, re.S).group(0)
    header, footer = CHROME[lang]
    footer = footer.replace('<!-- homepage-notifications -->', notification)
    label = 'Page information and contributions' if lang == 'en' else 'পাতার তথ্য ও সহযোগিতা'
    utilities = (f'<section class="homepage-utilities" aria-label="{label}">'
                 f'<div class="homepage-page-information">{updated_markup}{page_tools}{page_views}</div>'
                 f'{correction}</section>')
    return (f'<!DOCTYPE html>\n<html lang="{lang}"><head>{head}</head>'
            f'<body data-page="index" data-assets="{assets}">{header}'
            f'<main id="main" class="wrap">{fragment}{utilities}</main>{footer}{dialog}</body></html>')
