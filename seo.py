"""Search metadata and discovery files for the public, bilingual static site."""
from html import escape
from datetime import date
from pathlib import Path
import json
import re
from xml.etree import ElementTree as ET
from localization import ENGLISH_ONLY_KEYS, NO_SOCIAL_IMAGE_PROFILE_KEYS

CONFIG = json.loads((Path(__file__).parent/'content/site-config.json').read_text())
BASE = CONFIG['url'].rstrip('/')
SOCIAL = Path(__file__).parent/'assets/social'
ARTWORK = json.loads((Path(__file__).parent/'assets/page-artworks/catalog.json').read_text())
TEXT_ONLY_ARTICLE_KEYS=frozenset({'aguris-recognition','aguri-jotedars-dar-patnidars','bangsha-parichay-aguri-origins'})
TITLES = {
 'en': {
  'index': 'Aguri & Ugra Kshatriya Heritage — History, Culture & People',
  'history': 'Aguri History — Origins, Land & Social Change',
  'origins': 'Aguri Origins — From Nagadee to Jotedar',
  'culture': 'Aguri Culture — Customs, Learning & Community Life',
  'aguris-today': 'Aguris Today — Land, Mobility & Community Life',
  'geography': 'Aguris in Rarh Bengal — Bardhaman & Neighbouring Districts',
  'people': 'Notable Personalities — Aguri Heritage',
  'archives': 'Ugrakshatriya-Pratinidhi — Bengali Journal Archive',
  'translations': 'Aguri History — Bengali Sources & English Translations',
  'bibliography': 'Aguri & Ugra Kshatriya — Books, Research & Sources',
  'research': 'Aguri Research Topics — Heritage, Land, Caste & Society',
  'about': 'About Aguri Heritage — Editorial Approach & Contributions',
  'book-rajput-o-ugrakshatriya': 'Rajput O Ugrakshatriya — Bengali Book & English Translation',
 },
 'bn': {
  'index': 'আগুরী ও উগ্রক্ষত্রিয় সমাজের ইতিহাস — আগুরী ঐতিহ্য',
  'history': 'আগুরীদের ইতিহাস — উৎপত্তি, ভূমি ও সামাজিক পরিবর্তন',
  'origins': 'আগুরীদের উৎপত্তি — নগদী থেকে জোতদার',
  'culture': 'আগুরী সংস্কৃতি — রীতিনীতি, শিক্ষা ও সমাজজীবন',
  'aguris-today': 'আজকের আগুরীরা — জমি, অভিবাসন ও সমাজজীবন',
  'geography': 'রাঢ়বঙ্গে আগুরীরা — বর্ধমান ও পার্শ্ববর্তী অঞ্চল',
  'people': 'বিশিষ্ট ব্যক্তিত্ব — আগুরী ঐতিহ্য',
  'archives': 'উগ্রক্ষত্রিয়-প্রতিনিধি — বাংলা সাময়িকপত্রের সংগ্রহ',
  'translations': 'আগুরী ইতিহাস — বাংলা উৎস ও ইংরেজি অনুবাদ',
  'bibliography': 'আগুরী ও উগ্রক্ষত্রিয় — বই, গবেষণা ও তথ্যসূত্র',
  'research': 'আগুরী গবেষণার বিষয় — ঐতিহ্য, ভূমি, জাতি ও সমাজ',
  'about': 'আগুরী ঐতিহ্য — প্রকল্প ও সম্পাদনার দৃষ্টিভঙ্গি',
  'book-rajput-o-ugrakshatriya': 'রাজপুত ও উগ্রক্ষত্রিয় — বাংলা বই ও ইংরেজি অনুবাদ',
 }
}

def canonical(key, lang):
 prefix = '/bn/' if lang == 'bn' else '/'
 return BASE + prefix + ('' if key == 'index' else key)

