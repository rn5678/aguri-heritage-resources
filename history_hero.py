"""History's story carousel, generated from the existing bilingual story cards.

Images are already-published assets; source cards remain the editorial authority.
History and Culture share its renderer and controls. Source cards remain intact.
"""
from html import escape
from html.parser import HTMLParser
from pathlib import Path
from asset_paths import is_local_asset
from urllib.parse import urlsplit
import re
import json

ROOT = Path(__file__).resolve().parent
IMAGES = {'origins': {'file': 'assets/page-artworks/origins-armoured.webp',
             'width': 1536,
             'height': 1024,
             'alt_en': 'Artistic interpretation of a mounted Nagadee warrior in chest armour beside a '
                       'river and paddy fields in Burdwan.',
             'alt_bn': 'বর্ধমানের নদী ও ধানখেতের পাশে বক্ষবর্ম পরা অশ্বারোহী নগদী যোদ্ধার শিল্পিত '
                       'চিত্রায়ণ।',
             'caption_en': 'Contemporary illustration · Mounted Nagadee warrior; artistic '
                           'interpretation, not historical evidence.',
             'caption_bn': 'আধুনিক কল্পচিত্র · অশ্বারোহী নগদী যোদ্ধার শিল্পিত চিত্রায়ণ; '
                           'ঐতিহাসিক প্রমাণ নয়।',
             'image_fit': 'cover'},
 'bangsha-parichay-aguri-origins': {'file': 'assets/bangsha-parichay/kulapanjika-illustration.webp',
                                 'width': 1672,
                                 'height': 941,
                                 'alt_en': 'Illustration of an aged open family register with branching lineage lines, resting on a wooden reading board beside a bundle of folios.',
                                 'alt_bn': 'কাঠের পাঠপীঠে রাখা বংশতালিকার শাখারেখাসহ পুরোনো খোলা কুলপঞ্জিকার কল্পচিত্র; পাশে বাঁধা পুথির পাতা।',
                                 'caption_en': 'Kulapanjika-inspired artwork · Contemporary illustration',
                                 'caption_bn': 'কুলপঞ্জিকা-অনুপ্রাণিত শিল্পকর্ম · কল্পচিত্র',
                                 'image_fit': 'contain'},
 'aguri-jotedars-dar-patnidars': {'file': 'assets/page-artworks/geography.webp',
                                  'width': 1536,
                                  'height': 1024,
                                  'alt_en': 'An elevated view follows a Bengal river from red-earth '
                                            'groves into a patchwork of fertile fields.',
                                  'alt_bn': 'উঁচু থেকে দেখা বাংলার নদী লালমাটির বনানী ছেড়ে উর্বর খেতের '
                                            'মাঝে বয়ে চলেছে।',
                                  'caption_en': 'A contemporary topic illustration',
                                  'caption_bn': 'বিষয়ভিত্তিক কল্পিত চিত্র',
                                  'image_fit': 'cover'},
 'aguris-recognition': {'file': 'assets/volume-1-cover.jpg',
                        'width': 1404,
                        'height': 2004,
                        'alt_en': 'Original Bengali title page of Ugrakshatriya-Pratinidhi, volume 1, '
                                  'with handwritten labels and library stamps.',
                        'alt_bn': 'উগ্রক্ষত্রিয়-প্রতিনিধির প্রথম খণ্ডের মূল বাংলা নামপত্র; হাতে লেখা '
                                  'চিরকুট ও গ্রন্থাগারের সিলসহ।',
                        'caption_en': 'Ugrakshatriya-Pratinidhi · Volume 1',
                        'caption_bn': 'উগ্রক্ষত্রিয়-প্রতিনিধি · প্রথম খণ্ড',
                        'image_fit': 'contain'},
 'research': {'file': 'assets/page-artworks/archives.webp',
              'width': 1536,
              'height': 1024,
              'alt_en': 'Bound periodicals and blank pages rest on a reading table in a shaded Bengal '
                        'library.',
              'alt_bn': 'বাংলার ছায়াঘেরা গ্রন্থাগারের পাঠের টেবিলে বাঁধানো পত্রিকা ও সাদা পাতা রাখা।',
              'caption_en': 'Archives, memory and new research · A contemporary illustration',
              'caption_bn': 'নথি, স্মৃতি ও নতুন গবেষণা · সমকালীন কল্পচিত্র',
              'image_fit': 'cover'}}

