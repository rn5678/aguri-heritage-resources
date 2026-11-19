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

def spotlight_article(rows, history=None, config=None):
    """Use first recorded publication, never a later edit; explicit editorial override wins."""
    if config is None:
        config=json.loads((ROOT/'content/home-spotlight.json').read_text())
    override=config.get('article_id')
    if override:
        if override not in {row[0] for row in rows}:
            raise ValueError('Spotlight override is not an eligible article: '+override)
        return next(row for row in rows if row[0]==override)
    if history is None:
        history=json.loads((ROOT/'content/page-history.json').read_text())['pages']
    # Both editions deliberately select the same identity. Baseline records the
    # first recorded publication in this site's editorial history, not ancient source dates.
    return max(rows,key=lambda row:(history.get('en/'+row[0],{}).get('baseline',{}).get('date',''),row[0]))


def article_link(key, lang):
    # Complete reading editions are English-only, including when promoted in Bengali.
    if lang=='bn' and key.startswith('translation-'):
        return '../'+key+'.html', ' hreflang="en"'
    return key+'.html', ''


def render_spotlight(lang, fixed):
    key,title,image=spotlight_article(articles(lang,fixed)); e=lambda s:escape(s,quote=True)
    href,extra=article_link(key,lang)
    label='Spotlight of the Month' if lang=='en' else 'এ মাসের বিশেষ পাঠ'
    line=teasers(lang,fixed).get(key,title)
    return (f'<div class="hero-art home-spotlight" data-home-spotlight data-article-id="{key}">'
            f'<a class="home-spotlight-link" href="{href}"{extra}><img src="{e(image)}" width="800" height="600" alt="" fetchpriority="high" decoding="async">'
            f'<span class="spotlight-label">{label}</span><span class="home-article-title">{e(title)}'
            f'<span class="home-article-teaser">{e(line)}</span></span></a></div>')


def render(lang, fixed):
    rows=articles(lang, fixed); lines=teasers(lang, fixed); e=lambda s:escape(s,quote=True)
    labels=('Every history begins with a story.','Previous articles','Next articles','Pause','Play') if lang=='en' else ('একটি গল্প থেকেই ইতিহাসের শুরু।','আগের প্রবন্ধগুলি','পরের প্রবন্ধগুলি','বিরতি','চালু করুন')
    eyebrow='Origins. People. Places. Everyday life.' if lang=='en' else 'উৎপত্তি। মানুষ। জনপদ। দৈনন্দিন জীবন।'
    subhead='Discover the stories that connect us.<br>Follow what interests you.' if lang=='en' else 'যে গল্পগুলি আমাদের যুক্ত করে। আপনার আগ্রহের সূত্র ধরে এগিয়ে চলুন।'
    # Restore the original pre-PR21 editorial hierarchy and existing story CSS;
    # retain the requested concise title + one-line teaser, without long extracts.
    out=[f'<section class="stories home-article-carousel" id="stories" data-home-article-carousel data-pause-label="{labels[3]}" data-play-label="{labels[4]}" role="region" aria-roledescription="carousel" aria-labelledby="stories-title"><div class="section-heading"><div><p class="eyebrow">{eyebrow}</p><h2 id="stories-title">{labels[0]}</h2></div><p class="subhead">{subhead}</p></div><div class="carousel-viewport"><div class="story-grid home-article-track" id="story-track">']
    for i,(key,title,image) in enumerate(rows):
        href,extra=article_link(key,lang)
        visual='portrait' if key.startswith('person-') else 'custom'
        out.append(f'<a class="story home-article-slide" data-home-article-slide data-article-id="{key}" href="{href}"{extra}'+(' hidden' if i>=3 else '')+f'><span class="story-visual {visual}"><img src="{e(image)}" width="800" height="600" alt="" loading="lazy" decoding="async"></span><div class="story-body"><h3>{e(title)}</h3><span class="story-link"><span class="home-article-teaser">{e(lines.get(key, title))}</span><span class="arrow" aria-hidden="true">↗</span></span></div></a>')
    out.append(f'</div></div><div class="carousel-controls home-article-controls" data-home-controls hidden><div class="carousel-position"><span class="carousel-status" data-home-status aria-live="off"></span></div><div class="carousel-actions"><button class="carousel-arrow" type="button" data-home-prev aria-label="{labels[1]}" aria-controls="story-track"><span aria-hidden="true">←</span></button><button class="carousel-toggle" type="button" data-home-pause aria-label="{labels[3]}" aria-controls="story-track"><span data-home-pause-text>{labels[3]}</span></button><button class="carousel-arrow" type="button" data-home-next aria-label="{labels[2]}" aria-controls="story-track"><span aria-hidden="true">→</span></button></div></div></section>')
    return ''.join(out)
