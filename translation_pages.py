"""Render source-aligned reading editions and portable text downloads."""
from html import escape
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parent

def render_translations():
    articles = sorted((json.loads(p.read_text()) for p in
                       (ROOT/'content/translations').glob('*.json')), key=lambda a: a['order'])
    fragments = {}
    descriptors = []
    cards = []
    scan_links = {}
    downloads = ROOT/'assets/translations'
    downloads.mkdir(exist_ok=True)
    sources = json.loads((ROOT/'content/sources.json').read_text())
    for article in articles:
        a = article
        slug = a['slug']
        key = 'translation-' + slug
        url = key + '.html'
        complete = a['scope'].startswith('Complete')
        status = 'Complete selection' if complete else 'Opening extract'
        word_count = sum(len(p.split()) for b in a['blocks'] for p in b['paragraphs'])
        minutes = max(1, round(word_count/200))
        cards.append(f'''<article class="translation-card">
<p class="eyebrow">{escape(a['date'])}</p><span class="evidence-tag{' pending' if not complete else ''}">{status}</span>
<h3><a href="{url}">{escape(a['title'])}</a></h3><p class="translation-bengali" lang="bn">{escape(a['bengaliTitle'])}</p>
<p>{escape(a['description'])}</p><p class="translation-card-source">{escape(a['collection'])}<br>{escape(a['scope'])} · {minutes} min read</p>
<a class="text-link" href="{url}">Read the English translation →</a></article>''')

        english = [a['title'], a['bengaliTitle'], a['author'], a['collection'], a['date'], a['scope'],
                   'Original source: '+sources[a['source']]['url'], '', 'ENGLISH READING TRANSLATION',
                   'Prepared for Aguri Heritage. Compared with source scans; independent language review pending.',
                   '', 'EDITORIAL CONTEXT', a['editorial'], '', 'TRANSLATOR’S NOTES',
                   *[f'{n}. {note}' for n, note in enumerate(a['notes'], 1)], '']
        bengali = [a['bengaliTitle'], a['collection'], a['scope'], '',
                   'BENGALI TRANSCRIPTION COMPARED WITH THE SCANS',
                   'Historical spelling retained where legible; line-end word divisions joined. Independent language review pending.', '']
        sections = []
        for n, b in enumerate(a['blocks'], 1):
            for asset in [b['image']]:
                if not (ROOT/asset).is_file():
                    raise ValueError(f'Missing translation source image: {asset}')
            english += [b['title'], b['location'], 'Source image: '+b['image'], '', *b['paragraphs'], '']
            if b.get('reader'):
                scan_id = Path(b['image']).stem
                scan_links[scan_id] = {'title': a['title'], 'url': url, 'scope': a['scope']}
                scan_reader = f'<a href="{escape(b["reader"],quote=True)}">Open in journal reader ↗</a>'
            else:
                scan_reader = ''
            source = f'''<aside class="translation-source" aria-label="Bengali original for section {n}">
<figure><a href="{escape(b['image'],quote=True)}" aria-label="Enlarge original: {escape(b['location'],quote=True)}"><img src="{escape(b['image'],quote=True)}" alt="Bengali source: {escape(b['location'],quote=True)}" loading="lazy"></a>
<figcaption>{escape(b['location'])}<br><a href="{escape(b['image'],quote=True)}">Enlarge Bengali original ↗</a>{scan_reader}</figcaption></figure></aside>'''
            bn = ''
            if b.get('bengali'):
                bengali += [b['location'], '', *b['bengali'], '']
                bn = '<details class="translation-transcript"><summary>Read the Bengali transcription</summary><div lang="bn">'+''.join(f'<p>{escape(p)}</p>' for p in b['bengali'])+'</div></details>'
            sections.append(f'''<section class="translation-section" aria-labelledby="passage-{n}">
{source}<div class="translation-prose"><p class="translation-location">{escape(b['location'])}</p><h2 id="passage-{n}">{escape(b['title'])}</h2>
{''.join(f'<p>{escape(p)}</p>' for p in b['paragraphs'])}{bn}</div></section>''')
        english_name = slug+'-english.txt'
        (downloads/english_name).write_text('\n\n'.join(english)+'\n')
        links = f'<a href="assets/translations/{english_name}" download>Download English text ↓</a>'
        if a['source']=='rajput-1940':
            links += '<a href="book-rajput-o-ugrakshatriya.html#english-translation">Read the book in English ↗</a><a href="assets/documents/Rajput_O_Ugrakshatriya_1940.pdf">Open the Bengali book PDF ↗</a>'
        if any(b.get('bengali') for b in a['blocks']):
            name = slug+'-bengali.txt'
            (downloads/name).write_text('\n\n'.join(bengali)+'\n')
            links += f'<a href="assets/translations/{name}" download>Download Bengali transcription ↓</a>'
        if a.get('ocr'):
            if not (downloads/a['ocr']).is_file():
                raise ValueError(f'Missing article OCR: {a["ocr"]}')
            links += f'<a href="assets/translations/{escape(a["ocr"],quote=True)}" download>Download uncorrected Bengali OCR ↓</a>'
        fragments[key] = f'''<article class="translation-article">
<div class="translation-intro"><p class="translation-original-title" lang="bn">{escape(a['bengaliTitle'])}</p>
<p class="translation-byline">{escape(a['author'])} · {escape(a['date'])}</p>
<p>{escape(a['collection'])} [cite:{a['source']}]</p>
<p class="translation-scope"><strong>{escape(a['scope'])}</strong><span>{word_count:,} English words · About {minutes} min read</span></p>
<div class="translation-context"><p class="eyebrow">About this translation</p><p>{escape(a['editorial'])}</p>
<p class="translation-review">Reading translation compared with the scans · Independent language review pending</p>
<details class="translation-notes"><summary>Translator’s notes &amp; uncertain readings</summary><ol>{''.join('<li>'+escape(p)+'</li>' for p in a['notes'])}</ol></details></div>
<div class="translation-downloads">{links}</div>
<p class="translation-help">Read the English below; select a source image to examine the Bengali print. Section headings are editorial additions. Scan numbers and printed page numbers are kept separate.</p></div>
{''.join(sections)}
<div class="translation-end"><p>End of this {'selection' if complete else 'opening-page extract'}.</p><a class="text-link" href="translations.html">← Explore all translations</a></div></article>'''
        descriptors.append((key, 'Translations', a['title'], a['description']))

    complete_count = sum(a['scope'].startswith('Complete') for a in articles)
    fragments['translations'] = f'''<div class="translation-collection-intro"><p class="lead">Read the Bengali sources in English.</p>
<p>Explore Aguri heritage through an English translation of <em>Rajput O Ugrakshatriya</em> and selected historical articles, prefaces and a review. Books and periodicals offer different perspectives on community history, education and social life, with the Bengali originals available for comparison.</p>
<div class="translation-collection-count"><span><b>01</b> book translation</span><span><b>{complete_count:02d}</b> complete selections</span><span><b>{len(articles)-complete_count:02d}</b> opening extract</span><span><b>1891–1940</b> original publications</span></div>
<p class="small">“Complete selections” refers to the named articles, review and prefaces. The journal volumes are translated in part. The book translation covers its surviving text; two printed pages are missing from the digitised original.</p></div>
<section class="translated-book-feature" aria-labelledby="translated-book"><div><p class="eyebrow">Historical book · English PDF · 98 pages</p><h2 id="translated-book">Rajputs and Ugra Kshatriyas</h2><p>Haricharan Bandhu’s account of ancestry, the name Agari, Rarh and the Pala and Sena kings. Read all nine chapters and the surviving conclusion, with the prefaces, original errata sheets and a closing translator’s note.</p><p class="small">The gap left by missing Bengali pages 142–143 is marked. Uncertain readings are identified in the translation.</p></div><div class="actions"><a class="button" href="book-rajput-o-ugrakshatriya.html#english-translation">Read the English edition →</a><a class="button secondary" href="assets/documents/Rajputs_and_Ugra_Kshatriyas_English_Translation.pdf" download>Download English PDF ↓</a></div></section>
<section aria-labelledby="translated-readings"><div class="section-heading"><div><p class="eyebrow">Journals &amp; historical books</p><h2 id="translated-readings">Choose a reading</h2></div></div>
<div class="translation-grid">{''.join(cards)}</div></section>
<div class="prose"><h2>English text, Bengali evidence</h2><p>These are reading translations compared with the original scans. The author’s arguments and historical language are retained, with context and uncertain readings identified in the notes. They await an independent language review.</p><p>The two book prefaces include Bengali transcriptions. Selected journal articles have downloadable machine extractions, explicitly labelled as uncorrected OCR. Each reading also has a downloadable English text. The older short notes remain in the <a href="archives.html#reader">journal reader</a>.</p><p>Original historical voices can contain disputed origin theories, dated science or social judgements. Translating those passages makes them available for study; the website does not adopt them as established facts.</p></div>'''
    (ROOT/'assets/translation-links.js').write_text('window.TRANSLATION_LINKS = '+json.dumps(scan_links,ensure_ascii=False)+';\n')
    return fragments, descriptors
