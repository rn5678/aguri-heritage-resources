#!/usr/bin/env python3
"""Validate generated citations, local links, assets and archive completeness."""
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urlsplit, unquote
from datetime import date, datetime
from zoneinfo import ZoneInfo
import json, re, sys
from xml.etree import ElementTree as ET
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from seo import BASE, CONFIG, TEXT_ONLY_ARTICLE_KEYS, canonical
from localization import ENGLISH_ONLY_KEYS, NO_SOCIAL_IMAGE_PROFILE_KEYS, STANDALONE_PROFILE_KEYS
from file_links import JOURNAL_ROUTES
from authored_pages import page_map as editor_page_map
from profile_pages import profile_overrides
from portrait_headers import PROFILE_PATTERN
ROOT=Path(__file__).resolve().parents[1]/'site'
INDEPENDENT_ENGLISH_PROFILES=set(profile_overrides(ROOT.parent))
INDEPENDENT_BENGALI_PROFILES=set(profile_overrides(ROOT.parent,lang='bn'))
TODAY=datetime.now(ZoneInfo('Asia/Kolkata')).date()
class Doc(HTMLParser):
 def __init__(self,text):
  super().__init__();self.ids=set();self.refs=[];self.errors=[];self.h1=0;self.lang=None;self.language_options=[];self.canonicals=[];self.alternates={};self.meta={};self.schemas=[];self.schema_text=None;self.in_head=False;self.title_text=None;self.titles=[];self.in_main=False;self.comment_mounts=[];self.feed(text)
 def handle_starttag(self,tag,attrs):
  a=dict(attrs)
  if tag=='main':self.in_main=True
  if 'data-comments' in a:self.comment_mounts.append((self.in_main,'hidden' in a))
  if tag=='head':self.in_head=True
  if tag=='title' and self.in_head:self.title_text=''
  if tag=='h1':self.h1+=1
  if tag=='html':self.lang=a.get('lang')
  if tag=='link' and a.get('rel')=='canonical':self.canonicals.append(a.get('href'))
  if tag=='link' and a.get('hreflang'):self.alternates[a['hreflang']]=a.get('href')
  if tag=='meta':self.meta[a.get('name',a.get('property'))]=a.get('content')
  if tag=='script' and a.get('type')=='application/ld+json':self.schema_text=''
  if tag=='option' and a.get('lang') in ('en','bn'):self.language_options.append((a['lang'],a.get('value')))
  if tag=='a' and 'data-language-switch' in a:
   if a.get('lang') not in ('en','bn') or a.get('hreflang')!=a.get('lang'):
    self.errors.append('Language switch requires matching supported lang and hreflang')
   else:self.language_options.append((a['lang'],a.get('href')))
  if tag=='object' and a.get('data'):self.refs.append(a['data'])
  if 'id' in a:
   if a['id'] in self.ids:self.errors.append('Duplicate id '+a['id'])
   self.ids.add(a['id'])
  for k in ('href','src'):
   if k in a:self.refs.append(a[k])
 def handle_data(self,text):
  if self.title_text is not None:self.title_text+=text
  if self.schema_text is not None:self.schema_text+=text
 def handle_endtag(self,tag):
  if tag=='main':self.in_main=False
  if tag=='title' and self.title_text is not None:
   self.titles.append(' '.join(self.title_text.split()));self.title_text=None
  if tag=='head':self.in_head=False
  if tag=='script' and self.schema_text is not None:
   self.schemas.append(json.loads(self.schema_text));self.schema_text=None

def destination(page,ref):
 u=urlsplit(ref)
 if u.netloc and u.netloc!=urlsplit(BASE).netloc:return None
 if u.scheme and u.scheme not in ('http','https'):return None
 path=unquote(u.path)
 target=(ROOT/path.lstrip('/')) if path.startswith('/') else (page.parent/path) if path else page
 if target.is_dir():target=target/'index.html'
 if not target.exists() and not target.suffix:target=target.with_suffix('.html')
 return target.resolve()
