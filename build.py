#!/usr/bin/env python3
"""Build the English and Bengali community heritage website; Python standard library only."""
from pathlib import Path
from html import escape, unescape
from html.parser import HTMLParser
import hashlib, json, os, re, shutil
from translation_pages import render_translations
from bengali_readings import render_bengali_readings
from localization import ENGLISH_ONLY_KEYS, PAGES_BN, num, ui, display_date
from page_history import PageHistory
from weekly_feature import prepare_weekly_feature
from homepage import render_homepage
from history_page import render_history
from culture_page import render_culture
from people_page import render_people
from profile_pages import profiles, profile_overrides
from page_artwork import load_catalog, page_heading
from seo import BASE, TEXT_ONLY_ARTICLE_KEYS, canonical, metadata, write_discovery
from file_links import open_file_links
from authored_pages import descriptors as editor_descriptors, page_map as editor_page_map
from urllib.parse import urljoin, quote

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'site'
PAGES = [
 ('index','Home','Aguri Heritage','Discover the history, culture, places and people of the Aguri / Ugra Kshatriya community of West Bengal.'),
 ('history','History','The Aguris through history','Origins, land, social change and the community’s place in Bengal’s history.'),
 ('origins','Origins','From Nagadee to Jotedar: The Burdwan Raj and the Origins of the Aguris','An argument about military service, landholding and identity in the history of the Aguris and the Burdwan Raj.'),
 ('bangsha-parichay-aguri-origins','Family histories','Reading the Bangsha Parichay','What Bengal’s lineage books reveal about Aguri origins, family memory and belonging in Rarh.'),
 ('aguris-recognition','Search for recognition','Aguris and the Search for Recognition','Status, marriage and belonging in Bengal'),
 ('aguri-jotedars-dar-patnidars','The Missing Middle','The Missing Middle','Aguri Jotedars, Dar-Patnidars and the Making of Rural Power in the Burdwan Raj'),
 ('culture','Culture','Culture, customs & community life','Village life, worship, custom and reform, print and family memory in the records of the Aguri community.'),
 ('aguris-today','Aguris Today','Aguris Today','Land, mobility, political participation and the remaking of community.'),
 ('food-and-village-life','Food & village life','Food and Village Life among the Aguris','Macher tok, harvest meals, festivals and the everyday history of Bardhaman’s villages.'),
 ('geography','Places','Rooted in Rarh Bengal','Bardhaman and the neighbouring districts connected with Aguri history and community life.'),
 ('water-landscape','Water landscape','Aguris and the Water Landscape of Rarh Bengal','Rivers, canals and the history of Aguri settlement, cultivation and rural power in Rarh Bengal.'),
 ('people','People','Lives behind the history','Biographical profiles in public service, medicine, literature, cinema, education and journalism.'),
 ('surnames','Surnames','Where Aguri surnames come from','The meanings and origins of Aguri surnames, and the family histories behind changing titles.'),
 ('archives','Periodical archive','Ugrakshatriya-Pratinidhi','Two historical journal volumes, preserved as source material for the study of the Aguri community.'),
 ('translations','Translations','Bengali voices, in English','An English book translation, selected journal articles, book prefaces and a contemporary review, with their Bengali sources.'),
 ('bibliography','Resources','Resources for exploring Aguri heritage','Books, scholarship, biographies, periodicals and translated source material supporting the community’s story.'),
 ('research','Research topics','Research topics','Questions for studying Aguri heritage, migration, land, marriage and inequality through archives, oral history and fieldwork.'),
 ('contact','Contact Us','Contact Us','Send a private message to Aguri Heritage about the website or project.'),
 ('contribute','Contribute','Add a piece of the story','Share a memory, photograph or document, or help us correct the record. Bengali and English contributions are welcome.'),
 ('review','Editor review','The contribution desk','Review community contributions, request more information and record editorial decisions.'),
 ('about','About','A heritage worth keeping','An independent project celebrating the history, culture and people of the Aguri / Ugra Kshatriya community.'),
 ('rights','Copyright & reuse','Copyright & reuse','A community project with reserved rights: how to read, share, quote and request permission to reuse material.'),
 ('contributor-terms','Contributor terms','Your contribution, your rights','The permissions you give Aguri Heritage, the rights you keep, and how we review and care for your contribution.'),
 ('book-rajput-o-ugrakshatriya','Historical book','Rajput O Ugrakshatriya','Haricharan Bandhu’s historical book, second edition, 1940: read the English translation and the Bengali original.')]
