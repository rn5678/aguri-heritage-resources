// Run after build.py with Playwright and Chrome available.
// Uses local files, so citations must still contain the public page address.
'use strict';
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {pathToFileURL}=require('node:url');
const root=path.resolve(__dirname,'..');
const base=pathToFileURL(path.join(root,'site')+path.sep).href;
const output=path.join(root,'output','page-citations-2026-10-09');
const cases=['index.html','history.html','bn/history.html','person-hare-krishna-konar.html',
 'bn/person-pratap-chandra-ray.html','translation-rajput-publishers-note.html','bn/translation-rajput-publishers-note.html'];

(async()=>{
 fs.mkdirSync(output,{recursive:true});
 const browser=await chromium.launch({channel:'chrome',headless:true});
 const errors=[];
 try{
  const context=await browser.newContext();
  await context.addInitScript(()=>{
   window.__copied=null;
   Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async text=>{window.__copied=text;}}});
  });
  const page=await context.newPage();
  page.on('pageerror',error=>errors.push(error.message));
  for(const route of cases){
   for(const width of [1280,320]){
    await page.setViewportSize({width,height:1000});
    await page.goto(base+route);
    const date=page.locator('.page-updated time');
    assert.equal(await date.count(),1,route+': one visible update date');
    assert.ok(await date.isVisible(),route+': date is visible');
    const iso=await date.getAttribute('datetime');
    assert.match(iso,/^\d{4}-\d{2}-\d{2}$/);
    assert.equal(await page.locator('.citation-text time').getAttribute('datetime'),iso);
    const schema=JSON.parse(await page.locator('script[type="application/ld+json"]').textContent());
    assert.equal(schema['@graph'].find(item=>item['@type']==='WebPage').dateModified,iso);
    assert.equal(await page.locator('.page-citation').evaluate(element=>element.open),false);
    await page.locator('.page-citation>summary').focus();
    await page.keyboard.press('Enter');
    assert.ok(await page.locator('.citation-text').isVisible(),route+': keyboard opens citation');
    await page.locator('.citation-copy').click();
    await page.waitForFunction(()=>window.__copied!==null);
    const text=await page.evaluate(()=>window.__copied);
    assert.equal(text,(await page.locator('.citation-text').textContent()).trim().replace(/\s+/g,' '));
    assert.ok(text.includes(await page.locator('link[rel=canonical]').getAttribute('href')));
    assert.ok(!text.includes('file:')&&!text.includes('localhost'));
    assert.ok((await page.locator('.citation-status').innerText()).length>0);
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false,route+': fits '+width+'px');
   }
  }
  // The reader keeps its selected scan, without copying tracking parameters.
  await page.goto(base+'archives.html?volume=2&scan=9&utm_source=test');
  await page.locator('.page-citation>summary').click();
  await page.locator('.citation-copy').click();
  assert.match(await page.evaluate(()=>window.__copied),/\/archives\?volume=2&scan=9/);
  assert.ok(!(await page.evaluate(()=>window.__copied)).includes('utm_source'));
  await page.locator('#next-scan').click();
  await page.locator('.citation-copy').click();
  assert.match(await page.evaluate(()=>window.__copied),/\/archives\?volume=2&scan=10/);

  // Clipboard denial should try the fallback, then offer readable manual copying.
  await page.goto(base+'history.html');
  await page.locator('.page-citation>summary').click();
  await page.evaluate(()=>{
   navigator.clipboard.writeText=async()=>{throw new Error('Denied');};
   document.execCommand=command=>{window.__fallback=command;return true;};
  });
  await page.locator('.citation-copy').click();
  assert.equal(await page.evaluate(()=>window.__fallback),'copy');
  assert.equal(await page.locator('.citation-status').innerText(),'Citation copied.');
  assert.equal(await page.evaluate(()=>document.activeElement.className),'citation-copy');
  await page.evaluate(()=>{document.execCommand=()=>false;});
  await page.locator('.citation-copy').click();
  assert.match(await page.locator('.citation-status').innerText(),/Select the citation text/);
  assert.ok(await page.locator('.citation-text').isVisible());

  // Printing preserves the update date and existing attribution, hides controls.
  await page.emulateMedia({media:'print'});
  assert.ok(await page.locator('.page-updated').isVisible());
  assert.ok(await page.locator('.print-source').isVisible());
  assert.equal(await page.locator('.page-citation').isVisible(),false);
  await page.emulateMedia({media:'screen'});
  for(const route of ['404.html','bn/404.html','contribute.html','review.html']){
   await page.goto(base+route);
   assert.equal(await page.locator('.page-citation,.page-updated').count(),0);
  }
  // Static citations still work with JavaScript turned off.
  const nojs=await browser.newContext({javaScriptEnabled:false,viewport:{width:390,height:844}});
  const plain=await nojs.newPage();
  await plain.goto(base+'bn/history.html');
  await plain.locator('.page-citation>summary').click();
  assert.ok(await plain.locator('.citation-text').isVisible());
  assert.equal(await plain.locator('.citation-copy').isVisible(),false);
  assert.ok((await plain.locator('.page-updated').innerText()).includes('সর্বশেষ হালনাগাদ'));
  await nojs.close();

  for(const [route,width,name] of [['history.html',1280,'desktop-history'],['bn/history.html',390,'mobile-bn-history'],['index.html',1280,'desktop-home']]){
   await page.setViewportSize({width,height:1000});
   await page.goto(base+route);
   await page.evaluate(()=>document.fonts.ready);
   await page.locator('.page-citation>summary').click();
   await page.screenshot({path:path.join(output,name+'.png'),fullPage:false});
  }
  assert.deepEqual(errors,[],'No page JavaScript errors');
  fs.writeFileSync(path.join(output,'browser-checks.json'),JSON.stringify({passed:true,cases,checks:['desktop/mobile','keyboard','clipboard and fallback','archive scan navigation','print','no JavaScript','excluded forms/error pages']},null,2)+'\n');
  console.log('Citation checks passed: both editions, desktop/mobile, copying, archive scans, print and no-JavaScript fallback.');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