docs={p:Doc(p.read_text()) for p in ROOT.rglob('*.html')}
errors=[]
def check_modification_date(value,context):
 if value is None:return
 try:
  modified=date.fromisoformat(value)
 except (ValueError,TypeError):
  errors.append(f'{context}: invalid modification date {value!r}')
  return
 if modified>TODAY:errors.append(f'{context}: modification date is in the future')

for key,entry in editor_page_map(ROOT.parent).items():
 for lang in ('en','bn'):
  folder=ROOT/('bn' if lang=='bn' else '')
  page=folder/(key+'.html');parent=folder/(entry['section']+'.html')
  if page not in docs:errors.append(f'{lang}: editor page {key} was not built')
  if parent not in docs or key+'.html' not in docs[parent].refs:errors.append(f'{lang}: editor page {key} is missing from its section')
  if page in docs and entry['section']+'.html' not in docs[page].refs:errors.append(f'{lang}: editor page {key} has no link to its section')
for p,d in docs.items():
 errors.extend(f'{p.name}: {e}' for e in d.errors)
 # Check mounts only after build: Node source tests run before site/ exists in CI.
 expected_mounts=0 if p.stem in ('404','contact','contribute','review','editor','admin') else 1
 if len(d.comment_mounts)!=expected_mounts:errors.append(f'{p}: expected {expected_mounts} comment mount(s), found {len(d.comment_mounts)}')
 if any(not in_main or not hidden for in_main,hidden in d.comment_mounts):errors.append(f'{p}: comment mount must be inside main and initially hidden')
 if len(d.titles)!=1 or not d.titles[0]:errors.append(f'{p}: expected exactly one nonempty head title')
 if d.h1!=1:errors.append(f'{p.name}: expected one H1, found {d.h1}')
 for ref in d.refs:
  u=urlsplit(ref)
  if u.path in JOURNAL_ROUTES and (not u.netloc or u.netloc==urlsplit(BASE).netloc):continue
  dest=destination(p,ref)
  if dest is None:continue
  if not dest.exists():errors.append(f'{p.name}: missing {ref}')
  if u.fragment and dest in docs and unquote(u.fragment) not in docs[dest].ids:
   errors.append(f'{p.name}: missing anchor {ref}')
# Bilingual pages need matching editions; explicit English-only pages must not advertise one.
for p,d in docs.items():
 expected='bn' if p.parent.name=='bn' else 'en'
 if d.lang!=expected:errors.append(f'{p}: wrong language {d.lang}')
 english_only=p.stem in ENGLISH_ONLY_KEYS
 if english_only:
  if expected!='en' or (ROOT/'bn'/p.name) in docs:errors.append(f'{p}: unexpected Bengali edition of English-only page')
  if d.language_options:errors.append(f'{p}: English-only page advertises a language switch')
 elif len(d.language_options)!=2 or {lang for lang,_ in d.language_options}!={'en','bn'}:errors.append(f'{p}: expected exactly one route to each language edition')
 for lang,ref in d.language_options:
  dest=destination(p,ref)
  if dest not in docs or docs[dest].lang!=lang:errors.append(f'{p}: invalid language option {ref}')
  if dest is None or dest.name!=p.name:errors.append(f'{p}: language option changes page')
 if expected=='en' and not english_only:
  other=ROOT/'bn'/p.name
  if other not in docs:errors.append(f'{p}: missing Bengali edition')
  else:
   # Navigation sections and sources must survive a language switch.
   # Carousel slide anchors are generated separately from each edition's
   # surviving authored cards. Editorial deep links still must match.
   sections={i for i in d.ids if not i.startswith(('ref-','note-','original-')) and
             not re.fullmatch(r'(?:history|culture|people)-hero-(?:label|track|slide-\d+(?:-title|-summary)?)',i)}
   # The numbered notes panel exists only while this edition cites sources.
   # Its links are checked above; it is not an authored bilingual section.
   if any(re.fullmatch(r'note-\d+',i) for i in d.ids):sections.discard('notes-heading')
   if not sections.issubset(docs[other].ids):errors.append(f'{p.name}: missing Bengali anchors {sections-docs[other].ids}')
