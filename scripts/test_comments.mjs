import test from 'node:test';
import assert from 'node:assert/strict';
import worker from '../contributions/worker.mjs';
import { readFileSync } from 'node:fs';
import { LocalD1 } from '../contributions/local-db.mjs';
const origin = 'https://aguri-heritage.in';
const terms = 'comments-2026-11-09';
const keys = await crypto.subtle.generateKey({name:'RSASSA-PKCS1-v1_5',modulusLength:2048,publicExponent:new Uint8Array([1,0,1]),hash:'SHA-256'},true,['sign','verify']);
const jwk = {...await crypto.subtle.exportKey('jwk',keys.publicKey),kid:'test-key',alg:'RS256',use:'sig'};
function env() { return {COMMENTS_ENABLED:'true',GOOGLE_CLIENT_ID:'test.apps.googleusercontent.com',COMMENTS_SESSION_SECRET:'independent-comment-session-secret-12345',EDITOR_KEY:'existing-editor-secret-123456789012345',CONTRIBUTIONS_DB:new LocalD1(),ASSETS:{fetch:async req=>new Response(`<html><body data-page="${new URL(req.url).pathname.replace(/^\//,'').replace(/\.html$/,'')}"></body></html>`,{headers:{'Content-Type':'text/html'}})}}; }
async function call(e,path,method='GET',body,headers={}) {
 const response=await worker.fetch(new Request(origin+'/api/comments'+path,{method,headers:{Origin:origin,'Content-Type':'application/json',...headers},...(body===undefined?{}:{body:JSON.stringify(body)})}),e);
 return {response,data:await response.json()};
}
const b64=value=>Buffer.from(typeof value==='string'?value:JSON.stringify(value)).toString('base64url');
async function credential(e,nonce,overrides={},header={alg:'RS256',kid:'test-key'}) {
 const now=Math.floor(Date.now()/1000), claims={iss:'https://accounts.google.com',aud:e.GOOGLE_CLIENT_ID,sub:'123456',iat:now,exp:now+3600,nonce,name:'Reader <img onerror=x>',email:'never-store@example.org',...overrides};
 const input=b64(header)+'.'+b64(claims);
 return input+'.'+Buffer.from(await crypto.subtle.sign('RSASSA-PKCS1-v1_5',keys.privateKey,new TextEncoder().encode(input))).toString('base64url');
}
async function login(e,sub='123456') {
 const start=await call(e,'/auth/nonce'); const nonce=start.data.nonce;
 const result=await call(e,'/auth/google','POST',{nonce,credential:await credential(e,nonce,{sub})},{Cookie:start.response.headers.get('Set-Cookie').split(';')[0]});
 assert.equal(result.response.status,200,JSON.stringify(result.data));
 return {Cookie:result.response.headers.get('Set-Cookie').split(';')[0],'X-CSRF-Token':result.data.csrf_token};
}
function mockKeys(t) { t.mock.method(globalThis,'fetch',async url=>{assert.equal(url,'https://www.googleapis.com/oauth2/v3/certs');return Response.json({keys:[jwk]},{headers:{'Cache-Control':'max-age=3600'}});}); }
const post=(body='A reader comment')=>({page:'history',body,client_id:crypto.randomUUID(),consent:true,terms_version:terms});
test('comments fail closed and do not expose secrets',async t=>{
 const e=env();t.after(()=>e.CONTRIBUTIONS_DB.close());
 for(const key of ['COMMENTS_ENABLED','GOOGLE_CLIENT_ID','COMMENTS_SESSION_SECRET','EDITOR_KEY','CONTRIBUTIONS_DB','ASSETS']) {
  const missing={...e,[key]:undefined};assert.equal((await call(missing,'/config')).data.available,false);assert.equal((await call(missing,'?page=history')).response.status,503);
 }
 assert.equal((await call({...e,COMMENTS_SESSION_SECRET:e.EDITOR_KEY},'/config')).data.available,false);
 const config=await call(e,'/config');assert.equal(config.data.terms_version,terms);assert.equal(JSON.stringify(config.data).includes(e.COMMENTS_SESSION_SECRET),false);
});
test('Google claims, signature, nonce, login replay, session flags and logout',async t=>{
 mockKeys(t);const e=env();t.after(()=>e.CONTRIBUTIONS_DB.close());
 const start=await call(e,'/auth/nonce'), nonce=start.data.nonce, Cookie=start.response.headers.get('Set-Cookie').split(';')[0];
 for(const override of [{aud:'evil'},{iss:'https://evil.test'},{exp:1},{iat:1},{sub:''},{nonce:'wrong'},{azp:'wrong'},{nbf:9999999999}]) {
  assert.equal((await call(e,'/auth/google','POST',{nonce,credential:await credential(e,nonce,override)},{Cookie})).response.status,401);
 }
 const signed=await credential(e,nonce);
 assert.equal((await call(e,'/auth/google','POST',{nonce,credential:signed.slice(0,-20)+'a'.repeat(20)},{Cookie})).response.status,401);
 assert.equal((await call(e,'/auth/google','POST',{nonce,credential:await credential(e,nonce,{}, {alg:'none',kid:'test-key'})},{Cookie})).response.status,401);
 assert.equal((await call(e,'/auth/google','POST',{nonce,credential:signed},{Cookie:'wrong=1'})).response.status,401);
 const good=await call(e,'/auth/google','POST',{nonce,credential:signed},{Cookie});assert.equal(good.response.status,200);
 assert.match(good.response.headers.get('Set-Cookie'),/HttpOnly; Secure; SameSite=Strict/);
 assert.equal((await call(e,'/auth/google','POST',{nonce,credential:signed},{Cookie})).response.status,401);
 const auth={Cookie:good.response.headers.get('Set-Cookie').split(';')[0],'X-CSRF-Token':good.data.csrf_token};
 assert.equal((await call(e,'/me','GET',undefined,auth)).data.user.name,'Reader <img onerror=x>');
 assert.equal((await call(e,'/auth/logout','POST',{},auth)).response.status,200);
 assert.equal((await call(e,'/me','GET',undefined,auth)).data.user,null);
});
test('premoderation, plain text, consent, CSRF, ownership, idempotency, reports and deletion',async t=>{
 mockKeys(t);const e=env();t.after(()=>e.CONTRIBUTIONS_DB.close());const auth=await login(e), other=await login(e,'other');
 assert.equal((await call(e,'','POST',post())).response.status,401);
 assert.equal((await call(e,'','POST',post(),{...auth,'X-CSRF-Token':''})).response.status,403);
 assert.equal((await call(e,'','POST',post(),{...auth,Origin:'https://evil.test'})).response.status,403);
 assert.equal((await call(e,'','POST',{...post(),consent:false},auth)).response.status,400);
 assert.equal((await call(e,'','POST',{...post(),terms_version:'old'},auth)).response.status,400);
 const payload=post('<script>alert("x")</script> & plain text'), created=await call(e,'','POST',payload,auth);
 assert.equal(created.response.status,201);assert.equal(created.data.status,'pending');
 assert.deepEqual((await call(e,'?page=history')).data.comments,[]);
 assert.equal((await call(e,'/mine?page=history','GET',undefined,auth)).data.comments[0].body,payload.body);
 assert.equal((await call(e,'','POST',payload,auth)).data.id,created.data.id);
 assert.equal((await call(e,'','POST',{...payload,body:'changed'},auth)).response.status,409);
 assert.equal((await call(e,'/'+created.data.id,'DELETE',undefined,other)).response.status,404);
 assert.equal((await call(e,'/review')).response.status,401);
 const editor={Authorization:'Bearer '+e.EDITOR_KEY};
 assert.equal((await call(e,'/review/'+created.data.id,'PATCH',{status:'approved',note:'Checked',version:1},editor)).response.status,200);
 assert.equal((await call(e,'/review/'+created.data.id,'PATCH',{status:'rejected',version:1},editor)).response.status,409);
 const visible=await call(e,'?page=history');assert.equal(visible.data.comments[0].body,payload.body);assert.match(visible.response.headers.get('Content-Type'),/application\/json/);
 assert.equal(JSON.stringify(visible.data).includes('email'),false);assert.equal(Object.hasOwn(visible.data.comments[0],'user_id'),false);
 assert.equal((await call(e,'/'+created.data.id+'/report','POST',{reason:'Please review'},other)).response.status,200);
 const review=(await call(e,'/review?status=approved','GET',undefined,editor)).data.comments[0];assert.equal(review.report_count,1);assert.equal(review.reports[0].reason,'Please review');
 assert.equal((await call(e,'/review/'+created.data.id,'PATCH',{status:'hidden',version:2},editor)).response.status,200);
 assert.equal((await call(e,'?page=history')).data.comments.length,0);
 assert.equal((await call(e,'/'+created.data.id,'DELETE',undefined,auth)).response.status,200);
 const deleted=await e.CONTRIBUTIONS_DB.prepare('SELECT * FROM comments WHERE id=?').bind(created.data.id).first();assert.equal(deleted.body,'');assert.equal(deleted.name,'');
 assert.equal((await call(e,'/review/'+created.data.id,'PATCH',{status:'approved',version:3},editor)).response.status,409);
 assert.equal((await e.CONTRIBUTIONS_DB.prepare('SELECT count(*) n FROM comment_moderation_history').first()).n,3);
});
test('page identity, body limits, rate limits, pagination and expired sessions',async t=>{
 mockKeys(t);const e=env();t.after(()=>e.CONTRIBUTIONS_DB.close());const auth=await login(e);
 for(const page of ['contact','contribute','review','404','../history','bn/history','https://evil.test']) assert.equal((await call(e,'?page='+encodeURIComponent(page))).response.status,400);
 assert.equal((await call({...e,ASSETS:{fetch:async()=>new Response('<body data-page="404">',{headers:{'Content-Type':'text/html'}})}},'?page=nonexistent')).response.status,404);
 assert.equal((await call(e,'','POST',post('x'.repeat(2001)),auth)).response.status,400);
 assert.equal((await call(e,'','POST',post('x'.repeat(13000)),auth)).response.status,413);
 for(let i=0;i<5;i++) assert.equal((await call(e,'','POST',post('Entry '+i),auth)).response.status,201);
 assert.equal((await call(e,'','POST',post(),auth)).response.status,429);
 const base=await e.CONTRIBUTIONS_DB.prepare('SELECT * FROM comments LIMIT 1').first();
 for(let i=0;i<26;i++) await e.CONTRIBUTIONS_DB.prepare(`INSERT INTO comments(id,user_id,client_id,payload_hash,page,name,body,status,terms_version,consented_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?,'approved',?,?,?,?)`).bind(crypto.randomUUID(),base.user_id,crypto.randomUUID(),'hash','history','Reader','Approved '+i,terms,base.consented_at,base.created_at,base.updated_at).run();
 const first=await call(e,'?page=history');assert.equal(first.data.comments.length,20);assert.ok(first.data.next_cursor);
 const second=await call(e,'?page=history&cursor='+first.data.next_cursor);assert.equal(second.data.comments.length,6);assert.equal(new Set([...first.data.comments,...second.data.comments].map(x=>x.id)).size,26);
 assert.equal((await call(e,'?page=history&cursor=bad')).response.status,400);
 await e.CONTRIBUTIONS_DB.prepare('UPDATE comment_sessions SET expires_at=0').run();assert.equal((await call(e,'/me','GET',undefined,auth)).data.user,null);
});

