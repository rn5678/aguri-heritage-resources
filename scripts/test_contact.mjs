import test from 'node:test';
import assert from 'node:assert/strict';
import worker from '../contributions/worker.mjs';
import { LocalD1 } from '../contributions/local-db.mjs';
const ORIGIN = 'https://aguri-heritage.in';
const makeEnv = () => ({ CONTRIBUTIONS_DB: new LocalD1(), EDITOR_KEY: 'local-test-only-not-a-real-key-00000000',
  CONTACT_HOSTNAMES: 'aguri-heritage.in,aguri-heritage.pages.dev',
  CONTACT_TURNSTILE_SITE_KEY: 'fixture-public-site-key-not-live', CONTACT_TURNSTILE_SECRET_KEY: 'fixture-server-secret-not-live',
  CONTACT_DELIVERY_PROVIDER: 'resend', CONTACT_RESEND_API_KEY: 'fixture-mail-api-key-never-live',
  CONTACT_TO_EMAIL: 'owner@example.org', CONTACT_FROM_EMAIL: 'contact@example.org' });
const payload = (overrides={}) => ({ name: 'Test Reader', email: 'reader@example.org', subject: 'A heritage question',
  message: 'Local automated fixture, never sent.', language: 'en', website: '', consent: 'yes', token: 'fixture-token', request_id: crypto.randomUUID(), ...overrides });
async function call(env, data, options={}) {
 const { method='POST', origin=ORIGIN, path='/api/contact', raw, headers={} }=options;
 const request=new Request(ORIGIN+path, { method, headers:{...(origin?{Origin:origin}:{}), 'Content-Type':'application/json', ...headers}, ...(method==='GET'?{}:{body:raw??JSON.stringify(data)}) });
 const response=await worker.fetch(request,env);return { response, data:await response.json() };
}
function mockNetwork(t, { verify={success:true,hostname:'aguri-heritage.in',action:'contact'}, verifyStatus=200, mailStatus=200, mailBody={id:'fixture-mail-id'}, rejectVerify=false,rejectMail=false, malformedVerify=false }={}) {
 const calls=[];
 t.mock.method(globalThis,'fetch',async(url,init)=>{
  calls.push({url,init});
  // Cloudflare Workers supports follow/manual only. Reject redirects without forwarding secrets.
  assert.equal(init.redirect,'manual');
  if(url==='https://challenges.cloudflare.com/turnstile/v0/siteverify'){
   if(rejectVerify)throw new Error('fixture verification outage');
   return new Response(malformedVerify?'not-json':JSON.stringify(verify),{status:verifyStatus,headers:{'Content-Type':'application/json'}});
  }
  assert.equal(url,'https://api.resend.com/emails');
  if(rejectMail)throw new Error('fixture delivery timeout');
  return new Response(JSON.stringify(mailBody),{status:mailStatus,headers:{'Content-Type':'application/json'}});
 });return calls;
}
async function count(env){return (await env.CONTRIBUTIONS_DB.prepare('SELECT count(*) n FROM contact_requests').first()).n;}

test('contact is unavailable without every production binding, rejects dummy keys, and exposes no private config',async t=>{
 mockNetwork(t); const env=makeEnv();t.after(()=>env.CONTRIBUTIONS_DB.close());
 for(const key of ['CONTRIBUTIONS_DB','EDITOR_KEY','CONTACT_HOSTNAMES','CONTACT_TURNSTILE_SITE_KEY','CONTACT_TURNSTILE_SECRET_KEY','CONTACT_DELIVERY_PROVIDER','CONTACT_RESEND_API_KEY','CONTACT_TO_EMAIL','CONTACT_FROM_EMAIL']){
  const missing={...env,[key]:undefined};const config=await call(missing,null,{method:'GET',path:'/api/contact/config'});
  assert.deepEqual(config.data,{available:false},key);assert.equal((await call(missing,payload())).response.status,503,key);
 }
 for(const key of ['CONTACT_TURNSTILE_SITE_KEY','CONTACT_TURNSTILE_SECRET_KEY']){
  const config=await call({...env,[key]:'1x00000000000000000000AA'},null,{method:'GET',path:'/api/contact/config'});assert.equal(config.data.available,false);
 }
 for(const changes of [{CONTACT_HOSTNAMES:'evil.example'},{CONTACT_HOSTNAMES:'*.aguri-heritage.in'},{CONTACT_TO_EMAIL:'owner@example.org\nBcc: other@example.org'},{CONTACT_DELIVERY_PROVIDER:'other'}]){
  assert.equal((await call({...env,...changes},null,{method:'GET',path:'/api/contact/config'})).data.available,false);
 }
 const config=await call(env,null,{method:'GET',path:'/api/contact/config'});
 assert.deepEqual(config.data,{available:true,turnstile_site_key:env.CONTACT_TURNSTILE_SITE_KEY});
 assert.equal(JSON.stringify(config.data).includes(env.CONTACT_RESEND_API_KEY),false);
});

