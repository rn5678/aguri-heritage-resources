'use strict';
document.documentElement.classList.add('js');
const bengali=document.documentElement.lang==='bn';
const localNumber=n=>new Intl.NumberFormat(bengali?'bn-IN':'en-IN',{useGrouping:false}).format(n);
const picker=document.querySelector('#language-picker');
// One host-only preference, written only after an explicit language choice.
// A blocked cookie must not prevent switching or cause an English/home loop.
function rememberLanguage(language){
 if(location.protocol!=='https:'&&location.protocol!=='http:')return;
 try{document.cookie=`aguri_language=${language}; Max-Age=31536000; Path=/; SameSite=Lax${location.protocol==='https:'?'; Secure':''}`;}catch{}
}
function languageDestination(route,language){
 const destination=new URL(route,location.href);
 destination.search=location.search;destination.hash=location.hash;
 // The explicit marker survives Pages' index.html canonical redirect and
 // lets English work in West Bengal even with cookies or JavaScript blocked.
 if(/^\/(?:bn\/)?(?:index\.html)?$/.test(destination.pathname))destination.searchParams.set('lang',language);
 return destination;
}
picker?.addEventListener('change',()=>{
 const language=picker.selectedIndex===1?'bn':'en';
 const destination=languageDestination(picker.value,language);
 rememberLanguage(language);
 location.assign(destination.href);
});
// An explicit homepage link opened in a new tab also records its choice.
const explicitLanguage=new URL(location.href).searchParams.get('lang');
if(/^\/(?:bn\/)?(?:index\.html)?$/.test(location.pathname)&&explicitLanguage===(bengali?'bn':'en'))rememberLanguage(explicitLanguage);
// Home and History use visible language links instead of the article picker.
document.querySelectorAll('[data-language-switch]').forEach(link=>{
 const route=link.getAttribute('href'),language=link.lang;
 const update=()=>{link.href=languageDestination(route,language).href;};
 update();link.addEventListener('click',()=>{update();rememberLanguage(language);});
 link.addEventListener('contextmenu',update);
 window.addEventListener('hashchange',update);window.addEventListener('popstate',update);
});
// Back/forward restores native form controls; keep the selector consistent with the URL.
window.addEventListener('pageshow',()=>{if(picker)picker.selectedIndex=bengali?1:0;});
// Resolve at click time so a correction retains the reader's current volume,
// scan and section, including changes made without loading another page.
document.querySelectorAll('[data-correction]').forEach(link=>{
 const update=()=>{
  const destination=new URL('contribute.html',location.href);
  const path=location.protocol==='file:'
   ? (bengali?'/bn/':'/')+(location.pathname.split('/').pop()||'index.html')
   : location.pathname;
  destination.searchParams.set('type','correction');
  destination.searchParams.set('page',path+location.search+location.hash);
  destination.searchParams.set('title',document.querySelector('h1')?.textContent.trim()||document.title);
  for(const key of ['volume','scan']){
   const value=new URLSearchParams(location.search).get(key);
   if(value)destination.searchParams.set(key,value);
  }
  link.href=destination.href;
 };
 update();link.addEventListener('click',update);link.addEventListener('contextmenu',update);
 window.addEventListener('hashchange',update);window.addEventListener('popstate',update);
});
const menu=document.querySelector('.menu-toggle'), navigation=document.querySelector('.main-nav');
menu?.addEventListener('click',()=>{const open=menu.getAttribute('aria-expanded')!=='true';menu.setAttribute('aria-expanded',String(open));navigation.classList.toggle('is-open',open);});
const dialog=document.querySelector('#search-dialog'), search=document.querySelector('#site-search'),results=document.querySelector('#search-results'), status=document.querySelector('#search-status');
let opener;
document.querySelector('.search-open')?.addEventListener('click',event=>{opener=event.currentTarget;dialog.showModal();search.focus();});
document.querySelector('.search-close')?.addEventListener('click',()=>dialog.close());
dialog?.addEventListener('click',e=>{if(e.target===dialog){const r=dialog.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)dialog.close();}});
dialog?.addEventListener('keydown',e=>{if(e.key==='Escape'){e.preventDefault();dialog.close();}});
dialog?.addEventListener('close',()=>opener?.focus());
search?.addEventListener('input',()=>{
 const q=search.value.trim().normalize('NFC').toLocaleLowerCase();results.replaceChildren();
 if(!q){status.textContent=bengali?'শুরু করতে একটি শব্দ বা বাক্যাংশ লিখুন।':'Enter a word or phrase to begin.';return;}
 const hits=(window.SITE_SEARCH||[]).filter(r=>(r.title+' '+r.text).normalize('NFC').toLocaleLowerCase().includes(q));
 status.textContent=hits.length?(bengali?`${localNumber(hits.length)}টি পাতা পাওয়া গেছে।`:`${hits.length} ${hits.length===1?'page':'pages'} found.`):(bengali?'কোনও পাতা মেলেনি। অন্য বানান বা ছোট বাক্যাংশ দিয়ে খুঁজুন।':'No matching pages. Try another spelling or a shorter phrase.');
 for(const r of hits){const link=document.createElement('a');link.className='search-result';link.href=new URL(r.url,document.body.dataset.searchRoot||location.href).href;const title=document.createElement('strong');title.textContent=r.title;const excerpt=document.createElement('span');const pos=r.text.toLocaleLowerCase().indexOf(q);const start=Math.max(0,pos-60);excerpt.textContent=(start?'…':'')+r.text.slice(start,start+210)+'…';link.append(title,excerpt);results.append(link);}
});
const filters=[...document.querySelectorAll('[data-source-filter]')];
filters.forEach(b=>b.addEventListener('click',()=>{filters.forEach(x=>x.setAttribute('aria-pressed',String(x===b)));let count=0;document.querySelectorAll('.source-entry').forEach(e=>{e.hidden=b.dataset.sourceFilter!=='all'&&e.dataset.kind!==b.dataset.sourceFilter;if(!e.hidden)count++;});document.querySelector('#source-count').textContent=bengali?`${localNumber(count)}টি উৎস`:`${count} ${count===1?'source':'sources'}`;}));
// Reveal a linked note before scrolling, including direct URLs and a repeated
// click on the current fragment after the reader has closed the notes again.
// Fragment IDs are data, not selectors: malformed or unusual hashes are safe.
function revealReference(hash){
 if(!hash||hash==='#')return;
 let id;
 try{id=decodeURIComponent(hash.slice(1));}catch{return;}
 const target=document.getElementById(id);
 if(!target)return;
 const notes=target.closest('details.notes'),source=target.closest('.source-entry');
 if(!notes&&!source)return;
 if(notes)notes.open=true;
 if(source)document.querySelector('[data-source-filter="all"]')?.click();
 requestAnimationFrame(()=>{if(target.isConnected)target.scrollIntoView({block:'start'});});
}
window.addEventListener('hashchange',()=>revealReference(location.hash));
window.addEventListener('pageshow',event=>{if(event.persisted)revealReference(location.hash);});
document.addEventListener('click',event=>{
 if(event.defaultPrevented||event.button!==0||event.metaKey||event.ctrlKey||event.shiftKey||event.altKey)return;
 const link=event.target instanceof Element?event.target.closest('a[href]'):null;
 if(!link||link.hasAttribute('download')||(link.target&&link.target!=='_self'))return;
 let destination;
 try{destination=new URL(link.href,location.href);}catch{return;}
 if(destination.origin===location.origin&&destination.pathname===location.pathname&&destination.search===location.search){
  revealReference(destination.hash);
 }
});
revealReference(location.hash);

