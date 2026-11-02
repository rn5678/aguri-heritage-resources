"""Bengali reading interfaces use original scans, never a back-translation posing as an original."""
from pathlib import Path
from html import escape as e
import json
from localization import num
ROOT=Path(__file__).resolve().parent

def render_bengali_readings():
 metadata=json.loads((ROOT/'content/bn/readings.json').read_text())
 originals=sorted((json.loads(p.read_text()) for p in (ROOT/'content/translations').glob('*.json')),key=lambda a:a['order'])
 assert set(metadata)=={a['slug'] for a in originals}
 fragments={};descriptors=[];cards=[];scan_links={}
 for a in originals:
  slug=a['slug'];b=metadata[slug];key='translation-'+slug;url=key+'.html'
  complete=a['scope'].startswith('Complete')
  word_count=sum(len(p.split()) for block in a['blocks'] for p in block['paragraphs'])
  minutes=max(1,round(word_count/200))
  ending='এই সম্পূর্ণ নির্বাচিত পাঠের সমাপ্তি।' if complete else 'শুধু সূচনাপৃষ্ঠার এই অংশের সমাপ্তি; সম্পূর্ণ সম্পাদকীয় নয়।'
  assert len(a['blocks'])==len(b['sections']),slug
  cards.append(f'<article class="translation-card"><p class="eyebrow">{e(b["date"])}</p><span class="evidence-tag">{e(b["scope"])}</span><h3><a href="{url}">{e(b["title"])}</a></h3><p>{e(b["description"])}</p><p class="translation-card-source">{e(b["collection"])}<br>ইংরেজি অনুবাদ পড়তে প্রায় {num(minutes,"bn")} মিনিট</p><a class="text-link" href="{url}">বাংলা মূল ও ইংরেজি অনুবাদ দেখুন →</a></article>')
  sections=[];seen={};transcripts=[]
  for n,(block,(title,location)) in enumerate(zip(a['blocks'],b['sections']),1):
   image=block['image'];source_id=f'original-{n}'
   reader=f'<a href="{e(block["reader"],quote=True)}">সাময়িকপত্রের পাঠাগারে খুলুন ↗</a>' if block.get('reader') else ''
   if block.get('reader'):scan_links[Path(image).stem]={'title':b['title'],'url':url,'scope':b['scope']}
   if image not in seen:
    source=f'<figure class="bengali-original" id="{source_id}"><a href="{image}" aria-label="{e(location,quote=True)}: মূল পাতা বড় করে দেখুন"><img src="{image}" alt="বাংলা মূল: {e(location,quote=True)}" loading="lazy"></a><figcaption>{e(location)} · <a href="{image}">পূর্ণ আকারে খুলুন ↗</a> {reader}</figcaption></figure>'
    seen[image]=source_id
   else:source=f'<p class="source-repeat"><a href="#{seen[image]}">এই অংশের বাংলা মূল আগের স্ক্যানেই রয়েছে ↑</a> · {e(location)} · {reader}</p>'
   transcript=''
   if block.get('bengali'):
    transcript='<div class="bengali-transcription"><p class="eyebrow">স্ক্যানের সঙ্গে মেলানো বাংলা প্রতিলিপি</p>'+''.join(f'<p>{e(p)}</p>' for p in block['bengali'])+'</div>'
    transcripts += [location,*block['bengali'],'']
   english='<details class="english-comparison"><summary>এই অংশের ইংরেজি অনুবাদ পড়ুন</summary><div lang="en">'+''.join(f'<p>{e(p)}</p>' for p in block['paragraphs'])+'</div></details>'
   sections.append(f'<section class="bengali-reading-section" aria-labelledby="passage-{n}"><h2 id="passage-{n}">{e(title)}</h2><p class="translation-location">{e(location)}</p>{source}{transcript}{english}</section>')
  download=f'<a href="assets/translations/{slug}-english.txt" download>ইংরেজি অনুবাদ ডাউনলোড ↓</a>'
  if transcripts:
   filename=slug+'-bengali.txt'
   text=[a['bengaliTitle'],b['author'],b['collection'],b['scope'],'স্ক্যানের সঙ্গে মেলানো বাংলা প্রতিলিপি। পাঠযোগ্য ঐতিহাসিক বানান রাখা হয়েছে; পঙ্‌ক্তির শেষে ভাগ করা শব্দ জোড়া হয়েছে। স্বাধীন ভাষা-পর্যালোচনা সম্পন্ন নয়।','',*transcripts]
   (ROOT/'assets/translations'/filename).write_text('\n\n'.join(text)+'\n')
   download+=f'<a href="assets/translations/{filename}" download>বাংলা প্রতিলিপি ডাউনলোড ↓</a>'
  if a.get('ocr'):download+=f'<a href="assets/translations/{a["ocr"]}" download>অযাচাইকৃত বাংলা যন্ত্রপাঠ ডাউনলোড ↓</a>'
  if a['source']=='rajput-1940':download+='<a href="book-rajput-o-ugrakshatriya.html#read-bengali-book">সম্পূর্ণ বাংলা বই পড়ুন ↗</a>'
  fragments[key]=f'''<article class="translation-article bengali-reading-edition"><div class="translation-intro"><p class="translation-byline">{e(b['author'])} · {e(b['date'])}</p><p>{e(b['collection'])} [cite:{a['source']}]</p><p class="translation-scope"><strong>{e(b['scope'])}</strong><span>ইংরেজি অনুবাদে {num(f"{word_count:,}","bn")}টি শব্দ · পড়তে প্রায় {num(minutes,"bn")} মিনিট</span></p><div class="translation-context"><p class="eyebrow">এই পাঠের পরিচয়</p><p>{e(b['editorial'])}</p><details class="translation-notes"><summary>পাঠ ও অনুবাদ সম্পর্কে টীকা</summary><ol>{''.join('<li>'+e(note)+'</li>' for note in b['notes'])}</ol></details></div><div class="translation-downloads">{download}</div><p class="translation-help">নিচে বাংলা মূলের মুদ্রিত পাতা পড়ুন; ছবিতে চাপ দিলে পূর্ণ আকারে খুলবে। যাচাই করা প্রতিলিপি থাকলে তার নিচে দেওয়া হয়েছে। ইংরেজি অনুবাদ আলাদাভাবে খুলে মিলিয়ে পড়তে পারেন। অংশের শিরোনাম সম্পাদনাকালে যোগ করা; মূল পাতার নম্বর ও স্ক্যান নম্বর পৃথক।</p><p class="small">ইংরেজি পাঠ-অনুবাদ স্ক্যানের সঙ্গে মেলানো হয়েছে; স্বাধীন ভাষা-পর্যালোচনা সম্পন্ন নয়। অযাচাইকৃত যন্ত্রপাঠ উদ্ধৃতির আগে মূল ছবির সঙ্গে মিলিয়ে নিন।</p></div>{''.join(sections)}<div class="translation-end"><p>{ending}</p><a class="text-link" href="translations.html">← সব পাঠ ও অনুবাদ দেখুন</a></div></article>'''
  descriptors.append((key,'পাঠ ও অনুবাদ',b['title'],b['description']))
 complete_count=sum(a['scope'].startswith('Complete') for a in originals)
 extract_count=len(originals)-complete_count
 fragments['translations']=f'''<div class="translation-collection-intro"><p class="lead">বাংলা উৎস পড়ুন, ইংরেজি অনুবাদ মিলিয়ে দেখুন।</p><p><em>রাজপুত ও উগ্রক্ষত্রিয়</em> এবং নির্বাচিত ঐতিহাসিক প্রবন্ধ, ভূমিকা ও সমালোচনার মাধ্যমে আগুরী ঐতিহ্য জানুন। বই ও সাময়িকপত্রে সমাজের ইতিহাস, শিক্ষা ও সামাজিক জীবনের বিভিন্ন দৃষ্টিভঙ্গি পাওয়া যায়। তুলনার জন্য বাংলা মূল সংরক্ষিত।</p><div class="translation-collection-count"><span><b>০১</b> বইয়ের ইংরেজি অনুবাদ</span><span><b>{num(f"{complete_count:02d}","bn")}</b> সম্পূর্ণ নির্বাচিত রচনা</span><span><b>{num(f"{extract_count:02d}","bn")}</b> সূচনাপৃষ্ঠার অংশ</span><span><b>১৮৯১–১৯৪০</b> মূল প্রকাশকাল</span></div><p class="small">সম্পূর্ণ নির্বাচিত রচনা বলতে নির্দিষ্ট প্রবন্ধ, সমালোচনা ও ভূমিকা বোঝায়। পত্রিকার খণ্ডগুলি আংশিক অনূদিত। বইয়ের অনুবাদে সংরক্ষিত পাঠ রয়েছে; ডিজিটাল মূল থেকে দুটি মুদ্রিত পাতা অনুপস্থিত।</p></div>
<section class="translated-book-feature" aria-labelledby="translated-book"><div><p class="eyebrow">ঐতিহাসিক বই · বাংলা মূল · ৯৮ পাতার ইংরেজি অনুবাদ</p><h2 id="translated-book">রাজপুত ও উগ্রক্ষত্রিয়</h2><p>বংশপরিচয়, আগরী নাম, রাঢ় এবং পাল ও সেন রাজাদের নিয়ে হরিচরণ বন্ধুর বিবরণ। নয়টি অধ্যায়, সংরক্ষিত উপসংহার, ভূমিকা, মূল শুদ্ধিপত্র এবং ইংরেজি সংস্করণের শেষে অনুবাদকের টীকা পড়ুন।</p><p class="small">বাংলা মূলের অনুপস্থিত ১৪২–১৪৩ পাতার শূন্যস্থান চিহ্নিত। অনিশ্চিত পাঠ অনুবাদে উল্লেখ করা হয়েছে।</p></div><div class="actions"><a class="button" href="book-rajput-o-ugrakshatriya.html#read-bengali-book">বাংলা বই পড়ুন →</a><a class="button secondary" href="book-rajput-o-ugrakshatriya.html#english-translation">ইংরেজি অনুবাদ →</a></div></section>
<section aria-labelledby="translated-readings"><div class="section-heading"><div><p class="eyebrow">সাময়িকপত্র ও ঐতিহাসিক বই</p><h2 id="translated-readings">একটি পাঠ বেছে নিন</h2></div></div><div class="translation-grid">{''.join(cards)}</div></section><div class="prose"><h2 id="english-text-bengali-evidence">ইংরেজি পাঠ, বাংলা সাক্ষ্য</h2><p>অনুবাদগুলি মূল স্ক্যানের সঙ্গে মিলিয়ে পড়ার জন্য। লেখকের যুক্তি ও ঐতিহাসিক ভাষা রাখা হয়েছে; টীকায় প্রেক্ষাপট ও অনিশ্চিত পাঠ চিহ্নিত। স্বাধীন ভাষা-পর্যালোচনা সম্পন্ন নয়।</p><p>বইয়ের দুটি ভূমিকায় বাংলা প্রতিলিপি রয়েছে। নির্বাচিত সাময়িকপত্রের রচনায় ডাউনলোডযোগ্য যন্ত্রপাঠ স্পষ্টভাবে অযাচাইকৃত বলে চিহ্নিত। প্রতিটি রচনার ইংরেজি পাঠও ডাউনলোড করা যায়। সংক্ষিপ্ত টীকা <a href="archives.html#reader">সাময়িকপত্রের পাঠাগারে</a> রয়েছে।</p><p>ঐতিহাসিক লেখায় বিতর্কিত উৎপত্তিতত্ত্ব, পুরোনো বিজ্ঞান বা সামাজিক মূল্যায়ন থাকতে পারে। অনুবাদ সেগুলি অধ্যয়নের সুযোগ করে দেয়; সাইট সেগুলিকে প্রতিষ্ঠিত সত্য হিসেবে গ্রহণ করে না।</p></div>'''
 (ROOT/'assets/translation-links-bn.js').write_text('window.TRANSLATION_LINKS = '+json.dumps(scan_links,ensure_ascii=False)+';\n')
 return fragments,descriptors
