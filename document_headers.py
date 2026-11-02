"""Quiet page headers built from the collection's unaltered document scans."""
from html import escape
from pathlib import Path
from asset_paths import is_local_asset
import json

ROOT = Path(__file__).resolve().parent

# Dimensions are those of the existing source files; no derivative images are made.
DIMENSIONS = {
    'assets/volume-1-cover.jpg': (1404, 2004),
    'assets/volume-1-contents.jpg': (1404, 1998),
    'assets/books/rajput-title.jpg': (638, 878),
    'assets/books/rajput-foreword.jpg': (798, 1098),
    'assets/books/rajput-publishers-note-1.jpg': (638, 878),
    'assets/books/prabasi-498.jpg': (1920, 2547),
    'assets/scans/v1-003.jpg': (1900, 1213),
    'assets/scans/v1-009.jpg': (1900, 1213),
    'assets/scans/v2-001.jpg': (1900, 1213),
}

COLLECTION_HEADERS = {
    'archives': {
        'file': 'assets/volume-1-cover.jpg',
        'title': ('The journal’s title page', 'পত্রিকার নামপত্র'),
        'detail': ('Ugrakshatriya-Pratinidhi · Volume 1', 'উগ্রক্ষত্রিয়-প্রতিনিধি · প্রথম খণ্ড'),
        'alt': ('Original Bengali title page of Ugrakshatriya-Pratinidhi, volume 1, with handwritten labels and library stamps.',
                'উগ্রক্ষত্রিয়-প্রতিনিধির প্রথম খণ্ডের মূল বাংলা নামপত্র; হাতে লেখা চিরকুট ও গ্রন্থাগারের সিলসহ।'),
        'link': 'archives.html?volume=1&scan=1#reader',
        'link_text': ('Enter the journal reader', 'পত্রিকার পাঠক খুলুন'),
    },
    'translations': {
        'file': 'assets/books/rajput-foreword.jpg',
        'title': ('The author’s own words', 'লেখকের নিজের কথা'),
        'detail': ('Rajput O Ugrakshatriya · Foreword, PDF scan 9', 'রাজপুত ও উগ্রক্ষত্রিয় · মুখবন্ধ, পিডিএফ স্ক্যান ৯'),
        'alt': ('The original Bengali foreword to Rajput O Ugrakshatriya, with Haricharan Bandhu’s printed name.',
                'রাজপুত ও উগ্রক্ষত্রিয়ের মূল বাংলা মুখবন্ধ, হরিচরণ বন্ধুর মুদ্রিত নামসহ।'),
        'link': 'translation-rajput-authors-foreword.html',
        'link_text': ('Read the English translation', 'মূল পাঠ ও অনুবাদ পড়ুন'),
    },
    'bibliography': {
        'file': 'assets/volume-1-contents.jpg',
        'title': ('A journal’s contents', 'পত্রিকার সূচিপত্র'),
        'detail': ('Ugrakshatriya-Pratinidhi · Volume 1', 'উগ্রক্ষত্রিয়-প্রতিনিধি · প্রথম খণ্ড'),
        'alt': ('Original Bengali contents page from volume 1 of Ugrakshatriya-Pratinidhi.',
                'উগ্রক্ষত্রিয়-প্রতিনিধির প্রথম খণ্ডের মূল বাংলা সূচিপত্র।'),
        'link': 'archives.html?volume=1&scan=2#reader',
        'link_text': ('Explore the journal', 'পত্রিকা দেখুন'),
    },
    'book-rajput-o-ugrakshatriya': {
        'file': 'assets/books/rajput-title.jpg',
        'title': ('The original title page', 'মূল নামপত্র'),
        'detail': ('Rajput O Ugrakshatriya · Second edition, 1940', 'রাজপুত ও উগ্রক্ষত্রিয় · দ্বিতীয় সংস্করণ, ১৯৪০'),
        'alt': ('Original Bengali title page of Haricharan Bandhu’s Rajput O Ugrakshatriya, second edition.',
                'হরিচরণ বন্ধুর রাজপুত ও উগ্রক্ষত্রিয়ের দ্বিতীয় সংস্করণের মূল বাংলা নামপত্র।'),
        'link': 'assets/documents/Rajput_O_Ugrakshatriya_1940.pdf#page=4',
        'link_text': ('Open the Bengali book', 'বাংলা বই খুলুন'),
    },
}