IMAGES['military-settlers-bengal'] = {'file': 'assets/military-settlers/carousel.webp', 'width': 1536, 'height': 1024, 'alt_en': 'Imagined early modern military household travelling by boat towards a Bengal riverside settlement.', 'alt_bn': 'নৌকায় বাংলার নদীতীরবর্তী বসতির দিকে যাত্রারত এক আদি আধুনিক সামরিক পরিবারের কল্পচিত্র।', 'caption_en': 'Contemporary illustration · An imagined journey, not a recorded event.', 'caption_bn': 'কল্পচিত্র · কোনও নথিভুক্ত ঘটনার চিত্র নয়।', 'image_fit': 'cover'}

IMAGES['aguris-freedom-struggle'] = {'file': 'assets/aguri-freedom-struggle/cover.webp', 'width': 1536, 'height': 1024, 'alt_en': 'Aguris in the freedom struggle and its impact on Aguri society through the 1950s, illustrated with marchers, a political assembly, cultivated fields and a lending ledger.', 'alt_bn': 'পঞ্চাশের দশক পর্যন্ত স্বাধীনতা সংগ্রামে আগুরীদের ভূমিকা ও আগুরী সমাজে তার প্রভাব: মিছিল, রাজনৈতিক সমাবেশ, কৃষিজমি ও ঋণদানের খাতার প্রতীকী চিত্র।', 'caption_en': 'Contemporary illustration · Burdwan and Bengal through the 1950s.', 'caption_bn': 'আধুনিক অলংকরণ · পঞ্চাশের দশক পর্যন্ত বর্ধমান ও বাংলা।', 'image_fit': 'contain'}

# Reuse the published article artwork and its bilingual disclosure.
IMAGES['ugra-kshatriya-patrika'] = {**json.loads((ROOT / 'assets/page-artworks/catalog.json').read_text())['ugra-kshatriya-patrika'], 'image_fit': 'contain'}
for language in ('en', 'bn'):
 IMAGES['ugra-kshatriya-patrika']['caption_' + language] = IMAGES['ugra-kshatriya-patrika']['title_' + language] + ' · ' + IMAGES['ugra-kshatriya-patrika']['caption_' + language]

LABELS = {
 'en': {'carousel':'carousel','slide':'slide','pause':'Pause rotation','resume':'Resume rotation',
        'reduced':'Auto-rotation off: reduced motion','previous':'Previous story','next':'Next story',
        'show':'Show story','all':'All eight stories below','read':'Read the story','english':'Read in English',
        'controls':'Story controls'},
 'bn': {'carousel':'ক্যারোসেল','slide':'স্লাইড','pause':'ঘূর্ণন থামান','resume':'আবার ঘূর্ণন চালু করুন',
        'reduced':'কম নড়াচড়ার পছন্দে স্বয়ংক্রিয় ঘূর্ণন বন্ধ','previous':'আগের কাহিনি','next':'পরের কাহিনি',
        'show':'কাহিনি দেখুন','all':'নিচে আটটি কাহিনি দেখুন','read':'কাহিনি পড়ুন','english':'ইংরেজিতে পড়ুন',
        'controls':'কাহিনি দেখার নিয়ন্ত্রণ'},
}

class Stories(HTMLParser):
 def __init__(self):
  super().__init__(convert_charrefs=True)
  self.cards=[];self.current=None;self.field=None;self.in_title=False;self.heading=[];self.in_heading=False
 def handle_starttag(self,tag,attrs):
  attrs=dict(attrs)
  if tag=='h2':self.in_heading=True
  if tag=='article' and 'guide-card' in attrs.get('class','').split():
   self.current={'kicker':[],'title':[],'summary':[],'link':{}}
  if self.current is None:return
  if tag=='h3':self.in_title=True;self.field='title'
  if tag=='a' and self.in_title:self.current['link']=attrs
  if tag=='p':
   classes=attrs.get('class','').split()
   self.field='kicker' if 'guide-kicker' in classes else 'summary' if 'guide-description' in classes else None
 def handle_endtag(self,tag):
  if tag=='h2':self.in_heading=False
  if tag=='h3':self.in_title=False;self.field=None
  if tag=='p':self.field=None
  if tag=='article' and self.current is not None:
   card=self.current
   for key in ('kicker','title','summary'):card[key]=''.join(card[key]).strip()
   if not all(card[key] for key in ('kicker','title','summary')) or not card['link'].get('href'):
    raise ValueError('History carousel: a story card is missing its title, summary, kicker or link')
   self.cards.append(card);self.current=None;self.field=None
 def handle_data(self,data):
  if self.in_heading:self.heading.append(data)
  if self.current is not None and self.field:self.current[self.field].append(data)

