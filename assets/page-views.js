'use strict';
// A page total, not a visitor tracker. The only browser record is a timestamp
// for this canonical page in this tab's session; no identifier or cookie is set.
(()=>{
 const block=document.querySelector('[data-page-views]'),count=block?.querySelector('[data-view-count]');
 if(!block||!count||!['http:','https:'].includes(location.protocol))return;
 const page=block.dataset.pageViews;
 if(!/^\/(?:bn\/)?(?:[a-z0-9]+(?:-[a-z0-9]+)*)?$/.test(page))return;
 const storageKey='aguri:page-views:'+page,windowMs=30*60*1000;
 let started=false;
 async function load(){
  if(started||document.visibilityState!=='visible')return;
  started=true;document.removeEventListener('visibilitychange',load);
  if(navigator.onLine===false)return;
  const now=Date.now();let recent=false;
  try{
   const previous=Number(sessionStorage.getItem(storageKey));
   recent=Number.isFinite(previous)&&previous>0&&now>=previous&&now-previous<windowMs;
   // Save before sending: an interrupted response may already have incremented
   // the server. Reloading must not retry that ambiguous write.
   if(!recent)sessionStorage.setItem(storageKey,String(now));
  }catch{}
  const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),8000);
  try{
   const options={method:recent?'GET':'POST',credentials:'omit',referrerPolicy:'no-referrer',mode:'same-origin',redirect:'error',cache:'no-store',signal:controller.signal};
   if(!recent){options.headers={'Content-Type':'application/json'};options.body=JSON.stringify({page});}
   const response=await fetch('/api/page-views'+(recent?'?page='+encodeURIComponent(page):''),options);
   if(!response.ok)throw new Error('Page views unavailable');
   const data=await response.json();
   if(!data||data.page!==page||!Number.isSafeInteger(data.views)||data.views<0)throw new Error('Invalid page total');
   count.textContent=new Intl.NumberFormat(document.documentElement.lang==='bn'?'bn-IN':'en-IN').format(data.views);
   block.hidden=false;
  }catch{block.hidden=true;}
  finally{clearTimeout(timeout);}
 }
 document.addEventListener('visibilitychange',load);
 load();
})();