NAV_KEYS=['index','history','culture','geography','people','surnames','about','bibliography']
RESOURCE_KEYS={'bibliography','archives','translations','book-rajput-o-ugrakshatriya','research'}
SOURCES = json.loads((ROOT/'content/sources.json').read_text())
ARTWORKS = load_catalog()

class Plain(HTMLParser):
 def __init__(self): super().__init__(); self.parts=[]
 def handle_data(self, data): self.parts.append(data)
def plain(s):
 p=Plain(); p.feed(s); return ' '.join(' '.join(p.parts).split())
def source_html(s):
 return f'<span class="source-type {s["kind"]}">{escape(s["label"])}</span><h3>{escape(s["title"])}</h3><p>{escape(s["detail"])}</p><p class="source-status">{escape(s["status"])}</p><a href="{escape(s["url"],quote=True)}">{escape(s.get("linkLabel","Open source"))} <span aria-hidden="true">↗</span></a>'

def anchored(frag):
 headings=[]
 def heading(m):
  attrs,text=m.group(1),m.group(2)
  match=re.search(r'id="([^"]+)"',attrs)
  slug=match.group(1) if match else re.sub(r'[^a-z0-9]+','-',plain(text).lower()).strip('-')
  if not slug: raise ValueError('A heading needs a stable ID: '+text)
  if not match: attrs+=f' id="{slug}"'
  headings.append((slug,plain(text)))
  return f'<h2{attrs}>{text}</h2>'
 return re.sub(r'<h2([^>]*)>(.*?)</h2>',heading,frag,flags=re.S),headings

def align_headings(frag,english):
 ids=[sid for sid,_ in anchored(english)[1]]
 matches=list(re.finditer(r'<h2([^>]*)>(.*?)</h2>',frag,re.S))
 explicit=[re.search(r'\bid="([^"]+)"',m.group(1)) for m in matches]
 if all(explicit):return frag
 preserved={m.group(1) for m in explicit if m}
 deleted=set(re.findall(r'<span\b(?=[^>]*\bdata-editor-anchor="true")[^>]*\bid="([^"]+)"',frag))
 available=[sid for sid in ids if sid not in deleted]
 if len(matches)==len(available) and all(not m or m.group(1)==available[i] for i,m in enumerate(explicit)):
  assigned=available
 else:
  remaining=[sid for sid in available if sid not in preserved]
  if len(remaining)!=1 or sum(m is None for m in explicit)!=1:
   raise ValueError('Bengali headings without IDs cannot be aligned unambiguously; retain explicit section IDs')
  assigned=[m.group(1) if m else remaining[0] for m in explicit]
 position=iter(assigned)
 def heading(m):
  sid=next(position)
  if re.search(r'\bid="[^"]+"',m.group(1)):return m.group(0)
  return f'<h2{m.group(1)} id="{sid}">{m.group(2)}</h2>'
 return re.sub(r'<h2([^>]*)>(.*?)</h2>',heading,frag,flags=re.S)

class GuideHeadings(HTMLParser):
 """Keep collection navigation focused on visible sections; retain all deep anchors."""
 def __init__(self):
  super().__init__(); self.depth=0; self.ids=set()
 def handle_starttag(self,tag,attrs):
  if tag=='details':self.depth+=1
  if tag=='h2' and not self.depth:self.ids.add(dict(attrs).get('id'))
 def handle_endtag(self,tag):
  if tag=='details':self.depth=max(0,self.depth-1)