test('rotating session secret invalidates sessions but preserves author ownership',async t=>{
 mockKeys(t);const e=env();t.after(()=>e.CONTRIBUTIONS_DB.close());const auth=await login(e);
 const created=await call(e,'','POST',post(),auth);
 const rotated={...e,COMMENTS_SESSION_SECRET:'new-independent-session-secret-1234567890'};
 assert.equal((await call(rotated,'/me','GET',undefined,auth)).data.user,null);
 const fresh=await login(rotated);
 assert.equal((await call(rotated,'/'+created.data.id,'DELETE',undefined,fresh)).response.status,200);
});

test('migration is additive and repeatable, page redirects and JWKS unknown kids fail closed',async t=>{
 const e=env();t.after(()=>e.CONTRIBUTIONS_DB.close());
 const migration=readFileSync(new URL('../contributions/migrations/2026-11-09-comments.sql',import.meta.url),'utf8');
 e.CONTRIBUTIONS_DB.exec(migration);e.CONTRIBUTIONS_DB.exec(migration);
 const tables=(await e.CONTRIBUTIONS_DB.prepare("SELECT name FROM sqlite_master WHERE type='table'").all()).results.map(r=>r.name);
 assert.ok(tables.includes('contributions'));assert.ok(tables.includes('comments'));
 const foreign={...e,ASSETS:{fetch:async()=>new Response(null,{status:302,headers:{Location:'https://evil.test/history'}})}};
 assert.equal((await call(foreign,'?page=history')).response.status,404);
 mockKeys(t);await login(e);
 let requests=0;t.mock.method(globalThis,'fetch',async()=>{requests++;throw new Error('Should use cached keys');});
 const start=await call(e,'/auth/nonce'),nonce=start.data.nonce,Cookie=start.response.headers.get('Set-Cookie').split(';')[0];
 const bad=await credential(e,nonce,{}, {alg:'RS256',kid:'unrecognized-key'});
 for(let i=0;i<3;i++) assert.equal((await call(e,'/auth/google','POST',{nonce,credential:bad},{Cookie})).response.status,401);
 assert.equal(requests,0,'unknown key does not trigger repeated refreshes inside cooldown');
});

test('same-status moderation note edits are audited',async t=>{
 mockKeys(t);const e=env();t.after(()=>e.CONTRIBUTIONS_DB.close());const auth=await login(e);
 const created=await call(e,'','POST',post(),auth), editor={Authorization:'Bearer '+e.EDITOR_KEY};
 assert.equal((await call(e,'/review/'+created.data.id,'PATCH',{status:'approved',note:'First review',version:1},editor)).response.status,200);
 assert.equal((await call(e,'/review/'+created.data.id,'PATCH',{status:'approved',note:'Clarified review',version:2},editor)).response.status,200);
 const history=(await e.CONTRIBUTIONS_DB.prepare('SELECT previous_status,status,note FROM comment_moderation_history WHERE comment_id=? ORDER BY rowid').bind(created.data.id).all()).results;
 assert.equal(history.length,2);assert.equal(history[0].note,'First review');assert.equal(history[1].note,'Clarified review');
 assert.equal(history[1].previous_status,'approved');assert.equal(history[1].status,'approved');
});