for lang,suffix,folder in [('en','',''),('bn','-bn','bn')]:
 index=json.loads((ROOT/'assets'/f'search-index{suffix}.js').read_text().split('=',1)[1].strip().rstrip(';'))
 if len(index)!=len([p for p in docs if p.parent==ROOT/folder and p.stem not in ('404','review')]):errors.append(f'{lang}: search index incomplete')
 for record in index:
  if (ROOT/folder/record['url']) not in docs:errors.append(f'{lang}: broken search result {record["url"]}')
  if record['url'] in ('404.html','review.html'):errors.append(f'{lang}: error page in search index')
  if lang=='bn' and not any('\u0980'<=c<='\u09ff' for c in record['text']):errors.append(f'Untranslated Bengali search entry: {record["url"]}')
# Search-engine discovery must agree with the actual published route for every edition.
sitemap=ET.parse(ROOT/'sitemap.xml')
sitemap_ns='{http://www.sitemaps.org/schemas/sitemap/0.9}'
locations=[e.text for e in sitemap.iter(sitemap_ns+'loc')]
expected_urls={canonical(p.stem,d.lang) for p,d in docs.items() if p.stem not in ('404','review')}
if len(locations)!=len(set(locations)) or set(locations)!=expected_urls:errors.append('Sitemap does not match editorial pages')
history=json.loads((ROOT.parent/'content/page-history.json').read_text())['pages']
expected_dates={canonical(p.stem,d.lang):history.get(f'{d.lang}/{p.stem}',{}).get('updated')
                for p,d in docs.items() if p.stem not in ('404','review')}
for entry in sitemap.iter(sitemap_ns+'url'):
 url=entry.findtext(sitemap_ns+'loc')
 lastmod=entry.findtext(sitemap_ns+'lastmod')
 if lastmod!=expected_dates.get(url):errors.append(f'{url}: sitemap lastmod differs from editorial history')
 check_modification_date(lastmod,f'{url}: sitemap')
if (ROOT/'robots.txt').read_text()!=f'User-agent: *\nAllow: /\n\nSitemap: {BASE}/sitemap.xml\n':errors.append('Invalid robots discovery rules')
verification=ROOT.parent/'content/BingSiteAuth.xml'
if not verification.is_file() or not (ROOT/'BingSiteAuth.xml').is_file():errors.append('Missing Bing ownership verification file')
elif (ROOT/'BingSiteAuth.xml').read_bytes()!=verification.read_bytes():errors.append('Published Bing verification differs from its source')
indexnow_key=CONFIG.get('indexnow_key')
if indexnow_key:
 if not isinstance(indexnow_key,str) or not re.fullmatch(r'[A-Za-z0-9-]{8,128}',indexnow_key):errors.append('Invalid configured IndexNow key')
 else:
  key_file=ROOT/(indexnow_key+'.txt')
  if not key_file.is_file() or key_file.read_text().strip()!=indexnow_key:errors.append('Published IndexNow key file differs from its configured key')
