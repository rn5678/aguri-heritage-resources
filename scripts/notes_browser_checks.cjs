// Run after build.py with Playwright and Chrome available. Uses local site files.
'use strict';
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {pathToFileURL}=require('node:url');
const root=path.resolve(__dirname,'..');
const base=pathToFileURL(path.join(root,'site')+path.sep).href;
const output=path.join(root,'output','notes-sources-checks');
const cases=['history.html','bn/history.html'];
const summary={passed:false,cases,widths:[1280,320],checks:[],errors:[]};

async function load(page,route){
 // A fresh document is necessary when testing initial disclosure/hash state.
 console.log('Checking '+route);
 await page.goto('about:blank',{waitUntil:'domcontentloaded'});
 await page.goto(base+route,{waitUntil:'domcontentloaded'});
 // Notes are far down the article. Settle its fonts and lazy illustrations
 // before keyboard scrolling so a genuine click can pass actionability checks.
 let readyTimeout;
 try{
  await Promise.race([
   page.evaluate(async()=>{
    await document.fonts.ready;
    await Promise.all([...document.images].map(async image=>{
     image.loading='eager';
     await image.decode().catch(()=>{});
    }));
   }),
   new Promise((_,reject)=>{readyTimeout=setTimeout(()=>reject(new Error(route+': fonts/images did not settle within 15 seconds')),15000);}),
  ]);
 }finally{clearTimeout(readyTimeout);}
}

async function noteVisible(page,label){
 assert.equal(await page.locator('details.notes').evaluate(element=>element.open),true,label+': notes opened');
 assert.ok(await page.locator('#note-2').isVisible(),label+': destination is visible');
 await page.waitForFunction(()=>{
  const rect=document.querySelector('#note-2').getBoundingClientRect();
  return rect.width>0&&rect.height>0&&rect.bottom>0&&rect.top<innerHeight;
 });
}

async function printLifecycle(page,route){
 for(const initiallyOpen of [false,true]){
  await load(page,route);
  const before=await page.evaluate(initiallyOpen=>{
   document.querySelector('details.notes').open=initiallyOpen;
   return [...document.querySelectorAll('details')].map(element=>element.open);
  },initiallyOpen);
  await page.evaluate(()=>{
   window.dispatchEvent(new Event('beforeprint'));
   // A second preview event must not overwrite the original closed state.
   window.dispatchEvent(new Event('beforeprint'));
  });
  await page.emulateMedia({media:'print'});
  assert.equal(await page.locator('details.notes').evaluate(element=>element.open),true,route+': notes open for print');
  assert.ok(await page.locator('details.notes>ol').isVisible(),route+': notes list prints');
  assert.ok(await page.locator('#notes-heading').isVisible(),route+': notes heading prints');
  assert.equal(await page.locator('details.notes>ol>li:visible').count(),
   await page.locator('details.notes>ol>li').count(),route+': every source prints');
  await page.evaluate(()=>window.dispatchEvent(new Event('afterprint')));
  await page.emulateMedia({media:'screen'});
  assert.deepEqual(await page.locator('details').evaluateAll(elements=>elements.map(element=>element.open)),
   before,route+': printing restores original details state ('+initiallyOpen+')');
  assert.equal(await page.locator('details.notes>ol').isVisible(),initiallyOpen,route+': screen visibility restored');
 }
 summary.checks.push(route+': repeated print events include every note and restore both open and closed state');
}

