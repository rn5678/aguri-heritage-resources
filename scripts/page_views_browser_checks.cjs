// Focused page-counter checks using mocked same-origin HTTP responses only.
// No build or live deployment is needed. Requires Playwright and Chrome.
'use strict';
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const os=require('node:os');
const {pathToFileURL}=require('node:url');
const script=fs.readFileSync(path.join(__dirname,'..','assets','page-views.js'),'utf8');
const origin='https://views.test';
const key=page=>'aguri:page-views:'+page;
const fixture=(page,inline=false)=>`<!doctype html><html lang="${page.startsWith('/bn/')?'bn':'en'}"><head><meta charset="utf-8"></head><body><p class="page-views" data-page-views="${page}" hidden><span>Page views:</span> <span data-view-count></span></p>${inline?'<script>'+script+'</script>':'<script src="/assets/page-views.js"></script>'}</body></html>`;

async function harness(browser,{storageDisabled=false,hidden=false,offline=false,shortTimeout=false}={}){
 const context=await browser.newContext();
 const requests=[],totals=new Map(),errors=[];
 let mode='ok';
 await context.addInitScript(({storageDisabled,hidden,offline,shortTimeout})=>{
  window.__visibility=hidden?'hidden':'visible';
  Object.defineProperty(document,'visibilityState',{configurable:true,get:()=>window.__visibility});
  if(storageDisabled)Object.defineProperty(window,'sessionStorage',{get(){throw new DOMException('Storage unavailable','SecurityError');}});
  if(offline)Object.defineProperty(navigator,'onLine',{get:()=>false});
  window.__viewFetches=[];window.__viewFetchSettled=0;
  const originalFetch=window.fetch.bind(window);
  window.fetch=(url,options)=>{
   window.__viewFetches.push({url,method:options.method,credentials:options.credentials,referrerPolicy:options.referrerPolicy,mode:options.mode,redirect:options.redirect,cache:options.cache,body:options.body||null});
   return originalFetch(url,options).finally(()=>window.__viewFetchSettled++);
  };
  if(shortTimeout){const originalTimeout=window.setTimeout.bind(window);window.setTimeout=(fn,delay,...args)=>originalTimeout(fn,delay===8000?20:delay,...args);}
 },{storageDisabled,hidden,offline,shortTimeout});
 await context.route(origin+'/**',async route=>{
  const request=route.request(),url=new URL(request.url());
  if(url.pathname==='/assets/page-views.js')return route.fulfill({contentType:'text/javascript',body:script});
  if(url.pathname==='/api/page-views'){
   const page=request.method()==='POST'?request.postDataJSON().page:url.searchParams.get('page');
   requests.push({method:request.method(),page,headers:request.headers()});
   if(mode==='abort')return route.abort('failed');
   if(mode==='timeout')return;
   if(mode==='unavailable')return route.fulfill({status:503,json:{error:'unavailable'}});
   if(mode==='wrong-page')return route.fulfill({json:{page:'/wrong',views:42}});
   if(mode==='string-count')return route.fulfill({json:{page,views:'42'}});
   if(mode==='negative')return route.fulfill({json:{page,views:-1}});
   if(mode==='fraction')return route.fulfill({json:{page,views:1.5}});
   if(mode==='unsafe')return route.fulfill({json:{page,views:Number.MAX_SAFE_INTEGER+1}});
   if(mode==='malformed')return route.fulfill({contentType:'application/json',body:'not JSON'});
   if(request.method()==='POST')totals.set(page,(totals.get(page)||0)+1);
   return route.fulfill({json:{page,views:totals.get(page)||0}});
  }
  const page=url.pathname.replace(/\.html$/,'').replace(/^\/index$/,'/')||'/';
  return route.fulfill({contentType:'text/html',body:fixture(page)});
 });
 const page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));
 return {context,page,requests,totals,errors,setMode:value=>{mode=value;}};
}
async function shown(page){await page.locator('.page-views').waitFor({state:'visible'});}
async function settled(page){
 await page.waitForFunction(()=>window.__viewFetchSettled===1);
 await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
}
async function visibility(page,state){await page.evaluate(value=>{window.__visibility=value;document.dispatchEvent(new Event('visibilitychange'));},state);}