TRANSLATION_LOCATIONS_BN = {
    'rajput-authors-foreword': 'পিডিএফ স্ক্যান ৯ · সম্পূর্ণ মুখবন্ধ',
    'rajput-publishers-note': 'পিডিএফ স্ক্যান ৭ · প্রথম পাতা',
    'editors-address-opening': 'প্রথম খণ্ড · মুদ্রিত পৃষ্ঠা ১ · স্ক্যান ৩, ডান পাতা',
    'journal-autobiography': 'দ্বিতীয় খণ্ড · মুদ্রিত পৃষ্ঠা ১ · স্ক্যান ১, ডান পাতা',
    'electricity': 'প্রথম খণ্ড · মুদ্রিত পৃষ্ঠা ১২ · স্ক্যান ৯, বাঁ পাতা',
    'prabasi-book-review': 'মুদ্রিত পৃষ্ঠা ৪৭০ · স্ক্যান ৪৯৮ · ডান স্তম্ভের নীচের অংশ',
}


def document_heading(key, copy, lang):
    """Return a document-led header, or None for pages outside the collection."""
    language_index = 1 if lang == 'bn' else 0
    select = lambda values: values[language_index]
    item = COLLECTION_HEADERS.get(key)
    source_title_lang = lang
    if key.startswith('translation-'):
        slug = key.removeprefix('translation-')
        # Only registered translations use this header, leaving new content explicit.
        if slug not in TRANSLATION_LOCATIONS_BN:
            return None
        article = json.loads((ROOT / 'content/translations' / (slug + '.json')).read_text())
        first = article['blocks'][0]
        item = {
            'file': first['image'],
            'title': (article['bengaliTitle'], article['bengaliTitle']),
            'detail': (first['location'], TRANSLATION_LOCATIONS_BN[slug]),
            'alt': (f'Bengali source scan for “{article["title"]}”; {first["location"]}.',
                    f'“{article["bengaliTitle"]}”-এর মূল বাংলা স্ক্যান; {TRANSLATION_LOCATIONS_BN[slug]}।'),
            'link': first.get('reader', ''),
            'link_text': ('Open in the journal reader', 'পত্রিকার পাঠক খুলুন'),
        }
        source_title_lang = 'bn'
    if item is None:
        return None

    asset = item['file']
    if not is_local_asset(ROOT, asset):
        raise ValueError(f'Missing document header source: {asset}')
    width, height = DIMENSIONS[asset]
    orientation = ' document-folio-landscape' if width > height else ''
    label = select(('From the original', 'মূল উৎস থেকে'))
    enlarge = select(('Enlarge original', 'মূল পাতা বড় করে দেখুন'))
    additional_link = ''
    if item.get('link'):
        additional_link = (f'<a href="{escape(item["link"], quote=True)}">'
                           f'{escape(select(item["link_text"]))} <span aria-hidden="true">↗</span></a>')
    figure = (
        f'<figure class="document-folio{orientation}">'
        f'<p class="document-folio-label">{label}</p>'
        f'<a class="document-folio-mount" href="{escape(asset, quote=True)}" '
        f'aria-label="{escape(enlarge + ": " + select(item["title"]), quote=True)}">'
        f'<img src="{escape(asset, quote=True)}" alt="{escape(select(item["alt"]), quote=True)}" '
        f'width="{width}" height="{height}" fetchpriority="high" decoding="async"></a>'
        f'<figcaption><strong lang="{source_title_lang}">{escape(select(item["title"]))}</strong>'
        f'<span class="document-folio-detail">{escape(select(item["detail"]))}</span>'
        f'<span class="document-folio-links"><a href="{escape(asset, quote=True)}">'
        f'{enlarge} <span aria-hidden="true">↗</span></a>{additional_link}</span>'
        '</figcaption></figure>'
    )
    return (f'<div class="page-heading page-heading-document"><div class="page-heading-copy">'
            f'{copy}</div>{figure}</div>')