public_titles={};public_descriptions={}
for p,d in docs.items():
 if p.stem in ('404','review'):
  if d.canonicals or d.alternates or 'noindex' not in d.meta.get('robots',''):errors.append(f'{p}: 404 must be noindex without canonical/hreflang')
  continue
 for value,seen,label in ((' '.join(d.titles).casefold(),public_titles,'title'),(' '.join((d.meta.get('description') or '').split()).casefold(),public_descriptions,'description')):
  if not value:errors.append(f'{p}: empty search {label}')
  elif value in seen:errors.append(f'{p}: duplicate search {label} also used by {seen[value]}')
  else:seen[value]=p
 url=canonical(p.stem,d.lang)
 if d.canonicals!=[url]:errors.append(f'{p}: wrong canonical')
 alternatives=[('en','en'),('x-default','en')] if p.stem in ENGLISH_ONLY_KEYS else [('en','en'),('bn','bn'),('x-default','en')]
 if d.alternates!={code:canonical(p.stem,lang) for code,lang in alternatives}:errors.append(f'{p}: wrong language alternatives')
 if p.stem in ENGLISH_ONLY_KEYS:
  if 'og:locale:alternate' in d.meta:errors.append(f'{p}: English-only page advertises an alternate sharing locale')
 elif d.meta.get('og:locale:alternate')!=('en_IN' if d.lang=='bn' else 'bn_IN'):errors.append(f'{p}: wrong alternate sharing locale')
 if p.stem in TEXT_ONLY_ARTICLE_KEYS | NO_SOCIAL_IMAGE_PROFILE_KEYS and any(k.startswith(('og:image','twitter:image')) for k in d.meta if k):errors.append(f'{p}: page with social images disabled has unexpected sharing artwork')
 if d.meta.get('og:url')!=url or not d.meta.get('og:title') or not d.meta.get('description'):errors.append(f'{p}: incomplete sharing/search metadata')
 if 'noindex' in d.meta.get('robots',''):errors.append(f'{p}: editorial page blocked from indexing')
 if len(d.schemas)!=1:errors.append(f'{p}: missing structured data')
 else:
  graph=d.schemas[0]['@graph'];types={n['@type'] for n in graph}
  if not {'WebSite','WebPage'}.issubset(types):errors.append(f'{p}: missing site/page schema')
  if p.stem!='index' and 'BreadcrumbList' not in types:errors.append(f'{p}: missing breadcrumb schema')
  page=next(n for n in graph if n['@type']=='WebPage')
  if page['url']!=url or page['inLanguage']!=d.lang:errors.append(f'{p}: inconsistent structured data')
  modified=page.get('dateModified')
  if modified!=expected_dates.get(url):errors.append(f'{p}: structured dateModified differs from editorial history')
  check_modification_date(modified,f'{p}: structured metadata')
for lang in ('en','bn'):
 folder=ROOT/('bn' if lang=='bn' else '')
 source=ROOT.parent/'content'/('bn' if lang=='bn' else '')/'people.html'
 expected_profiles={'person-'+slug+'.html' for slug,_ in re.findall(PROFILE_PATTERN,source.read_text(),re.S)}
 standalone=(INDEPENDENT_ENGLISH_PROFILES if lang=='en' else INDEPENDENT_BENGALI_PROFILES) & STANDALONE_PROFILE_KEYS
 expected_profiles.update(key+'.html' for key in standalone)
 for key in standalone:
  if key+'.html' not in docs[folder/'people.html'].refs:
   errors.append(f'{lang}: standalone biography {key} is not linked from People')
  page=folder/(key+'.html')
  if page in docs and 'people.html' not in docs[page].refs:
   errors.append(f'{lang}: standalone biography {key} has no backlink to People')
 actual_profiles={p.name for p in folder.glob('person-*.html')}
 if not expected_profiles or actual_profiles!=expected_profiles:errors.append(f'{lang}: individual biographies do not match the People collection')
 if not docs[folder/'index.html'].meta.get('google-site-verification'):errors.append(f'{lang}: missing verification tag')
for v,count in ((1,175),(2,167)):
 for n in range(1,count+1):
  stem=f'v{v}-{n:03}'
  for ext,sub in (('jpg','scans'),('json','ocr')):
   if not (ROOT/'assets'/sub/f'{stem}.{ext}').is_file():errors.append(f'Missing {stem}.{ext}')
  r=json.loads((ROOT/'assets/ocr'/f'{stem}.json').read_text())
  if r['volume']!=v or r['scan']!=n:errors.append(f'Wrong metadata for {stem}')
if errors:raise SystemExit('\n'.join(errors))
print(f'PASS: {len(expected_urls)} indexable pages plus two editor and two 404 pages; edition routes, canonicals, sitemap, structured data, links, citations and all 342 scans valid.')
