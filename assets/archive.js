'use strict';
(()=>{
const $=s=>document.querySelector(s), volumes={1:175,2:167}, notes=window.READING_NOTES||{}, records=window.JOURNAL_OCR||[];
const translations=window.TRANSLATION_LINKS||{};
const bn=document.documentElement.lang==='bn',number=n=>new Intl.NumberFormat(bn?'bn-IN':'en-IN',{useGrouping:false}).format(n),word=(en,bengali)=>bn?bengali:en;
const volumeName=v=>bn?(v===1?'প্রথম খণ্ড':'দ্বিতীয় খণ্ড'):`Volume ${v===1?'I':'II'}`;
const byId=new Map(records.map(x=>[x.id,x]));let volume=1,scan=1;
const slug=(v,s)=>`v${v}-${String(s).padStart(3,'0')}`;
const clamp=(n,min,max)=>Number.isFinite(n)?Math.min(max,Math.max(min,Math.trunc(n))):min;
function readLocation(){const p=new URLSearchParams(location.search);volume=clamp(Number(p.get('volume')||1),1,2);scan=clamp(Number(p.get('scan')||1),1,volumes[volume]);render(false);}
function paragraph(parent,text,cls){const p=document.createElement('p');p.textContent=text;if(cls)p.className=cls;parent.append(p);return p;}
function render(update=true){
 const id=slug(volume,scan), img=`${document.body.dataset.assets||'assets/'}scans/${id}.jpg`,note=notes[id];
 $('#volume').value=String(volume);$('#scan-number').max=volumes[volume];$('#scan-number').value=scan;
 $('#scan-image').src=img;$('#scan-image').alt=`${volumeName(volume)} · ${word('scan','স্ক্যান')} ${number(scan)}${note?': '+note.title:''}`;$('#scan-image-link').href=img;$('#open-scan').href=img;
 $('#previous-scan').disabled=scan===1;$('#next-scan').disabled=scan===volumes[volume];
 $('#reader-status').textContent=bn?`${volumeName(volume)} · স্ক্যান ${number(scan)} / ${number(volumes[volume])}`:`Volume ${volume===1?'I':'II'} · scan ${scan} of ${volumes[volume]}`;
 const panel=$('#notes-panel');panel.replaceChildren();
 const translation=translations[id];
 if(translation){const box=document.createElement('div');box.className='reader-translation-link';paragraph(box,word("English translation available","ইংরেজি অনুবাদও রয়েছে"),'reading-label');const h=document.createElement('h3');h.textContent=translation.title;box.append(h);paragraph(box,translation.scope);const link=document.createElement('a');link.href=translation.url;link.textContent=word("Read the translation with its source pages →","বাংলা মূল পাতা ও ইংরেজি অনুবাদ দেখুন →");box.append(link);panel.append(box);}
 if(note){paragraph(panel,note.label,'reading-label');const h=document.createElement('h3');h.textContent=note.title;panel.append(h);paragraph(panel,note.location,'small');if(note.bn){const q=document.createElement('blockquote');q.lang='bn';q.textContent=note.bn;q.style.whiteSpace='pre-line';panel.append(q);if(note.translation)paragraph(panel,note.translation);}paragraph(panel,note.text);paragraph(panel,note.scope,'small');}
 else if(!translation){paragraph(panel,word("English note not yet prepared","মূল বাংলা স্ক্যান"),'reading-label');const h=document.createElement('h3');h.textContent=word("The original is here to read.","মূল পাতা পড়ুন।");panel.append(h);paragraph(panel,word("This scan has no reviewed English reading note yet. You can enlarge the original image or use the Bengali OCR tab to explore the machine transcription.","এই স্ক্যানের জন্য যাচাই করা পাঠ-টীকা নেই। মূল ছবি বড় করে পড়ুন অথবা বাংলা যন্ত্রপাঠের ট্যাবে অনুসন্ধানের সহায়ক প্রতিলিপি দেখুন।"));const link=document.createElement('a');link.href='translations.html';link.textContent=word("Explore the articles already translated into English →","নির্বাচিত পাঠ ও ইংরেজি অনুবাদ দেখুন →");panel.append(link);}
 else{paragraph(panel,word("This image may also contain a neighbouring article. The translation identifies the exact printed pages included. The Bengali OCR tab shows the uncorrected machine extraction for the whole scan.","এই ছবিতে পাশের প্রবন্ধের অংশও থাকতে পারে। অনুবাদে অন্তর্ভুক্ত মুদ্রিত পাতাগুলি নির্দিষ্ট করা হয়েছে। বাংলা যন্ত্রপাঠের ট্যাবে গোটা স্ক্যানের অযাচাইকৃত প্রতিলিপি রয়েছে।"),'small');}
 const record=byId.get(id);$('#ocr-text').textContent=record?record.leaves.map(l=>`[${l.side==='left'?word("বাম পৃষ্ঠা / Left leaf","বাম পাতা"):word("ডান পৃষ্ঠা / Right leaf","ডান পাতা")}]\n${l.text||word("[No text recognised on this leaf]","[এই পাতায় লেখা শনাক্ত হয়নি]")}`).join('\n\n'):word("OCR is unavailable for this scan. Please consult the original PDF.","এই স্ক্যানের যন্ত্রপাঠ নেই। মূল PDF দেখুন।");
 if(update){const u=new URL(location.href);u.searchParams.set('volume',volume);u.searchParams.set('scan',scan);u.hash='reader';try{history.replaceState(null,'',u);}catch{} }
}
$('#volume').addEventListener('change',()=>{volume=Number($('#volume').value);scan=1;render();});
function go(){scan=clamp(Number($('#scan-number').value),1,volumes[volume]);render();}
$('#go-scan').addEventListener('click',go);$('#scan-number').addEventListener('keydown',e=>{if(e.key==='Enter')go();});
$('#previous-scan').addEventListener('click',()=>{scan=Math.max(1,scan-1);render();});$('#next-scan').addEventListener('click',()=>{scan=Math.min(volumes[volume],scan+1);render();});
const tabs=[$('#notes-tab'),$('#ocr-tab')];function selectTab(i){tabs.forEach((t,n)=>{t.setAttribute('aria-selected',String(n===i));t.tabIndex=n===i?0:-1;$('#'+t.getAttribute('aria-controls')).hidden=n!==i;});}
tabs.forEach((t,i)=>{t.addEventListener('click',()=>selectTab(i));t.addEventListener('keydown',e=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(e.key)){e.preventDefault();const n=e.key==='Home'?0:e.key==='End'?1:1-i;selectTab(n);tabs[n].focus();}});});
$('#journal-search-form').addEventListener('submit',e=>{e.preventDefault();const q=$('#journal-query').value.trim().normalize('NFC').toLocaleLowerCase();const out=$('#journal-results');out.replaceChildren();if(!q){$('#journal-search-status').textContent=word("Enter a Bengali word or an English topic.","একটি বাংলা শব্দ বা বিষয় লিখুন।");return;}const hits=[];
 for(let v=1;v<=2;v++)for(let s=1;s<=volumes[v];s++){const id=slug(v,s),n=notes[id],r=byId.get(id);const nt=n?Object.values(n).join(' '):'';const rt=r?r.leaves.map(l=>l.text).join(' '):'';const text=(nt+' '+rt).normalize('NFC');const p=text.toLocaleLowerCase().indexOf(q);if(p>=0)hits.push({v,s,n,excerpt:text.slice(Math.max(0,p-40),p+150)});}
 $('#journal-search-status').textContent=hits.length?(bn?`${number(hits.length)}টি স্ক্যান মিলেছে${hits.length>40?' · প্রথম ৪০টি দেখানো হচ্ছে; ফল কমাতে আরও নির্দিষ্ট শব্দ লিখুন':''}। যন্ত্রপাঠের ফল ছবির সঙ্গে মিলিয়ে নিন।`:`${hits.length} matching scans${hits.length>40?' · showing the first 40; use a more specific phrase to narrow results':''}. OCR matches need checking against the image.`):word("No matches found. Try a shorter phrase or another spelling; OCR may have missed the word.","কিছু মেলেনি। ছোট বাক্যাংশ বা অন্য বানান চেষ্টা করুন; যন্ত্রপাঠে শব্দটি বাদ পড়ে থাকতে পারে।");
 for(const h of hits.slice(0,40)){const b=document.createElement('button');b.type='button';b.className='journal-result';b.textContent=`${volumeName(h.v)} · ${word('scan','স্ক্যান')} ${number(h.s)}${h.n?' · '+h.n.title:''}`;const excerpt=document.createElement('span');excerpt.textContent=h.excerpt+'…';b.append(excerpt);b.addEventListener('click',()=>{volume=h.v;scan=h.s;render();selectTab(h.n?0:1);$('#reader').scrollIntoView({block:'start'});$('#scan-number').focus({preventScroll:true});});out.append(b);}
});
window.addEventListener('popstate',readLocation);readLocation();
})();