test('same-origin and bounded strict JSON validation happen before external side effects',async t=>{
 const calls=mockNetwork(t),env=makeEnv();t.after(()=>env.CONTRIBUTIONS_DB.close());
 for(const options of [{origin:null},{origin:'https://evil.example'},{headers:{'Sec-Fetch-Site':'cross-site'}}])assert.equal((await call(env,payload(),options)).response.status,403);
 assert.equal((await call(env,payload(),{headers:{'Content-Type':'text/plain'}})).response.status,415);
 assert.equal((await call(env,null,{raw:'{' })).response.status,400);
 assert.equal((await call(env,null,{raw:JSON.stringify({message:'x'.repeat(24_001)})})).response.status,413);
 assert.equal(calls.length,0);assert.equal(await count(env),0);
});

test('all contact fields, honeypot and consent are validated before CAPTCHA',async t=>{
 const calls=mockNetwork(t);
 const invalid=[{name:''},{name:'Name\nHeader'},{email:'bad'},{email:'name@example.org\nBcc: x@y.org'},{subject:'hello\r\nBcc: x@y.org'},{message:''},{message:'x'.repeat(5001)},{language:'fr'},{consent:'no'},{website:'https://spam.example'},{to:'other@example.org'},{request_id:'invalid'},{token:''},{token:'x'.repeat(2049)},{token:123}];
 for(const changes of invalid){const env=makeEnv();try{assert.equal((await call(env,payload(changes))).response.status,400,JSON.stringify(changes).slice(0,80));assert.equal(await count(env),0);}finally{env.CONTRIBUTIONS_DB.close();}}
 assert.equal(calls.length,0);
});

test('CAPTCHA must strictly pass hostname and contact action; upstream failures fail closed',async t=>{
 for(const verify of [{success:false},{success:'true',hostname:'aguri-heritage.in',action:'contact'},{success:true,hostname:'elsewhere.example',action:'contact'},{success:true,hostname:'aguri-heritage.in',action:'contribute'},{success:true,hostname:'aguri-heritage.in'},null]){
  const sub=t.mock.method(globalThis,'fetch',async()=>new Response(JSON.stringify(verify),{headers:{'Content-Type':'application/json'}}));
  const env=makeEnv();try{const r=await call(env,payload());assert.equal(r.response.status,400);assert.equal(r.data.error,'invalid_captcha');assert.equal(await count(env),0);assert.equal(sub.mock.callCount(),1);}finally{env.CONTRIBUTIONS_DB.close();sub.mock.restore();}
 }
 for(const fixture of [{verifyStatus:301},{verifyStatus:307},{verifyStatus:500},{rejectVerify:true},{malformedVerify:true}]){
  const calls=mockNetwork(t,fixture),env=makeEnv();try{const r=await call(env,payload());assert.equal(r.response.status,503);assert.equal(r.data.error,'captcha_unavailable');assert.equal(await count(env),0);assert.equal(calls.length,1);}finally{env.CONTRIBUTIONS_DB.close();t.mock.restoreAll();}
 }
});

test('valid English/Bengali contact sends only fixed-recipient plain text after server verification',async t=>{
 const calls=mockNetwork(t),env=makeEnv();t.after(()=>env.CONTRIBUTIONS_DB.close());
 const p=payload({name:'পাঠক',message:'<script>alert("fixture")</script>\nবাংলা প্রশ্ন',language:'bn'});
 const r=await call(env,p);assert.equal(r.response.status,201);assert.deepEqual(r.data,{received:true,reference:p.request_id});
 assert.equal(calls.length,2);assert.equal(calls[0].init.body.get('response'),p.token);assert.equal(calls[0].init.body.get('secret'),env.CONTACT_TURNSTILE_SECRET_KEY);
 const mail=JSON.parse(calls[1].init.body);assert.deepEqual(mail.to,[env.CONTACT_TO_EMAIL]);assert.equal(mail.reply_to,p.email);assert.equal(mail.from,`Aguri Heritage <${env.CONTACT_FROM_EMAIL}>`);assert.equal(mail.html,undefined);assert.match(mail.text,/<script>/);
 assert.equal(calls[1].init.headers['Idempotency-Key'],`aguri-contact/${p.request_id}`);
 assert.match(r.response.headers.get('Cache-Control'),/no-store/);assert.equal(r.response.headers.get('Access-Control-Allow-Origin'),null);
 const row=await env.CONTRIBUTIONS_DB.prepare('SELECT * FROM contact_requests').first();assert.equal(row.status,'sent');assert.equal(JSON.stringify(row).includes(p.email),false);assert.equal(JSON.stringify(row).includes(p.message),false);
});

