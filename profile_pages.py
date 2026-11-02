"""Build individual biographies and collection previews from the authored profiles."""
from html import escape, unescape
from html.parser import HTMLParser
from pathlib import Path
import json
import re
from portrait_headers import PROFILE_PATTERN, PHOTO_PATTERN, profile_name_heading, profile_secondary_artwork
from localization import STANDALONE_PROFILE_KEYS

ROOT = Path(__file__).parent
PATTERN = PROFILE_PATTERN

class Text(HTMLParser):
 def __init__(self, html):
  super().__init__(); self.parts=[]; self.feed(html)
 def handle_data(self, data): self.parts.append(data)

def plain(html):
 return ' '.join(' '.join(Text(re.sub(r'\[cite:[\w-]+\]', '', html)).parts).split())

def profile_overrides(root=None, lang='en'):
 """Read independent biographies for one explicitly selected edition."""
 if lang not in ('en', 'bn'):
  raise ValueError('Unsupported profile language: '+str(lang))
 root = Path(root) if root is not None else ROOT
 source = (root/'content'/('bn' if lang=='bn' else '')/'people.html').read_text()
 known = {slug for slug, _ in re.findall(PATTERN, source, re.S)}
 result = {}
 suffix = '.'+lang+'.json'
 for path in sorted((root/'content/profiles').glob('*'+suffix)):
  slug = path.name.removesuffix(suffix)
  if slug not in known and 'person-'+slug not in STANDALONE_PROFILE_KEYS:
   raise ValueError('Standalone profile override has no collection entry: '+slug)
  value = json.loads(path.read_text())
  if (not isinstance(value,dict) or set(value) != {'title','subtitle','body'} or
      any(not isinstance(value[field],str) or not value[field].strip()
          for field in ('title','subtitle','body'))):
   raise ValueError('Standalone profile override requires title, subtitle and body: '+slug)
  if re.search(r'<h1\b',value['body'],re.I):
   raise ValueError('Standalone profile body must follow its page title: '+slug)
  result['person-'+slug] = value
 return result