(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 const checks=[];let temporary;
 try{
  const h=await harness(browser),{page}=h;
  await h.context.addCookies([{name:'unrelated',value:'must-not-be-sent',url:origin}]);
  await page.goto(origin+'/history.html');await shown(page);
  assert.equal(await page.locator('[data-view-count]').textContent(),'1');
  assert.deepEqual(h.requests.map(r=>r.method),['POST']);
  const options=await page.evaluate(()=>window.__viewFetches[0]);
  assert.equal(options.credentials,'omit');assert.equal(options.referrerPolicy,'no-referrer');
  assert.equal(options.mode,'same-origin');assert.equal(options.redirect,'error');assert.equal(options.cache,'no-store');
  assert.deepEqual(JSON.parse(options.body),{page:'/history'});
  assert.equal(h.requests[0].headers.cookie,undefined);assert.equal(h.requests[0].headers.referer,undefined);
  await page.reload();await shown(page);
  await page.goto(origin+'/history?campaign=test#section');await shown(page);
  assert.deepEqual(h.requests.map(r=>r.method),['POST','GET','GET']);
  assert.equal(h.totals.get('/history'),1);
  await page.goto(origin+'/culture');await shown(page);
  assert.equal(h.totals.get('/culture'),1);
  h.totals.set('/bn/history',123455);
  await page.goto(origin+'/bn/history');await shown(page);
  assert.equal(await page.locator('[data-view-count]').textContent(),new Intl.NumberFormat('bn-IN').format(123456));
  assert.equal(h.totals.get('/history'),1);
  await page.evaluate(storageKey=>sessionStorage.setItem(storageKey,String(Date.now()-31*60*1000)),key('/history'));
  await page.goto(origin+'/history');await shown(page);
  assert.equal(h.totals.get('/history'),2,'expired page window can increment again');
  h.totals.set('/history',123456);
  await page.reload();await shown(page);
  assert.equal(await page.locator('[data-view-count]').textContent(),'1,23,456');
  h.totals.set('/history',0);
  await page.reload();await shown(page);
  assert.equal(await page.locator('[data-view-count]').textContent(),'0','zero is a valid exact server total');
  assert.deepEqual(h.errors,[]);await h.context.close();
  checks.push('canonical aliases, 30-minute session window, independent pages/editions, exact English/Bengali formatting, zero and privacy options');

  const fresh=await harness(browser);await fresh.page.goto(origin+'/history');await shown(fresh.page);
  assert.equal(fresh.requests[0].method,'POST','a new session starts its own page window');await fresh.context.close();
  const disabled=await harness(browser,{storageDisabled:true});
  await disabled.page.goto(origin+'/history');await shown(disabled.page);
  await visibility(disabled.page,'hidden');await visibility(disabled.page,'visible');
  assert.equal(disabled.requests.length,1,'storage failure still counts once per document');
  await disabled.page.reload();await shown(disabled.page);assert.equal(disabled.requests.length,2);
  await disabled.context.close();checks.push('new session and storage-unavailable best effort');

  const background=await harness(browser,{hidden:true});await background.page.goto(origin+'/history');
  assert.equal(background.requests.length,0);assert.equal(await background.page.locator('.page-views').isVisible(),false);
  await visibility(background.page,'visible');await shown(background.page);
  await visibility(background.page,'hidden');await visibility(background.page,'visible');
  assert.equal(background.requests.length,1);await background.context.close();
  const offline=await harness(browser,{offline:true});await offline.page.goto(origin+'/history');
  assert.equal(offline.requests.length,0);assert.equal(await offline.page.locator('.page-views').isVisible(),false);
  await offline.context.close();checks.push('background tabs wait for visibility and offline pages send nothing');

  for(const mode of ['unavailable','abort','wrong-page','string-count','negative','fraction','unsafe','malformed','timeout']){
   const failure=await harness(browser,{shortTimeout:mode==='timeout'});failure.setMode(mode);
   await failure.page.goto(origin+'/history');await settled(failure.page);
   assert.equal(await failure.page.locator('.page-views').isVisible(),false,mode+' is hidden');
   await visibility(failure.page,'hidden');await visibility(failure.page,'visible');
   assert.equal(failure.requests.length,1,mode+' is not retried');
   failure.setMode('ok');await failure.page.reload();await shown(failure.page);
   assert.equal(failure.requests[1].method,'GET',mode+' reload cannot repeat an ambiguous POST');
   assert.deepEqual(failure.errors,[]);await failure.context.close();
  }
  checks.push('unavailable, aborted, timed-out and malformed responses remain hidden without increment retries');

  temporary=fs.mkdtempSync(path.join(os.tmpdir(),'aguri-views-'));
  const file=path.join(temporary,'index.html');fs.writeFileSync(file,fixture('/history',true));
  const local=await browser.newContext(),filePage=await local.newPage();let fileTraffic=0;
  filePage.on('request',request=>{if(/^https?:/.test(request.url()))fileTraffic++;});
  await filePage.goto(pathToFileURL(file).href);
  assert.equal(await filePage.locator('.page-views').isVisible(),false);assert.equal(fileTraffic,0);
  await local.close();checks.push('file previews generate no HTTP traffic');
  console.log(JSON.stringify({passed:true,checks},null,2));
 }finally{await browser.close();if(temporary)fs.rmSync(temporary,{recursive:true,force:true});}
})().catch(error=>{console.error(error);process.exitCode=1;});