// The citation remains readable and selectable without JavaScript. Enhance it
// with a copy action while retaining its published address during local previews.
const citation=document.querySelector('.page-citation');
if(citation){
 const copy=citation.querySelector('.citation-copy'),text=citation.querySelector('.citation-text'),statusLine=citation.querySelector('.citation-status'),link=citation.querySelector('.citation-url');
 const canonical=link?.href;
 const updateCitation=()=>{
  if(!canonical||document.body.dataset.page!=='archives')return;
  const url=new URL(canonical),params=new URLSearchParams(location.search);
  for(const key of ['volume','scan']){
   const value=params.get(key);
   if(value&&/^\d+$/.test(value))url.searchParams.set(key,value);
  }
  link.href=url.href;link.textContent=url.href;
 };
 updateCitation();
 citation.addEventListener('toggle',updateCitation);
 window.addEventListener('popstate',updateCitation);
 // Reader navigation replaces history without emitting popstate. Its status
 // changes after every scan; observe that so manual copying stays current too.
 const readerStatus=document.querySelector('#reader-status');
 if(readerStatus)new MutationObserver(updateCitation).observe(readerStatus,{childList:true,subtree:true,characterData:true});
 if(copy&&text&&statusLine){
  copy.hidden=false;
  copy.addEventListener('click',async()=>{
   if(copy.disabled)return;
   updateCitation();
   const value=text.textContent.trim().replace(/\s+/g,' ');
   let copied=false,usedFallback=false;
   statusLine.textContent='';copy.disabled=true;copy.setAttribute('aria-busy','true');
   try{
    if(navigator.clipboard&&window.isSecureContext){
     try{await navigator.clipboard.writeText(value);copied=true;}catch{}
    }
    if(!copied){
     usedFallback=true;
     const field=document.createElement('textarea');field.value=value;field.setAttribute('readonly','');field.tabIndex=-1;
     field.style.cssText='position:fixed;top:0;left:0;width:1px;height:1px;padding:0;border:0;opacity:0;font-size:16px;';
     document.body.append(field);
     try{field.select();field.setSelectionRange(0,value.length);copied=document.execCommand('copy');}
     finally{field.remove();}
    }
   }catch{copied=false;}
   finally{
    copy.disabled=false;copy.removeAttribute('aria-busy');
    if(usedFallback)copy.focus({preventScroll:true});
   }
   statusLine.textContent=copied
    ?(bengali?'উদ্ধৃতির তথ্য কপি হয়েছে।':'Citation copied.')
    :(bengali?'স্বয়ংক্রিয়ভাবে কপি করা যায়নি। উপরের উদ্ধৃতির লেখাটি বেছে নিয়ে কপি করুন।':'Could not copy automatically. Select the citation text above and copy it.');
  });
 }
}

