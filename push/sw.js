'use strict';
// Aguri Heritage notification worker. It is registered only after a reader
// chooses to turn on notifications. It does not cache pages or intercept
// requests: it only shows messages and opens the linked page.
self.addEventListener('install',()=>self.skipWaiting());
self.addEventListener('activate',event=>event.waitUntil(self.clients.claim()));
self.addEventListener('push',event=>{
 let data={};
 try{data=event.data?event.data.json():{};}catch{data={};}
 const title=typeof data.title==='string'&&data.title?data.title.slice(0,80):'Aguri Heritage';
 const options={
  body:typeof data.body==='string'?data.body.slice(0,180):'',
  // The campaign tag stops a repeated delivery from appearing twice.
  tag:typeof data.tag==='string'?data.tag:'aguri-heritage',
  lang:data.lang==='bn'?'bn':'en',
  icon:'/assets/notification-icon.png',
  badge:'/assets/notification-badge.png',
  data:{url:typeof data.url==='string'?data.url:'/'}
 };
 event.waitUntil(self.registration.showNotification(title,options));
});
self.addEventListener('notificationclick',event=>{
 event.notification.close();
 // Only same-site pages may be opened from a notification.
 let target=new URL('/',self.location.origin);
 try{const url=new URL(event.notification.data?.url||'/',self.location.origin);if(url.origin===self.location.origin)target=url;}catch{}
 event.waitUntil((async()=>{
  const windows=await self.clients.matchAll({type:'window',includeUncontrolled:true});
  for(const client of windows){if(client.url===target.href&&'focus' in client)return client.focus();}
  return self.clients.openWindow(target.href);
 })());
});
// Browsers occasionally rotate a subscription. Re-register the new one with the
// same language; if that fails the reader can turn notifications on again.
self.addEventListener('pushsubscriptionchange',event=>{
 event.waitUntil((async()=>{
  try{
   const config=await (await fetch('/api/push/config',{credentials:'omit'})).json();
   if(!config.available)return;
   const raw=atob(config.public_key.replace(/-/g,'+').replace(/_/g,'/')+'==='.slice((config.public_key.length+3)%4));
   const subscription=event.newSubscription||await self.registration.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:Uint8Array.from(raw,c=>c.charCodeAt(0))});
   // The server copies the reader's language from the replaced subscription.
   await fetch('/api/push/subscribe',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({subscription,replaces:event.oldSubscription?.endpoint})});
  }catch{}
 })());
});