test('sent retries are idempotent, changed content conflicts, and every retry verifies a fresh token',async t=>{
 const calls=mockNetwork(t),env=makeEnv();t.after(()=>env.CONTRIBUTIONS_DB.close());const p=payload();
 assert.equal((await call(env,p)).response.status,201);assert.equal((await call(env,{...p,token:'new-fixture-token'})).response.status,200);
 assert.equal((await call(env,{...p,message:'changed'})).response.status,409);assert.equal(await count(env),1);assert.equal(calls.filter(c=>c.url.includes('resend.com')).length,1);assert.equal(calls.filter(c=>c.url.includes('siteverify')).length,3);
});

test('delivery failure is never reported as success and preserves safe provider retry identity',async t=>{
 const calls=mockNetwork(t,{rejectMail:true}),env=makeEnv();t.after(()=>env.CONTRIBUTIONS_DB.close());const p=payload();
 let r=await call(env,p);assert.equal(r.response.status,503);assert.equal(r.data.error,'delivery_unavailable');assert.equal(r.data.received,undefined);
 r=await call(env,{...p,token:'retry-token'});assert.equal(r.response.status,503);
 const mails=calls.filter(c=>c.url.includes('resend.com'));assert.equal(mails.length,2);assert.equal(mails[0].init.headers['Idempotency-Key'],mails[1].init.headers['Idempotency-Key']);assert.equal(mails[0].init.body,mails[1].init.body);
 await env.CONTRIBUTIONS_DB.prepare("UPDATE contact_requests SET created_at=? WHERE request_id=?").bind(new Date(Date.now()-24*3600_000).toISOString(),p.request_id).run();
 assert.equal((await call(env,{...p,token:'fresh-token'})).response.status,409);assert.equal(calls.filter(c=>c.url.includes('resend.com')).length,2);
});

test('IP attempts are limited; absent table and unavailable database cannot report success',async t=>{
 const calls=mockNetwork(t),env=makeEnv();t.after(()=>env.CONTRIBUTIONS_DB.close());
 for(let i=0;i<10;i++)assert.equal((await call(env,payload({token:''}))).response.status,400);
 assert.equal((await call(env,payload())).response.status,429);assert.equal(calls.length,0);
 const missing=makeEnv();try{await missing.CONTRIBUTIONS_DB.exec('DROP TABLE contact_requests');const r=await call(missing,payload());assert.equal(r.response.status,503);assert.equal(r.data.received,undefined);assert.equal(calls.filter(c=>c.url.includes('resend.com')).length,0);}finally{missing.CONTRIBUTIONS_DB.close();}
});

test('malformed or unsuccessful mail responses never become success',async t=>{
 for(const fixture of [{mailStatus:301},{mailStatus:307},{mailStatus:500},{mailBody:{}},{mailBody:null}]){
  mockNetwork(t,fixture);const env=makeEnv();try{const r=await call(env,payload());assert.equal(r.response.status,503);assert.equal(r.data.received,undefined);assert.equal((await env.CONTRIBUTIONS_DB.prepare('SELECT status FROM contact_requests').first()).status,'pending');}finally{env.CONTRIBUTIONS_DB.close();t.mock.restoreAll();}
 }
});

test('a receipt-write failure after provider acceptance remains uncertain and retries with the same provider key',async t=>{
 const calls=mockNetwork(t),env=makeEnv();t.after(()=>env.CONTRIBUTIONS_DB.close());const p=payload();
 const original=env.CONTRIBUTIONS_DB.prepare;let failUpdate=true;
 env.CONTRIBUTIONS_DB.prepare=(sql)=>sql.startsWith('UPDATE contact_requests SET status')&&failUpdate?{bind(){return this;},async run(){return {success:false};}}:original(sql);
 let r=await call(env,p);assert.equal(r.response.status,503);assert.equal(r.data.received,undefined);
 failUpdate=false;r=await call(env,{...p,token:'fresh-token'});assert.equal(r.response.status,201);
 const mails=calls.filter(c=>c.url.includes('resend.com'));assert.equal(mails.length,2);assert.equal(mails[0].init.headers['Idempotency-Key'],mails[1].init.headers['Idempotency-Key']);assert.equal(mails[0].init.body,mails[1].init.body);
});

test('concurrent identical attempts keep one metadata row and the same provider deduplication key',async t=>{
 const calls=mockNetwork(t),env=makeEnv();t.after(()=>env.CONTRIBUTIONS_DB.close());const p=payload();
 const results=await Promise.all([call(env,p),call(env,{...p,token:'separate-token'})]);
 assert.ok(results.every(r=>[200,201].includes(r.response.status)));assert.equal(await count(env),1);
 assert.equal(new Set(calls.filter(c=>c.url.includes('resend.com')).map(c=>c.init.headers['Idempotency-Key'])).size,1);
});