def render_hero(body,lang):
 """Replace only History's topic figure; leave its title and editorial body intact."""
 match=re.search(r'<section\b[^>]*aria-labelledby="explore-history-stories"[^>]*>.*?</section>',body,re.S)
 if not match:raise ValueError('History carousel: the story collection was not found')
 parsed=Stories();parsed.feed(match.group(0));cards=parsed.cards
 if len(cards)!=8:raise ValueError('History carousel: review the eight-story inventory before changing its size')
 hero=carousel_markup(cards,''.join(parsed.heading).strip(),lang,IMAGES,LABELS[lang],
                      'history-hero','explore-history-stories')
 return replace_artwork(body,hero)

def carousel_markup(cards,heading,lang,images,label,id_prefix,collection_id):
 """Build the shared carousel from a reviewed, language-specific story inventory."""
 number=lambda n:str(n).translate(str.maketrans('0123456789','০১২৩৪৫৬৭৮৯')) if lang=='bn' else str(n)
 slides=[];indicators=[]
 for index,card in enumerate(cards):
  key=Path(urlsplit(card['link']['href']).path).stem
  if key not in images:raise ValueError('History carousel: no reviewed image for '+key)
  image=images[key];asset=ROOT/image['file']
  if not is_local_asset(ROOT,asset):
   raise ValueError('History carousel: missing local image '+image['file'])
  sid=f'{id_prefix}-slide-{index+1}';title_id=sid+'-title';summary_id=sid+'-summary'
  src=('../' if lang=='bn' else '')+image['file'];title_lang=card['link'].get('lang',lang)
  hreflang=f' hreflang="{escape(card["link"]["hreflang"],quote=True)}"' if card['link'].get('hreflang') else ''
  load='fetchpriority="high" loading="eager"' if index==0 else 'loading="lazy"'
  cta=label['english'] if lang=='bn' and card['link'].get('hreflang')=='en' else label['read']
  slides.append(f'''<article class="history-hero-slide" id="{sid}" data-hero-title="{escape(card['title'],quote=True)}" role="group" aria-roledescription="{label['slide']}" aria-label="{number(index+1)} / {number(len(cards))}">
<a class="history-hero-link" href="{escape(card['link']['href'],quote=True)}"{hreflang} aria-labelledby="{title_id}" aria-describedby="{summary_id}">
<figure class="history-hero-media history-hero-media--{image['image_fit']}"><img src="{escape(src,quote=True)}" alt="{escape(image['alt_'+lang],quote=True)}" width="{image['width']}" height="{image['height']}" {load} decoding="async"><figcaption>{escape(image['caption_'+lang])}</figcaption></figure>
<div class="history-hero-copy"><p class="history-hero-kicker">{escape(card['kicker'])}</p><h2 id="{title_id}" lang="{escape(title_lang)}">{escape(card['title'])}</h2><p class="history-hero-summary" id="{summary_id}">{escape(card['summary'])}</p><span class="history-hero-read">{cta} <span aria-hidden="true">↗</span></span></div>
</a></article>''')
  indicators.append(f'<button type="button" data-hero-indicator="{index}" aria-controls="{sid}" aria-label="{escape(label["show"]+" "+number(index+1)+": "+card["title"],quote=True)}">{number(index+1)}</button>')
 hero=(f'<section class="history-hero" data-history-carousel data-interval="12000" data-pause-label="{label["pause"]}" data-resume-label="{label["resume"]}" data-reduced-label="{label["reduced"]}" role="region" aria-roledescription="{label["carousel"]}" aria-labelledby="{id_prefix}-label">'
       f'<p class="history-hero-label" id="{id_prefix}-label">{escape(heading)}</p>'
       f'<div class="history-hero-controls" role="group" aria-label="{label["controls"]}" hidden>'
       f'<button type="button" data-hero-toggle>{label["pause"]}</button>'
       f'<button type="button" data-hero-prev aria-label="{label["previous"]}" aria-controls="{id_prefix}-track"><span aria-hidden="true">←</span></button>'
       f'<button type="button" data-hero-next aria-label="{label["next"]}" aria-controls="{id_prefix}-track"><span aria-hidden="true">→</span></button>'
       '<div class="history-hero-indicators">'+''.join(indicators)+'</div>'
       '<span class="history-hero-status" data-hero-status aria-live="off" aria-atomic="true"></span>'
       f'<a class="history-hero-all" href="#{collection_id}">{label["all"]} ↓</a></div>'
       f'<div class="history-hero-track" id="{id_prefix}-track">'+''.join(slides)+'</div></section>')
 return hero

def replace_artwork(body,hero):
 """Replace one opening figure; preserve every editorial card and source anchor."""
 body,count=re.subn(r'<figure class="page-artwork">.*?</figure>',lambda _:hero,body,count=1,flags=re.S)
 if count!=1:raise ValueError('History carousel: expected one opening artwork')
 return body