def render_page(key,label,title,desc,frag,lang,sources,page_labels,history,editor_pages=None):
 if key in ENGLISH_ONLY_KEYS and lang!='en':raise ValueError(f'{key} has no {lang} edition')
 editor_page=(editor_pages or {}).get(key)
 parent=editor_page['section'] if editor_page else None
 t=lambda x:ui(x,lang)
 assets='../assets/' if lang=='bn' else 'assets/'
 title_hidden=key.startswith('person-') and 'data-editor-title-hidden="true"' in frag
 description_hidden=key.startswith('person-') and 'data-editor-description-hidden="true"' in frag
 if key=='index' and not re.search(r'<h1\b',frag) and re.search(r'<span\b(?=[^>]*data-editor-anchor="true")(?=[^>]*data-editor-tag="h1")[^>]*>',frag):
  frag='<h1 hidden data-editor-generated="true">'+escape(title)+'</h1>'+frag
 frag,headings=anchored(frag)
 if key in ('history','culture','geography','surnames','about','bibliography'):
  guide_headings=GuideHeadings();guide_headings.feed(frag)
  headings=[entry for entry in headings if entry[0] in guide_headings.ids]
 if key=='bibliography':
  entries=''.join(f'<article class="source-entry" id="source-{sid}" data-kind="{s["kind"]}">{source_html(s)}</article>' for sid,s in sources.items())
  frag=frag.replace('{{source_catalogue}}',entries).replace('{{source_count}}',num(len(sources),lang))
 citations=[];occurrences=[]
 def cite(m):
  sid=m.group(1)
  if sid not in sources:raise ValueError(f'Unknown citation: {sid}')
  if sid not in citations:citations.append(sid)
  n=citations.index(sid)+1;occurrences.append(sid)
  return f'<sup class="citation"><a id="ref-{n}-{len(occurrences)}" href="#note-{n}" aria-label="{t("Source")} {num(n,lang)}: {escape(sources[sid]["title"],quote=True)}">[{num(n,lang)}]</a></sup>'
 frag=re.sub(r'\[cite:([\w-]+)\]',cite,frag)
 notes=''
 if citations:
  note_items=''
  for n,sid in enumerate(citations,1):
   s=sources[sid]
   note_items+=f'<li id="note-{n}"><a href="{escape(s["url"],quote=True)}">{escape(s["title"])}</a>. {escape(s["status"])} <a class="text-link" href="bibliography.html#source-{sid}">{t("Source details")}</a></li>'
  notes=f'<section class="notes" aria-labelledby="notes-heading"><p class="eyebrow">{t("Read further")}</p><h2 id="notes-heading">{t("Notes & sources")}</h2><ol>{note_items}</ol></section>'
 # Track editorial content before adding dates, citations or shared page furniture.
 updated=history.updated(key,lang,title,desc,frag+notes) if key not in ('404','contact','contribute','review') else None
 # Apply the disclosure after fingerprinting so layout changes retain editorial dates.
 if citations and key!='bibliography':
  notes=f'<details class="notes" aria-labelledby="notes-heading"><summary><h2 id="notes-heading">{t("Notes & sources")}</h2></summary><ol>{note_items}</ol></details>'
 date_markup=f'<time datetime="{updated}">{display_date(updated,lang)}</time>' if updated else ''
 updated_markup=f'<p class="page-updated">{t("Last updated")}: {date_markup}</p>' if updated else ''
 is_translation=key.startswith('translation-');is_resource=is_translation or key in RESOURCE_KEYS
 active_key='people' if key.startswith('person-') else 'bibliography' if is_resource else 'history' if key=='origins' or key in TEXT_ONLY_ARTICLE_KEYS else 'culture' if key in ('aguris-today','food-and-village-life') else 'geography' if key=='water-landscape' else key
 if parent:active_key=parent
 nav=''.join(f'<a href="{k}.html"'+(' aria-current="page"' if k==active_key else '')+f'>{escape(page_labels[k])}</a>' for k in NAV_KEYS)
 crumb_label=f'<a href="translations.html">{t("Translations")}</a>' if is_translation else escape(label)
 if key.startswith('person-'):crumb_label=f'<a href="people.html">{escape(page_labels["people"])}</a><span aria-hidden="true"> / </span>'+crumb_label
 if key=='origins' or key in TEXT_ONLY_ARTICLE_KEYS:crumb_label=f'<a href="history.html">{escape(page_labels["history"])}</a><span aria-hidden="true"> / </span>'+crumb_label
 if key in ('aguris-today','food-and-village-life'):crumb_label=f'<a href="culture.html">{escape(page_labels["culture"])}</a><span aria-hidden="true"> / </span>'+crumb_label
 if key=='water-landscape':crumb_label=f'<a href="geography.html">{escape(page_labels["geography"])}</a><span aria-hidden="true"> / </span>'+crumb_label
 if is_resource and key!='bibliography':crumb_label=f'<a href="bibliography.html">{t("Resources")}</a><span aria-hidden="true"> / </span>'+crumb_label
 if parent:crumb_label=f'<a href="{parent}.html">{escape(page_labels[parent])}</a><span aria-hidden="true"> / </span>'+crumb_label
 heading_title=f'<h1 hidden data-editor-generated="true">{escape(title)}</h1>' if title_hidden else f'<h1>{escape(title)}</h1>'
 heading_description='' if description_hidden else f'<p class="dek">{escape(desc)}</p>'
 heading_copy=f'<p class="eyebrow"><a href="index.html">{t("The heritage project")}</a><span aria-hidden="true"> / </span>{crumb_label}</p>{heading_title}{heading_description}{updated_markup}'
 crumbs='' if key=='index' else f'<div class="page-heading">{heading_copy}</div>' if (editor_page and key not in ARTWORKS) or key in ('contact','contribute','review','rights','contributor-terms') or key in TEXT_ONLY_ARTICLE_KEYS else page_heading(key,heading_copy,lang,ARTWORKS)
 if is_resource:
  current='translations' if is_translation else 'bibliography' if key.startswith('book-') else key
  crumbs+=f'<nav class="resource-nav" aria-label="{t("Resource sections")}">'+''.join(f'<a href="{k}.html"'+(' aria-current="page"' if k==current else '')+f'>{t(text)}</a>' for k,text in [('bibliography','Books & references'),('research','Research topics'),('translations','English translations'),('archives','Periodical archive')])+'</nav>'
 toc=''
 if key not in ('index','archives','contact','contribute','review') and len(headings)>2:
  toc=f'<nav class="on-this-page" aria-label="{t("On this page")}"><span>{t("On this page")}</span>'+''.join(f'<a href="#{sid}">{escape(text)}</a>' for sid,text in headings)+'</nav>'
  if is_translation:toc=f'<details class="translation-toc"><summary>{t("In this translation")} · {num(len(headings),lang)} {t("sections")}</summary>{toc}</details>'
 page_tools=''
 if key not in ('404','contact','contribute','review'):
  source_url=escape(canonical(key,lang),quote=True)
  rights_url=escape(canonical('rights',lang),quote=True)
  print_source=f'<p class="print-source"><span>{t("Sourced from the Aguri Heritage project.")}</span><br><a href="{source_url}" lang="en" dir="ltr">{source_url}</a><br><span>{t("Original project material: all rights reserved. Other material retains its own rights.")}</span> <a href="{rights_url}">{t("Copyright & reuse")}</a></p>'
  attribution=(f'<div class="page-attribution"><details class="page-citation" id="cite-this-page"><summary>{t("Cite this page")}</summary>'
   f'<div class="citation-panel"><p class="citation-text" id="page-citation-text">{t("Aguri Heritage")}. “{escape(title)}.” '
   f'{t("Last updated")}: {date_markup}. <a class="citation-url" href="{source_url}" lang="en" dir="ltr">{source_url}</a>.</p>'
   f'<button type="button" class="citation-copy" aria-describedby="page-citation-text" hidden>{t("Copy citation")}</button>'
   f'<span class="citation-status" role="status" aria-live="polite"></span>'
   f'<p class="citation-reuse">{t("Citing this page does not grant permission to republish it.")} <a href="rights.html">{t("Copyright & reuse")}</a>.</p>'
   '</div></details></div>')
  if key not in ('rights','contributor-terms'):
   share_url=canonical(key,lang)
   q=lambda v:quote(v,safe='')
   share_title=escape(title,quote=True)
   message=f'{title} — {share_url}'
   share_links=(f'<a class="share-link" data-share="whatsapp" href="https://wa.me/?text={q(message)}" target="_blank" rel="noopener noreferrer">{t("WhatsApp")}</a>'
    f'<a class="share-link" data-share="facebook" href="https://www.facebook.com/sharer/sharer.php?u={q(share_url)}" target="_blank" rel="noopener noreferrer">{t("Facebook")}</a>'
    f'<a class="share-link" data-share="email" href="mailto:?subject={q(title)}&amp;body={q(desc+chr(10)+chr(10)+share_url)}">{t("Email")}</a>'
    f'<button type="button" class="share-link" data-share="copy">{t("Copy link")}</button>')
   page_tools=f'<div class="share" data-share-url="{escape(share_url,quote=True)}" data-share-title="{share_title}" data-share-text="{escape(desc,quote=True)}" data-copied="{t("Link copied.")}" data-copy-prompt="{t("Copy this link:")}"><button type="button" class="share-toggle" aria-expanded="false" aria-controls="share-panel" hidden><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="18" cy="5" r="2.6"/><circle cx="6" cy="12" r="2.6"/><circle cx="18" cy="19" r="2.6"/><path d="m8.3 10.8 7.4-4.3m-7.4 6.7 7.4 4.3"/></svg>{t("Share")}</button><div class="share-panel" id="share-panel" role="group" aria-label="{t("Share this page")}"><span class="share-label">{t("Share this page")}</span>{share_links}<span class="share-status" role="status" aria-live="polite"></span></div></div>'
  page_tools=f'<div class="page-tools">{page_tools}{attribution}</div>'
  if key=='index':
   frag=frag.replace('</h1>','</h1>'+print_source,1)
   # The homepage date is shown with the page utilities below its editorial body.
  else:crumbs=crumbs.replace('</h1>','</h1>'+print_source,1)
 correction=''
 if key not in ('404','contact','contribute','review','rights','contributor-terms'):
  correction=f'<aside class="article-contribution" aria-label="{t("Contribute")}"><div><strong>{t("Help improve this page")}</strong><p>{t("Have a correction or a source to add? Share it with the editors.")}</p></div><a class="button secondary" data-correction href="contribute.html?type=correction&amp;page={key}.html">{t("Suggest a correction")} <span aria-hidden="true">↗</span></a></aside>'
 page_views=''
 if key not in ('404','contact','review'):
  view_path=canonical(key,lang).removeprefix(BASE)
  page_views=f'<p class="page-views" data-page-views="{escape(view_path,quote=True)}" hidden><span>{t("Page views")}:</span> <span data-view-count></span></p>'
 en_url=f'../{key}.html' if lang=='bn' else f'{key}.html'
 bn_url=f'{key}.html' if lang=='bn' else f'bn/{key}.html'
 picker=f'''<div class="language-control"><label for="language-picker">{t('Language')}</label><select id="language-picker" aria-label="{t('Language')}"><option lang="en" value="{en_url}"{' selected' if lang=='en' else ''}>English</option><option lang="bn" value="{bn_url}"{' selected' if lang=='bn' else ''}>বাংলা</option></select><noscript><a href="{en_url}" lang="en">English</a> / <a href="{bn_url}" lang="bn">বাংলা</a></noscript></div>'''
 if key in ENGLISH_ONLY_KEYS:
  picker='<div class="language-control"><span lang="en">English</span></div>'
 body=f'''<!DOCTYPE html>
<html lang="{lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="description" content="{escape(desc,quote=True)}"><meta name="theme-color" content="#273d35">{metadata(key,title,desc,lang,updated,parent=(parent,page_labels[parent]) if parent else None)}<link rel="icon" href="{assets}favicon.svg" type="image/svg+xml"><link rel="stylesheet" href="{assets}style.css"><link rel="stylesheet" href="{assets}print.css" media="print"><script src="{assets}search-index{'-bn' if lang=='bn' else ''}.js" defer></script><script src="{assets}app.js?v={hashlib.sha256((ROOT / 'assets/app.js').read_bytes()).hexdigest()[:12]}" defer></script><script src="{assets}push.js" defer></script>'''
 if key in ('history','culture','geography','surnames','about','bibliography'):
  body+=f'<link rel="stylesheet" href="{assets}parent-guides.css"><script src="{assets}parent-guides.js" defer></script>'
 # Page-specific visual systems keep documentary material and orientation maps prominent.
 if key in TEXT_ONLY_ARTICLE_KEYS:
  body=body.replace(f'<link rel="stylesheet" href="{assets}print.css" media="print">',
                    f'<link rel="stylesheet" href="{assets}history-articles.css"><link rel="stylesheet" href="{assets}print.css" media="print">')
 header_sheet = ('portrait-headers' if key == 'people' or key.startswith('person-') else
                 'document-headers' if key in ('archives','translations','bibliography','book-rajput-o-ugrakshatriya') or key.startswith('translation-') else
                 'places-map' if key == 'geography' else None)
 if header_sheet:
  body = body.replace(f'<link rel="stylesheet" href="{assets}print.css" media="print">',
                      f'<link rel="stylesheet" href="{assets}{header_sheet}.css"><link rel="stylesheet" href="{assets}print.css" media="print">')
 if key == 'aguris-freedom-struggle':
  sheet_hash=hashlib.sha256((ROOT/'assets/aguri-freedom-struggle.css').read_bytes()).hexdigest()[:12]
  body+=f'<link rel="stylesheet" href="{assets}aguri-freedom-struggle.css?v={sheet_hash}">'
 if key == 'military-settlers-bengal':
  sheet_hash=hashlib.sha256((ROOT/'assets/military-settlers.css').read_bytes()).hexdigest()[:12]
  body+=f'<link rel="stylesheet" href="{assets}military-settlers.css?v={sheet_hash}">'
 if key == 'person-manohar-ray':
  sheet_hash=hashlib.sha256((ROOT/'assets/manohar-research.css').read_bytes()).hexdigest()[:12]
  body+=f'<link rel="stylesheet" href="{assets}manohar-research.css?v={sheet_hash}">'
 if page_views:
  body+=f'<script src="{assets}page-views.js" defer></script>'
 if key=='index' and '<!-- weekly-feature -->' in frag:
  # Returning browsers must not reuse the earlier static feature's cached assets.
  weekly_css=hashlib.sha256((ROOT/'assets/weekly-feature.css').read_bytes()).hexdigest()[:12]
  weekly_js=hashlib.sha256((ROOT/'assets/weekly-feature.js').read_bytes()).hexdigest()[:12]
  body+=f'<link rel="stylesheet" href="{assets}weekly-feature.css?v={weekly_css}"><script src="{assets}weekly-feature.js?v={weekly_js}" defer></script>'
 if key=='contact':
  contact_css=hashlib.sha256((ROOT/'assets/contact.css').read_bytes()).hexdigest()[:12]
  contact_js=hashlib.sha256((ROOT/'assets/contact.js').read_bytes()).hexdigest()[:12]
  body+=f'<meta name="referrer" content="no-referrer"><link rel="stylesheet" href="{assets}contact.css?v={contact_css}"><script src="{assets}contact.js?v={contact_js}" defer></script>'
 if key in ('contribute','review'):
  sheet='contributions' if key=='contribute' else 'review'
  script_version=hashlib.sha256((ROOT/'assets'/f'{key}.js').read_bytes()).hexdigest()[:12]
  body+=f'<meta name="referrer" content="no-referrer"><link rel="stylesheet" href="{assets}{sheet}.css"><script src="{assets}{key}.js?v={script_version}" defer></script>'
 if key=='archives':
  body+=''.join(f'<script src="{assets}{file}.js" defer></script>' for file in ['reading-notes'+('-bn' if lang=='bn' else ''),'translation-links'+('-bn' if lang=='bn' else ''),'ocr-data','archive'])
 body+=f'''</head><body data-page="{key}" data-assets="{assets}"><a class="skip-link" href="#main">{t('Skip to content')}</a><div class="edition-bar"><span>{t('An independent community heritage project')}</span>{picker}</div><header class="site-header"><div class="header-inner"><a class="brand" href="index.html"><span class="brand-mark" aria-hidden="true">অ</span><span>{t('Aguri Heritage')}<small>{t('UGRA KSHATRIYA · WEST BENGAL')}</small></span></a><div class="header-tools"><a class="header-contribute" href="contribute.html">{t('Contribute')}</a><button type="button" class="search-open" aria-label="{t('Search')}" aria-haspopup="dialog"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="10" cy="10" r="6.5"/><path d="m15 15 6 6"/></svg><span>{t('Search')}</span></button><button type="button" class="menu-toggle" aria-expanded="false" aria-controls="main-nav">{t('Menu')} <span aria-hidden="true">☰</span></button></div><nav id="main-nav" class="main-nav" aria-label="{t('Main navigation')}">{nav}</nav></div></header><main id="main">{crumbs}{page_tools}{toc}{frag}{notes}{correction}{page_views}</main><footer class="site-footer"><div class="footer-top"><a class="footer-brand" href="index.html">{t('Aguri Heritage')}<span lang="bn">আগুরী · উগ্রক্ষত্রিয়</span></a><p>{t('History, culture and people.')}<br>{t('Connecting generations.')}</p><a class="footer-link" href="bibliography.html">{t('Explore the resources')} <span aria-hidden="true">↗</span></a></div><section class="notify" data-notify hidden aria-labelledby="notify-heading"><div><h2 id="notify-heading">{t('Get notified of new articles')}</h2><p>{t('New articles, major research updates and new family profiles. At most a few a month. No tracking.')} <a href="about.html#notifications">{t('About notifications')}</a></p></div><button type="button" class="button secondary notify-toggle" data-on="{t('Turn on notifications')}" data-off="{t('Turn off notifications')}">{t('Turn on notifications')}</button><p class="notify-status small" role="status" aria-live="polite"></p></section><div class="footer-bottom"><span>{t('Independent heritage project · English edition · 2026')}</span><a href="about.html#editorial">{t('Editorial approach')}</a><a href="contact.html">{t('Contact Us')}</a><a href="contribute.html">{t('Contribute to the collection')}</a></div><div class="footer-legal"><p>{t('© 2026 Aguri Heritage. Original project material: all rights reserved.')}<br><span>{t('Contributors and other rights holders retain their rights. See our reuse policy.')}</span></p><nav aria-label="{t('Rights and participation')}"><a href="rights.html">{t('Copyright & reuse')}</a><a href="contributor-terms.html">{t('Contributor terms')}</a></nav></div></footer><dialog id="search-dialog" aria-labelledby="search-title"><div class="dialog-heading"><h2 id="search-title">{t('Search the heritage project')}</h2><button class="search-close" aria-label="{t('Close search')}">×</button></div><label for="site-search">{t('Search English articles and source descriptions')}</label><input id="site-search" type="search" placeholder="{t('Try Bardhaman, origins, culture, Panja…')}" autocomplete="off"><p id="search-status" class="small" role="status">{t('Enter a word or phrase to begin.')}</p><div id="search-results"></div><p class="small">{t('For Bengali text inside the journals, use the')} <a href="archives.html#reader">{t('journal reader')}</a>.</p></dialog></body></html>'''
 if key=='index':
  body=render_homepage(body,frag+notes,page_tools,correction,page_views,updated_markup,lang)
 if key=='history':
  body=render_history(body,lang)
 if key=='culture':
  body=render_culture(body,lang,ARTWORKS)
 if key=='people':
  body=render_people(body,lang)
 # Add discussions after special page renderers replace the main template.
 if key not in ('404','contact','contribute','review','editor','admin'):
  comment_version=hashlib.sha256((ROOT/'assets/comments.js').read_bytes()).hexdigest()[:12]
  body=body.replace('</head>',f'<link rel="stylesheet" href="{assets}comments.css"><script src="{assets}comments.js?v={comment_version}" defer></script></head>')
  body=body.replace('</main>','<section class="page-comments" data-comments hidden aria-labelledby="comments-heading"></section></main>',1)
 if key=='review':
  review_version=hashlib.sha256((ROOT/'assets/comments-review.js').read_bytes()).hexdigest()[:12]
  body=body.replace('</head>',f'<link rel="stylesheet" href="{assets}comments.css"><script src="{assets}comments-review.js?v={review_version}" defer></script></head>')
  body=body.replace('</main>','<section class="page-comments" data-comments-review hidden aria-labelledby="comments-review-heading"></section></main>',1)
 if lang=='bn':
  body=re.sub(r'((?:href|src|data)=")assets/',r'\1../assets/',body)
 body=open_file_links(body)
 return body,{'title':title,'label':label,'url':f'{key}.html','text':plain(open_file_links(frag))}

