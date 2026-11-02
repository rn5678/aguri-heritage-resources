'use strict';
// Opt-in notifications. Nothing is registered, requested or stored until the
// reader presses the button. The block stays hidden where the browser or the
// server does not support notifications.
(()=>{
 const block=document.querySelector('[data-notify]');
 if(!block)return;
 const bengali=document.documentElement.lang==='bn';
 const button=block.querySelector('.notify-toggle'),statusLine=block.querySelector('.notify-status');
 const say=(en,bn)=>{statusLine.textContent=bengali?bn:en;};
 const secure=window.isSecureContext&&location.protocol!=='file:';
 const supported=secure&&'serviceWorker' in navigator&&'PushManager' in window&&'Notification' in window;
 const iosBrowser=/iPad|iPhone|iPod/.test(navigator.userAgent)||(navigator.platform==='MacIntel'&&navigator.maxTouchPoints>1);
 const standalone=window.matchMedia('(display-mode: standalone)').matches||navigator.standalone===true;
 if(!supported){
  // iPhone and iPad support web notifications only for sites added to the Home Screen.
  if(secure&&iosBrowser&&!standalone){
   block.hidden=false;button.hidden=true;
   say('On iPhone or iPad, add this site to your Home Screen (Share → Add to Home Screen), open it from there, and then turn on notifications.','আইফোন বা আইপ্যাডে আগে সাইটটি হোম স্ক্রিনে যোগ করুন (Share → Add to Home Screen), সেখান থেকে খুলে তারপর বিজ্ঞপ্তি চালু করুন।');
  }
  return;
 }
 const decode=value=>{const raw=atob(value.replace(/-/g,'+').replace(/_/g,'/')+'==='.slice((value.length+3)%4));return Uint8Array.from(raw,c=>c.charCodeAt(0));};
 const post=(path,body)=>fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',body:JSON.stringify(body)}).then(r=>{if(!r.ok)throw new Error(String(r.status));return r.json();});
 let config=null,subscription=null;
 const render=()=>{
  const on=!!subscription;
  button.textContent=on?button.dataset.off:button.dataset.on;
  button.setAttribute('aria-pressed',String(on));
 };
 const busy=value=>{button.disabled=value;if(value)button.setAttribute('aria-busy','true');else button.removeAttribute('aria-busy');};
 (async()=>{
  try{config=await (await fetch('/api/push/config',{credentials:'same-origin'})).json();}catch{return;}
  if(!config||!config.available||!config.public_key)return;
  // Only look for an existing registration; never register one on page load.
  const registration=await navigator.serviceWorker.getRegistration('/');
  subscription=registration?await registration.pushManager.getSubscription():null;
  block.hidden=false;render();
  if(Notification.permission==='denied')say('Notifications are blocked for this site in your browser settings. Allow them there if you change your mind.','ব্রাউজারের সেটিংসে এই সাইটের বিজ্ঞপ্তি বন্ধ করা আছে। মত বদলালে সেখান থেকে অনুমতি দিন।');
 })();
 button.addEventListener('click',async()=>{
  busy(true);statusLine.textContent='';
  try{
   if(subscription){
    const endpoint=subscription.endpoint;
    await subscription.unsubscribe();subscription=null;
    await post('/api/push/unsubscribe',{endpoint}).catch(()=>{});
    say('Notifications are off. You will not receive further messages on this device.','বিজ্ঞপ্তি বন্ধ হয়েছে। এই যন্ত্রে আর কোনও বার্তা আসবে না।');
   }else{
    // The permission prompt appears only here, after the reader's own action.
    const permission=await Notification.requestPermission();
    if(permission!=='granted'){say('Notifications were not turned on. Nothing has been saved.','বিজ্ঞপ্তি চালু হয়নি। কিছুই সংরক্ষিত হয়নি।');return;}
    const registration=await navigator.serviceWorker.register('/sw.js',{scope:'/'});
    await navigator.serviceWorker.ready;
    subscription=await registration.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:decode(config.public_key)});
    try{await post('/api/push/subscribe',{subscription:subscription.toJSON(),language:bengali?'bn':'en'});}
    catch(error){await subscription.unsubscribe().catch(()=>{});subscription=null;throw error;}
    say('Notifications are on. Use the same button to turn them off at any time.','বিজ্ঞপ্তি চালু হয়েছে। যে-কোনও সময় একই বোতাম দিয়ে বন্ধ করতে পারেন।');
   }
  }catch{
   say('Something went wrong, so notifications were not changed. Please try again later.','কিছু সমস্যা হয়েছে, তাই বিজ্ঞপ্তির অবস্থা বদলানো যায়নি। পরে আবার চেষ্টা করুন।');
  }finally{busy(false);render();}
 });
})();