def profiles(lang, use_overrides=True):
 if lang not in ('en', 'bn'):
  raise ValueError('Unsupported profile language: '+str(lang))
 source = (ROOT/'content'/('bn' if lang=='bn' else '')/'people.html').read_text()
 fragments = {}; descriptors=[]
 def article(match):
  slug, body = match.group(1,2)
  opening = match.group(0).split('>',1)[0]+'>'
  name_heading = profile_name_heading(slug, body, opening)
  identity = re.search(r'\bdata-editor-title="([^"]+)"',opening)
  name = plain(name_heading.group(1)) if name_heading else unescape(identity.group(1)) if identity else ''
  if not name:
   raise ValueError('Biography needs its authored heading or preserved editor identity: '+slug)
  key = 'person-'+slug
  copy_match = re.search(r'<div\b[^>]*class="person-copy"[^>]*>(.*)</div>\s*$',body,re.S)
  if not copy_match: raise ValueError('Biography is missing its copy container: '+slug)
  copy = copy_match.group(1)
  paragraphs = list(re.finditer(r'<p\b(?![^>]*\bclass=)[^>]*>(.*?)</p>',copy,re.S))
  first = plain(paragraphs[0].group(1)) if paragraphs else ''
  description = re.split(r'(?<=[.!?।])\s+',first)[0]
  subtitle = re.search(r'<p\b[^>]*class="person-subtitle"[^>]*>(.*?)</p>',copy,re.S)
  if subtitle: description = plain(subtitle.group(1))
  context = ''
  if slug in ('ajit-kumar-panja','ranjit-kumar-panja','shakti-samanta','benoy-krishna-konar','nikhilananda-sar'):
   context = ('এই ব্যক্তির নাম উইকিপিডিয়ার আগুরী নিবন্ধের বিশিষ্ট ব্যক্তিদের তালিকায় রয়েছে। জীবনীতে ব্যবহৃত সূত্রগুলি তাঁর জীবন ও কাজের বিবরণ দেয়।[cite:aguri-reference]' if lang=='bn' else
              'This profile follows the notable-person list in Wikipedia’s Aguri article. The biographical sources cited here document the person’s life and work.[cite:aguri-reference]')
  # Konar and Tah profiles carry their own Dutta community-source notes.
  # Other biographies already contain their individual community-source note.
  heading = 'জীবন ও কাজ' if lang=='bn' else 'Life and work'
  full_body = body
  if name_heading:
   replacement = re.sub(r'(<h2[^>]*>).*?(</h2>)',lambda m:m[1]+heading+m[2],name_heading.group(0),count=1,flags=re.S)
   full_body = body[:name_heading.start()]+replacement+body[name_heading.end():]
  full_body = re.sub(r'<p\b[^>]*class="person-subtitle"[^>]*>.*?</p>', '', full_body, count=1, flags=re.S)
  # The exact authored photograph and its complete credits now lead the page.
  full_body = re.sub(PHOTO_PATTERN, '', full_body, count=1, flags=re.S)
  if context and paragraphs:
   full_body = re.sub(r'</div>\s*$',f'<p class="small">{context}</p></div>',full_body)
  back = 'সব ব্যক্তিত্বের পরিচয় পড়ুন' if lang=='bn' else 'Explore all featured personalities'
  connection = 'সংগ্রহে অন্তর্ভুক্তির সূত্র' if lang=='bn' else 'How the collection was selected'
  artwork = profile_secondary_artwork(key, lang)
  visibility = (' data-editor-title-hidden="true"' if not name_heading else '') + (' data-editor-description-hidden="true"' if not description else '')
  fragments[key] = f'<div class="person-profiles person-biography"><article class="person-profile" aria-labelledby="{slug}"{visibility}>{full_body}</article></div>{artwork}<div class="prose profile-navigation"><p><a class="text-link" href="people.html#{slug}">{back} →</a></p><p><a href="people.html#community-connections">{connection}</a></p></div>'
  descriptors.append((key,name,name,description or name))
  # Keep the old section anchors, portrait credits and affiliation qualifications.
  before = body[:copy_match.start()]
  intro = copy[:paragraphs[0].start()] if paragraphs else copy
  qualifications = ''.join(re.findall(r'<p\b[^>]*class="small"[^>]*>.*?</p>',copy,re.S)) if paragraphs else ''
  preview = paragraphs[0].group(0) if paragraphs else ''
  link = (f'{name} — সম্পূর্ণ পরিচয় পড়ুন' if lang=='bn' else f'Read the full profile of {name}') if name_heading else ('সম্পূর্ণ পরিচয় পড়ুন' if lang=='bn' else 'Read the full profile')
  return f'{opening}{before}<div class="person-copy">{intro}{preview}{qualifications}<p><a class="text-link" href="{key}.html">{escape(link)} →</a></p></div></article>'
 collection = re.sub(PATTERN,article,source,flags=re.S)
 if not descriptors: raise ValueError(f'No {lang} biographies found')
 if len({item[0] for item in descriptors})!=len(descriptors):
  raise ValueError(f'Duplicate {lang} biography identifiers')
 fragments['people'] = collection
 # Independent editions retain the collection's existing text and navigation.
 if use_overrides:
  for key, override in profile_overrides(lang=lang).items():
   if key not in fragments:
    if key not in STANDALONE_PROFILE_KEYS:
     raise ValueError('Standalone biography requires an explicit route: '+key)
    back = 'সব ব্যক্তিত্বের পরিচয় পড়ুন' if lang=='bn' else 'Explore all featured personalities'
    fragments[key] = (override['body'] + '<div class="prose profile-navigation"><p>'
                      '<a class="text-link" href="people.html">'+back+' →</a>'
                      '</p></div>')
    descriptors.append((key,override['title'],override['title'],override['subtitle']))
    continue
   old = fragments[key]
   navigation = re.search(r'<div class="prose profile-navigation">.*$',old,re.S)
   if not navigation:
    raise ValueError('Standalone biography is missing its collection links: '+key)
   slug = key.removeprefix('person-')
   artwork = profile_secondary_artwork(key, lang) if lang=='bn' else ''
   visibility = (' data-editor-title-hidden="true"' if 'data-editor-title-hidden="true"' in old else '')
   fragments[key] = '<div id="'+slug+'"'+visibility+'>'+override['body']+'</div>'+artwork+navigation[0]
   descriptors = [(k,label,override['title'],override['subtitle']) if k==key else (k,label,title,description)
                  for k,label,title,description in descriptors]
 return fragments, descriptors