def metadata(key, title, description, lang, updated=None, parent=None):
 if key in ENGLISH_ONLY_KEYS and lang!='en':
  raise ValueError(f'{key} has no {lang} edition')
 brand = 'আগুরী ঐতিহ্য' if lang == 'bn' else 'Aguri Heritage'
 page_title = title
 title = TITLES[lang].get(key, title + ' — ' + brand)
 if key in ('404','review'):
  return f'<title>{escape(title)}</title><meta name="robots" content="noindex, follow">'
 url = canonical(key, lang)
 tags = [f'<title>{escape(title)}</title>',
         f'<link rel="canonical" href="{escape(url, quote=True)}">',
         '<meta name="robots" content="index, follow, max-image-preview:large">']
 alternatives=[('en','en'),('x-default','en')] if key in ENGLISH_ONLY_KEYS else [('en','en'),('bn','bn'),('x-default','en')]
 for code, target in alternatives:
  tags.append(f'<link rel="alternate" hreflang="{code}" href="{canonical(key,target)}">')
 for prop, value in {'og:type':'website','og:site_name':brand,'og:title':title,
                     'og:description':description,'og:url':url,
                     'og:locale':'bn_IN' if lang=='bn' else 'en_IN'}.items():
  tags.append(f'<meta property="{prop}" content="{escape(value, quote=True)}">')
 if key not in ENGLISH_ONLY_KEYS:
  tags.append(f'<meta property="og:locale:alternate" content="{"en_IN" if lang=="bn" else "bn_IN"}">')
 # Link previews use the page's own topic artwork where a preview image exists.
 preferred_image_key = 'geography' if key in ('food-and-village-life','water-landscape') else 'culture' if key == 'aguris-today' else key
 image_key = preferred_image_key if (SOCIAL/f'{preferred_image_key}.jpg').is_file() else 'index'
 card = 'summary'
 if key not in TEXT_ONLY_ARTICLE_KEYS and key not in NO_SOCIAL_IMAGE_PROFILE_KEYS and (SOCIAL/f'{image_key}.jpg').is_file():
  item = ARTWORK.get(image_key, {})
  image_url = f'{BASE}/assets/social/{image_key}.jpg'
  alt = item.get('alt_bn' if lang=='bn' else 'alt_en', title)
  for prop, value in {'og:image':image_url,'og:image:type':'image/jpeg','og:image:width':'1200','og:image:height':'630','og:image:alt':alt}.items():
   tags.append(f'<meta property="{prop}" content="{escape(value, quote=True)}">')
  tags.append(f'<meta name="twitter:image" content="{escape(image_url, quote=True)}">')
  tags.append(f'<meta name="twitter:image:alt" content="{escape(alt, quote=True)}">')
  card = 'summary_large_image'
 for name, value in {'twitter:card':card,'twitter:title':title,'twitter:description':description}.items():
  tags.append(f'<meta name="{name}" content="{escape(value, quote=True)}">')
 if key == 'index' and CONFIG.get('google_site_verification'):
  tags.append(f'<meta name="google-site-verification" content="{escape(CONFIG["google_site_verification"], quote=True)}">')
 website = {'@type':'WebSite','@id':BASE+'/#website','url':BASE+'/',
            'name':'Aguri Heritage','alternateName':'আগুরী ঐতিহ্য','inLanguage':['en','bn']}
 page = {'@type':'WebPage','@id':url+'#webpage','url':url,'name':title,
         'description':description,'inLanguage':lang,'isPartOf':{'@id':BASE+'/#website'}}
 if updated:
  page['dateModified'] = updated
  page['publisher'] = {'@type':'Organization','name':'Aguri Heritage','url':BASE+'/'}
 graph = [website, page]
 if key != 'index':
  trail = [('প্রচ্ছদ' if lang=='bn' else 'Home', canonical('index',lang))]
  if parent:
   parent_key,parent_label=parent
   trail.append((parent_label,canonical(parent_key,lang)))
  elif key.startswith('person-'):
   trail.append(('ব্যক্তিত্ব' if lang=='bn' else 'People',canonical('people',lang)))
  elif key=='origins' or key in TEXT_ONLY_ARTICLE_KEYS:
   trail.append(('ইতিহাস' if lang=='bn' else 'History',canonical('history',lang)))
  elif key in ('aguris-today','food-and-village-life'):
   trail.append(('সংস্কৃতি' if lang=='bn' else 'Culture',canonical('culture',lang)))
  elif key=='water-landscape':
   trail.append(('অঞ্চল' if lang=='bn' else 'Places',canonical('geography',lang)))
  elif key.startswith('translation-'):
   trail.extend([('উৎসসমূহ' if lang=='bn' else 'Resources',canonical('bibliography',lang)),
                 ('পাঠ ও অনুবাদ' if lang=='bn' else 'Translations',canonical('translations',lang))])
  elif key in ('archives','translations','book-rajput-o-ugrakshatriya','research'):
   trail.append(('উৎসসমূহ' if lang=='bn' else 'Resources',canonical('bibliography',lang)))
  trail.append((page_title if parent or key in ('aguris-today','food-and-village-life','water-landscape') or key in TEXT_ONLY_ARTICLE_KEYS else title,url))
  graph.append({'@type':'BreadcrumbList','@id':url+'#breadcrumb','itemListElement':[
   {'@type':'ListItem','position':n,'name':name,'item':item} for n,(name,item) in enumerate(trail,1)]})
  page['breadcrumb']={'@id':url+'#breadcrumb'}
 tags.append('<script type="application/ld+json">'+json.dumps({'@context':'https://schema.org','@graph':graph},ensure_ascii=False).replace('<','\\u003c')+'</script>')
 return '\n'.join(tags)