// Keep explanatory notes in the PDF, then restore the reader's screen state.
// These events also cover the browser's own Print command.
let printDetails=null;
function preparePagePrint(){
 if(printDetails!==null)return;
 printDetails=[...document.querySelectorAll('details.origins-timeline-text, details.translation-notes, details.notes')].map(element=>({element,open:element.open}));
 printDetails.forEach(({element})=>{element.open=true;});
}
function restorePagePrint(){
 if(printDetails===null)return;
 printDetails.forEach(({element,open})=>{element.open=open;});
 printDetails=null;
}
window.addEventListener('beforeprint',preparePagePrint);
window.addEventListener('afterprint',restorePagePrint);
window.matchMedia('print').addEventListener('change',event=>event.matches?preparePagePrint():restorePagePrint());
// Sharing: native share sheet where the device offers one, otherwise a small
// panel of plain links. No third-party script loads and no tracking parameter
// is added; a service is contacted only if the reader chooses it.
const share=document.querySelector('.share');
if(share){
 const toggle=share.querySelector('.share-toggle'),panel=share.querySelector('.share-panel'),statusLine=share.querySelector('.share-status');
 const shareUrl=()=>{
  // The canonical address identifies the article; the journal reader also
  // keeps its volume and scan so a shared link opens the same page.
  const url=new URL(share.dataset.shareUrl);
  if(document.body.dataset.page==='archives')url.search=location.search;
  return url.href;
 };
 const announce=message=>{statusLine.textContent=message;};
 const close=(restoreFocus)=>{panel.hidden=true;toggle.setAttribute('aria-expanded','false');if(restoreFocus)toggle.focus();};
 const open=()=>{panel.hidden=false;toggle.setAttribute('aria-expanded','true');announce('');panel.querySelector('.share-link')?.focus();};
 panel.hidden=true;toggle.hidden=false;
 toggle.addEventListener('click',async()=>{
  if(toggle.getAttribute('aria-expanded')==='true'){close(true);return;}
  const data={title:share.dataset.shareTitle,text:share.dataset.shareText,url:shareUrl()};
  if(navigator.share&&(!navigator.canShare||navigator.canShare(data))){
   try{await navigator.share(data);return;}
   catch(error){if(error&&error.name==='AbortError')return;}
  }
  open();
 });
 panel.addEventListener('keydown',event=>{if(event.key==='Escape'){event.preventDefault();close(true);}});
 document.addEventListener('click',event=>{if(!panel.hidden&&!share.contains(event.target))close(false);});
 // Keep the archive reader's current scan in the WhatsApp, Facebook and email links.
 panel.querySelectorAll('a.share-link').forEach(link=>link.addEventListener('click',()=>{
  if(document.body.dataset.page!=='archives')return;
  const url=shareUrl(),title=share.dataset.shareTitle;
  if(link.dataset.share==='whatsapp')link.href='https://wa.me/?text='+encodeURIComponent(`${title} — ${url}`);
  if(link.dataset.share==='facebook')link.href='https://www.facebook.com/sharer/sharer.php?u='+encodeURIComponent(url);
  if(link.dataset.share==='email')link.href='mailto:?subject='+encodeURIComponent(title)+'&body='+encodeURIComponent(share.dataset.shareText+'\n\n'+url);
 }));
 panel.querySelector('[data-share="copy"]')?.addEventListener('click',async()=>{
  const url=shareUrl();
  try{
   if(navigator.clipboard&&window.isSecureContext)await navigator.clipboard.writeText(url);
   else{
    const field=document.createElement('textarea');field.value=url;field.setAttribute('readonly','');
    field.style.position='fixed';field.style.opacity='0';document.body.append(field);field.select();
    const copied=document.execCommand('copy');field.remove();
    if(!copied)throw new Error('copy failed');
   }
   announce(share.dataset.copied);
  }catch{announce(`${share.dataset.copyPrompt} ${url}`);}
 });
}