(async()=>{
 fs.mkdirSync(output,{recursive:true});
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try{
  const context=await browser.newContext();
  context.setDefaultTimeout(10000);
  context.setDefaultNavigationTimeout(15000);
  const page=await context.newPage();
  page.on('pageerror',error=>summary.errors.push(error.message));
  for(const route of cases){
   for(const width of summary.widths){
    const label=route+' at '+width+'px';
    await page.setViewportSize({width,height:960});
    await load(page,route);
    const notes=page.locator('details.notes');
    const toggle=notes.locator(':scope>summary');
    assert.equal(await notes.count(),1,label+': one notes disclosure');
    assert.equal(await notes.evaluate(element=>element.open),false,label+': initially closed');
    assert.equal(await notes.locator(':scope>ol').isVisible(),false,label+': sources initially collapsed');
    assert.ok(await toggle.isVisible(),label+': native summary is available');
    await toggle.focus();
    await page.keyboard.press('Enter');
    assert.ok(await notes.locator(':scope>ol').isVisible(),label+': Enter expands sources');
    await page.keyboard.press('Space');
    assert.equal(await notes.evaluate(element=>element.open),false,label+': Space collapses sources');

    const citation=page.locator('.citation a[href="#note-2"]').first();
    await citation.click();
    await noteVisible(page,label+' citation');
    assert.equal(await page.evaluate(()=>location.hash),'#note-2',label+': citation keeps its fragment');
    await toggle.click();
    assert.equal(await notes.evaluate(element=>element.open),false,label+': sources close while hash stays');
    await citation.click();
    await noteVisible(page,label+' repeated same-hash citation');
    assert.equal(await page.evaluate(()=>location.hash),'#note-2');

    await load(page,route+'#note-2');
    await noteVisible(page,label+' direct link');
    await load(page,route+'#main');
    assert.equal(await notes.evaluate(element=>element.open),false,label+': unrelated fragment leaves notes closed');
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false,label+': no horizontal overflow');
    await toggle.click();
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false,label+': expanded notes fit width');
    if(width===320){
     await toggle.scrollIntoViewIfNeeded();
     await page.screenshot({path:path.join(output,route.replaceAll('/','-')+'-320.png')});
    }
    summary.checks.push(label+': initial collapse, keyboard, citation/direct/same-hash navigation and layout');
   }
   await printLifecycle(page,route);
   console.log('Passed interactions and print lifecycle: '+route);
  }

  // The dedicated source catalogue remains directly readable in both editions.
  for(const route of ['bibliography.html','bn/bibliography.html']){
   await load(page,route);
   assert.ok(await page.locator('.source-entry').count()>0,route+': source catalogue exists');
   assert.equal(await page.locator('.source-entry:visible').count(),await page.locator('.source-entry').count(),route+': all catalogue entries visible');
   assert.equal(await page.locator('.source-entry').evaluateAll(elements=>elements.some(element=>element.closest('details:not([open])'))),false,route+': catalogue is not collapsed');
   summary.checks.push(route+': catalogue remains expanded');
  }

  // Native details remains fully operable when scripts are disabled.
  const nojs=await browser.newContext({javaScriptEnabled:false,viewport:{width:320,height:960}});
  nojs.setDefaultTimeout(10000);
  nojs.setDefaultNavigationTimeout(15000);
  const plain=await nojs.newPage();
  for(const route of cases){
   await load(plain,route);
   const notes=plain.locator('details.notes');
   assert.equal(await notes.evaluate(element=>element.open),false,route+': no-JS initial state');
   await notes.locator(':scope>summary').focus();
   await plain.keyboard.press('Enter');
   assert.ok(await notes.locator(':scope>ol').isVisible(),route+': no-JS native keyboard expansion');
   await plain.keyboard.press('Space');
   assert.equal(await notes.evaluate(element=>element.open),false,route+': no-JS native keyboard collapse');
   // Closing a long list can leave the browser adjusting its scroll anchor.
   // Bring the native control into view immediately; still use a regular click.
   await notes.locator(':scope>summary').evaluate(element=>element.scrollIntoView({behavior:'instant',block:'center'}));
   await notes.locator(':scope>summary').click();
   assert.ok(await notes.locator(':scope>ol').isVisible(),route+': no-JS native click expansion');
   summary.checks.push(route+': native keyboard/click toggle works without JavaScript');
   console.log('Passed no-JavaScript native controls: '+route);
  }
  await nojs.close();
  assert.deepEqual(summary.errors,[],'No page JavaScript errors');
  summary.passed=true;
 }finally{
  await browser.close();
 }
 fs.writeFileSync(path.join(output,'browser-checks.json'),JSON.stringify(summary,null,2)+'\n');
 console.log('Notes checks passed: both editions, desktop/320px, keyboard, footnote/direct/same-hash navigation, printing, no JavaScript and bibliography.');
})().catch(error=>{
 summary.errors.push(error.stack||String(error));
 fs.mkdirSync(output,{recursive:true});
 fs.writeFileSync(path.join(output,'browser-checks.json'),JSON.stringify(summary,null,2)+'\n');
 console.error(error);
 process.exitCode=1;
});
