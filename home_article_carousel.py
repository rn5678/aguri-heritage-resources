"""Homepage discovery of editorial articles, not section indexes or source editions."""
import json
import re
from html import escape, unescape
from pathlib import Path
from authored_pages import load_registry
from asset_paths import is_local_asset
from localization import PAGES_BN
from profile_pages import profiles
from portrait_headers import authored_portraits
ROOT = Path(__file__).resolve().parent
FIXED_ARTICLES = ('origins', 'bangsha-parichay-aguri-origins', 'aguris-recognition',
                  'aguri-jotedars-dar-patnidars', 'aguris-today', 'food-and-village-life',
                  'water-landscape', 'surnames')

# Deliberate homepage selections: use the existing article illustration, not a
# body timeline/diagram or a text-dense reading scan. Article pages retain sources.
ARTWORK_SLIDES = frozenset({'origins', 'military-settlers-bengal',
    'translation-journal-autobiography', 'translation-electricity',
    'translation-prabasi-book-review'})

def articles(lang, fixed):
    titles={k:(PAGES_BN[k][1] if lang=='bn' else title) for k,_,title,_ in fixed if k in FIXED_ARTICLES}
    registry=load_registry(ROOT)
    types={'article','biography'} | {t['id'] for t in registry['types'] if t['template'] in ('article','biography')}
    titles.update({p['id']:p[lang]['title'] for p in registry['pages'] if p['type'] in types})
    _,descriptors=profiles(lang)
    titles.update({k:title for k,_,title,_ in descriptors})
    catalog=json.loads((ROOT/'assets/page-artworks/catalog.json').read_text())
    portraits=authored_portraits(lang)
    result=[]
    for key,title in titles.items():
        source=ROOT/'content'/('bn' if lang=='bn' else '')/(key+'.html')
        html=portraits.get(key.removeprefix('person-'),{}).get('figure','') if key.startswith('person-') else (source.read_text() if source.exists() else '')
        match=re.search(r'<img\b[^>]*src="([^"]+)"',html)
        image=unescape(match[1]) if match else catalog.get(key,{}).get('file','assets/volume-1-cover.jpg')
        if key in ARTWORK_SLIDES:
            image=catalog[key]['file']
        image=image.removeprefix('../')
        if not is_local_asset(ROOT,image): image='assets/volume-1-cover.jpg'
        result.append((key,title,image))
    for slug in ('journal-autobiography','electricity','prabasi-book-review'):
        item=json.loads((ROOT/'content/translations'/(slug+'.json')).read_text())
        key='translation-'+slug
        image=catalog[key]['file'] if key in ARTWORK_SLIDES else item['blocks'][0]['image']
        if not is_local_asset(ROOT,image):
            raise ValueError('Missing curated reading image: '+key)
        result.append((key,item['bengaliTitle'] if lang=='bn' else item['title'],image))
    return result

def teasers(lang, fixed):
    """Curated short lines, with localized descriptions for future additions."""
    result={k:(PAGES_BN[k][2] if lang=='bn' else description)
            for k,_,_,description in fixed if k in FIXED_ARTICLES}
    result.update({p['id']:p[lang]['description'] for p in load_registry(ROOT)['pages']})
    result.update({k:description for k,_,_,description in profiles(lang)[1]})
    curated=json.loads((ROOT/'content/home-carousel-teasers.json').read_text())
    result.update({key:copy[lang] for key,copy in curated.items() if copy.get(lang)})
    return result

def render(lang, fixed):
    rows=articles(lang, fixed); lines=teasers(lang, fixed); e=lambda s:escape(s,quote=True)
    labels=('Articles','Previous article','Next article','Pause','Play') if lang=='en' else ('প্রবন্ধ','আগের প্রবন্ধ','পরের প্রবন্ধ','বিরতি','চালু করুন')
    out=[f'<div class="hero-art home-article-carousel" id="stories" data-home-article-carousel data-pause-label="{labels[3]}" data-play-label="{labels[4]}" role="region" aria-roledescription="carousel" aria-label="{labels[0]}">']
    for i,(key,title,image) in enumerate(rows):
        out.append(f'<a class="home-article-slide" data-home-article-slide data-article-id="{key}" href="{key}.html"'+(' hidden' if i else '')+f'><img src="{e(image)}" width="800" height="600" alt="" '+('loading="lazy"' if i else 'fetchpriority="high"')+f' decoding="async"><span class="home-article-title">{e(title)}<span class="home-article-teaser">{e(lines.get(key, title))}</span></span></a>')
    out.append(f'<div class="home-article-controls" data-home-controls hidden><button type="button" data-home-prev aria-label="{labels[1]}"><span aria-hidden="true">‹</span></button><button type="button" data-home-pause aria-label="{labels[3]}"><span data-home-pause-icon aria-hidden="true">Ⅱ</span></button><button type="button" data-home-next aria-label="{labels[2]}"><span aria-hidden="true">›</span></button></div></div>')
    return ''.join(out)