def section_page_links(key,lang,editor_pages):
 """Keep new pages reachable from their selected section without source edits."""
 children=[entry for entry in editor_pages.values() if entry['section']==key]
 if not children:return ''
 heading='More in this section' if lang=='en' else 'এই বিভাগের আরও পাতা'
 links=''.join(f'<li><a class="text-link" href="{entry["id"]}.html">{escape(entry[lang]["title"])}</a><p>{escape(entry[lang]["description"])}</p></li>' for entry in children)
 return f'<section class="prose editor-page-directory" aria-labelledby="editor-added-pages"><h2 id="editor-added-pages">{heading}</h2><ul>{links}</ul></section>'

def build():
 history=PageHistory(ROOT)
 editor_pages=editor_page_map(ROOT)
 custom_descriptors={lang:editor_descriptors(ROOT,lang) for lang in ('en','bn')}
 OUT.mkdir(exist_ok=True);(OUT/'bn').mkdir(exist_ok=True)
 translation_fragments,translation_descriptors=render_translations()
 bn_fragments,bn_descriptors=render_bengali_readings()
 en_profiles,en_profile_descriptors=profiles('en')
 en_alignment_profiles,_=profiles('en',use_overrides=False)
 bn_profiles,bn_profile_descriptors=profiles('bn')
 translation_fragments.update(en_profiles);bn_fragments.update(bn_profiles)
 translation_descriptors+=en_profile_descriptors;bn_descriptors+=bn_profile_descriptors
 en_descriptors=PAGES+translation_descriptors+custom_descriptors['en']
 localized_descriptors=[(k,*PAGES_BN[k]) for k,*_ in PAGES if k not in ENGLISH_ONLY_KEYS]+bn_descriptors+custom_descriptors['bn']
 for lang,items in (('en',en_descriptors),('bn',localized_descriptors)):
  if len({key for key,*_ in items})!=len(items):raise ValueError(f'Duplicate {lang} website page addresses')
 shutil.copytree(ROOT/'assets',OUT/'assets',dirs_exist_ok=True)
 # The notification service worker must sit at the root to control every page.
 shutil.copyfile(ROOT/'push'/'sw.js',OUT/'sw.js')
 # Keep Bing ownership verification available at the website root on every rebuild.
 shutil.copyfile(ROOT/'content'/'BingSiteAuth.xml',OUT/'BingSiteAuth.xml')
 english={k:(translation_fragments[k] if k in translation_fragments else (ROOT/'content'/f'{k}.html').read_text())+section_page_links(k,'en',editor_pages) for k,*_ in en_descriptors}
 english_for_alignment=dict(english)
 paired_overrides=set(profile_overrides(lang='bn'))
 for key in profile_overrides():
  if key in en_alignment_profiles and key not in paired_overrides:
   english_for_alignment[key]=en_alignment_profiles[key]
 bn_sources=json.loads((ROOT/'content/bn/sources.json').read_text())
 if SOURCES.keys()!=bn_sources.keys():raise ValueError('Bengali source catalogue is incomplete')
 for lang in ('en','bn'):
  sources=SOURCES if lang=='en' else {k:{**s,**bn_sources[k]} for k,s in SOURCES.items()}
  pages=en_descriptors if lang=='en' else localized_descriptors
  # Retire generated biographies when their authored profile is removed.
  expected_profiles={key+'.html' for key,*_ in pages if key.startswith('person-')}
  for old_profile in (OUT/('bn' if lang=='bn' else '')).glob('person-*.html'):
   if old_profile.name not in expected_profiles:old_profile.unlink()
  labels={k:l for k,l,_,_ in pages};search=[]
  for key,label,title,desc in pages:
   frag=english[key] if lang=='en' else bn_fragments[key] if key in bn_fragments else (ROOT/'content/bn'/f'{key}.html').read_text()
   if lang=='bn':frag=align_headings(frag+section_page_links(key,lang,editor_pages),english_for_alignment[key])
   body,index=render_page(key,label,title,desc,frag,lang,sources,labels,history,editor_pages)
   (OUT/('bn' if lang=='bn' else '')/f'{key}.html').write_text(body)
   if key!='review':search.append(index)
  (OUT/'assets'/f'search-index{"-bn" if lang=="bn" else ""}.js').write_text('window.SITE_SEARCH = '+json.dumps(search,ensure_ascii=False)+';\n')
  label,title,desc=('পাতা পাওয়া যায়নি','পাতাটি পাওয়া যায়নি','লিঙ্কটি বদলে গিয়ে থাকতে পারে। প্রচ্ছদে ফিরে যান বা অনুসন্ধান করুন।') if lang=='bn' else ('Page not found','This page could not be found','The link may have changed. Return to the home page or search the collection.')
  text='প্রচ্ছদে ফিরে যান' if lang=='bn' else 'Return to the home page'
  error,_=render_page('404',label,title,desc,f'<div class="prose"><p><a class="text-link" href="index.html">{text} →</a></p></div>',lang,sources,labels,history)
  # A fallback can be served at any path depth. Resolve its assets and navigation
  # against the real edition root, not the missing URL's directory.
  origin=BASE+('/bn/' if lang=='bn' else '/')
  error=error.replace('<body ',f'<body data-search-root="{origin}" ',1)
  error=re.sub(r'((?:href|src|data-assets|value)=")([^"#][^"]*)"',lambda m:m[1]+escape(urljoin(origin,unescape(m[2])),quote=True)+'"',error)
  (OUT/('bn' if lang=='bn' else '')/'404.html').write_text(error)
  print(f'Built {len(pages)} {lang} pages')
 # The approved story carousel is authored in the homepage body. Retain the
 # older weekly subsystem only for homepages that explicitly request its slot.
 homepages={lang:OUT/('bn' if lang=='bn' else '')/'index.html' for lang in ('en','bn')}
 markers={lang:page.read_text().count('<!-- weekly-feature -->') for lang,page in homepages.items()}
 if any(markers.values()):
  if any(count!=1 for count in markers.values()):
   raise ValueError('Weekly feature requires one insertion point in both homepage editions')
  feature_descriptors={
   'en':en_descriptors,
   'bn':localized_descriptors,
  }
  features=prepare_weekly_feature(ROOT,history.data['pages'],feature_descriptors)
  for lang,homepage in homepages.items():
   feature=features[lang]
   if lang=='bn':
    feature=re.sub(r'((?:src|href)=")assets/',r'\1../assets/',feature)
   homepage.write_text(homepage.read_text().replace('<!-- weekly-feature -->',feature))
 history.save()
 write_discovery(OUT,[k for k,*_ in en_descriptors if k!='review'],
                 {key:entry['updated'] for key,entry in history.data['pages'].items()})
 if os.environ.get('AGURI_CI_BUILD') != '1':
  (ROOT.parent/'index-preview.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta http-equiv="refresh" content="0;url=aguri-heritage/site/index.html"><title>Aguri Heritage</title><p><a href="aguri-heritage/site/index.html">Open Aguri Heritage</a></p></html>')

if __name__=='__main__':build()