def write_discovery(out, keys, updated_dates=None):
 # IndexNow proves control of this public origin with a public text file.
 # The key is deliberately not an account credential or a private API token.
 key = CONFIG.get('indexnow_key')
 if key:
  if not re.fullmatch(r'[A-Za-z0-9-]{8,128}', key):
   raise ValueError('Invalid public IndexNow verification key')
  (out/f'{key}.txt').write_text(key, encoding='utf-8')
 ns = 'http://www.sitemaps.org/schemas/sitemap/0.9'
 ET.register_namespace('', ns)
 root = ET.Element('{'+ns+'}urlset')
 for lang in ('en','bn'):
  for key in keys:
   if lang=='bn' and key in ENGLISH_ONLY_KEYS:continue
   node = ET.SubElement(root, '{'+ns+'}url')
   ET.SubElement(node, '{'+ns+'}loc').text = canonical(key,lang)
   # Reuse editorial dates; a rebuild or domain move is not a content update.
   updated = (updated_dates or {}).get(f'{lang}/{key}')
   if updated:
    ET.SubElement(node, '{'+ns+'}lastmod').text = date.fromisoformat(updated).isoformat()
 ET.indent(root)
 ET.ElementTree(root).write(out/'sitemap.xml',encoding='utf-8',xml_declaration=True)
 (out/'robots.txt').write_text(f'User-agent: *\nAllow: /\n\nSitemap: {BASE}/sitemap.xml\n')
 # Preview hosts must never compete with the production site. OCR stays crawlable
 # so the noindex response can be read; the reader remains an indexable resource.
 (out/'_headers').write_text('https://:version.aguri-heritage.pages.dev/*\n  X-Robots-Tag: noindex\n\n/assets/ocr/*\n  X-Robots-Tag: noindex\n\n/review*\n  X-Robots-Tag: noindex, nofollow\n  Cache-Control: no-store\n  Referrer-Policy: no-referrer\n\n/bn/review*\n  X-Robots-Tag: noindex, nofollow\n  Cache-Control: no-store\n  Referrer-Policy: no-referrer\n\n/contribute*\n  Referrer-Policy: no-referrer\n\n/bn/contribute*\n  Referrer-Policy: no-referrer\n\n/sw.js\n  Cache-Control: no-cache\n')
