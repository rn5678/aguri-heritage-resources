import test from 'node:test';
import assert from 'node:assert/strict';
import worker from '../contributions/worker.mjs';
import { createLocalDatabase } from '../contributions/local-db.mjs';
const env = () => ({ CONTRIBUTIONS_DB: { prepare() { throw Error('No database access permitted'); } }, EDITOR_KEY: 'x'.repeat(40), CONTACT_HOSTNAMES: 'heritage.example', CONTACT_TURNSTILE_SITE_KEY: 'site'.repeat(10), CONTACT_TURNSTILE_SECRET_KEY: 'secret'.repeat(10), CONTACT_DELIVERY_PROVIDER: 'resend', CONTACT_RESEND_API_KEY: 'resend'.repeat(10), CONTACT_TO_EMAIL: 'owner@example.test', CONTACT_FROM_EMAIL: 'site@example.test' });
async function config(e, contact=false) { const r=await worker.fetch(new Request('https://heritage.example/api/'+(contact?'contact/config':'config')), e); assert.equal(r.status,200); assert.equal(r.headers.get('Cache-Control'),'no-store, private'); return r.json(); }
test('successful configuration payloads unchanged; no diagnostics or database calls',async()=>{
 assert.deepEqual(await config(env()), {available:true,uploads:{max_files:3,max_file_bytes:1500000}});
 assert.deepEqual(await config(env(),true),{available:true,turnstile_site_key:env().CONTACT_TURNSTILE_SITE_KEY});
});
test('coarse unavailable categories distinguish shared storage/security without secrets',async()=>{
 for(const contact of [false,true]) for(const [key,value,reason] of [['CONTRIBUTIONS_DB',undefined,'storage'],['EDITOR_KEY',undefined,'security'],['EDITOR_KEY','short','security'],['EDITOR_KEY',{},'security']]) {
  const result=await config({...env(),[key]:value},contact); assert.equal(result.available,false); assert.equal(result.readiness,reason);
  const text=JSON.stringify(result); assert.ok(!text.includes(key)); assert.ok(!text.includes('short')); assert.ok(!text.includes(env().EDITOR_KEY));
 }
});
test('verification pair and contact hostname/captcha/delivery gates remain closed',async()=>{
 assert.equal((await config({...env(),TURNSTILE_SITE_KEY:'orphan'})).readiness,'verification');
 for(const [key,value,reason] of [['CONTACT_HOSTNAMES','other.example','hostname'],['CONTACT_HOSTNAMES','bad host','hostname'],['CONTACT_TURNSTILE_SECRET_KEY','bad','verification'],['CONTACT_DELIVERY_PROVIDER','other','delivery'],['CONTACT_RESEND_API_KEY','bad','delivery'],['CONTACT_TO_EMAIL','not-email','delivery']]){
  const result=await config({...env(),[key]:value},true);assert.equal(result.available,false);assert.equal(result.readiness,reason);
 }
});
test('readiness diagnostics never authorize review or bypass origin validation',async()=>{
 let r=await worker.fetch(new Request('https://heritage.example/api/review'),{...env(),CONTRIBUTIONS_DB:createLocalDatabase()});assert.equal(r.status,401);
 r=await worker.fetch(new Request('https://heritage.example/api/config',{headers:{Origin:'https://evil.example'}}),env());assert.equal(r.status,403);
});
