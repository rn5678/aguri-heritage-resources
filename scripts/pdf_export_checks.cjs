// Run after build.py. Requires Playwright, Chrome and Poppler on PATH.
// QA artifacts stay outside the public site in research/pdf-export-checks/.
'use strict';
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {pathToFileURL}=require('node:url');
const {execFileSync}=require('node:child_process');

const root=path.resolve(__dirname,'..');
const output=path.join(root,'research','pdf-export-checks');
const base=pathToFileURL(path.join(root,'site')+path.sep).href;
const summary={checks:[],pdfs:[],issues:[]};
const normalize=text=>text.normalize('NFC').replace(/[\s\u00ad\u200b-\u200f\ufeff]/gu,'');
const hiddenUI='.edition-bar,.site-header,.site-footer,nav,.page-heading>.eyebrow,.page-tools,dialog,.reader-controls,.reader-search,.reader-tabs,.filter-bar,iframe,object,.translation-source,.translation-transcript,.english-comparison,.profile-navigation,.person-copy>p:has(>.text-link)';
const expandable='details.origins-timeline-text,details.translation-notes';
const cases=[
 {route:'index.html'},
 {route:'bn/index.html'},
 {route:'origins.html',tail:'.origins-article>p'},
 {route:'bn/origins.html',tail:'.origins-article>p'},
 {route:'person-pratap-chandra-ray.html',tail:'.person-copy>p:not(:has(a.text-link))'},
 {route:'bn/person-pratap-chandra-ray.html',tail:'.person-copy>p:not(:has(a.text-link))'},
 {route:'translation-rajput-publishers-note.html',tail:'.translation-prose>p'},
 {route:'bn/translation-rajput-publishers-note.html',tail:'.bengali-transcription>p'},
 {route:'archives.html?volume=1&scan=9#reader',ocr:true},
 {route:'bn/archives.html?volume=1&scan=9#reader',ocr:true},
 {route:'bibliography.html',filter:true},
 {route:'bn/bibliography.html',filter:true},
 {route:'book-rajput-o-ugrakshatriya.html'},
];

async function ready(page){
 await page.evaluate(async()=>{
  await document.fonts.ready;
  await Promise.all([...document.images].map(async image=>{
   image.loading='eager';
   await image.decode().catch(()=>{});
  }));
 });
}

async function testLifecycle(page,route){
 await page.goto(base+route);
 await ready(page);
 assert.ok(await page.locator(expandable).count(),`${route}: lifecycle fixture has expandable content`);
 for(const initiallyOpen of [false,true]){
  const state=await page.evaluate(({expandable,initiallyOpen})=>{
   document.querySelectorAll(expandable).forEach(detail=>{detail.open=initiallyOpen;});
   const before=[...document.querySelectorAll('details')].map(detail=>detail.open);
   window.dispatchEvent(new Event('beforeprint'));
   // Browsers may dispatch more than one beforeprint event for a preview.
   window.dispatchEvent(new Event('beforeprint'));
   const expanded=[...document.querySelectorAll(expandable)].every(detail=>detail.open);
   window.dispatchEvent(new Event('afterprint'));
   return {
    before,expanded,after:[...document.querySelectorAll('details')].map(detail=>detail.open),
   };
  },{expandable,initiallyOpen});
  assert.equal(state.expanded,true,`${route}: supplementary content expands for print`);
  assert.deepEqual(state.after,state.before,`${route}: details restored after print (${initiallyOpen})`);
 }
 summary.checks.push(`${route}: browser print events expand relevant text and restore both closed/open details after repeated beforeprint events.`);
}

(async()=>{
 fs.mkdirSync(output,{recursive:true});
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1280,height:960}});
  page.on('pageerror',error=>summary.issues.push(error.message));
  await testLifecycle(page,'origins.html');
  await testLifecycle(page,'translation-rajput-publishers-note.html');
  await page.goto(base+'404.html');
  assert.equal(await page.locator('.page-tools').count(),0,'404 omits article tools');
  assert.equal(await page.locator('button.pdf-export').count(),0,'404 has no site export button');
  await page.goto(base+'bn/404.html');
  assert.equal(await page.locator('.page-tools').count(),0,'Bengali 404 omits article tools');
  assert.equal(await page.locator('button.pdf-export').count(),0,'Bengali 404 has no site export button');
  await page.setViewportSize({width:1280,height:980});
  await page.goto(base+'origins.html');
  await ready(page);
  await page.screenshot({path:path.join(output,'desktop-origins.png')});
  await page.setViewportSize({width:390,height:844});
  await page.goto(base+'bn/history.html');
  await ready(page);
  await page.screenshot({path:path.join(output,'mobile-bn-history.png')});

  for(const item of cases){
   const name=item.route.split(/[?#]/)[0].replace(/\.html$/,'').replaceAll('/','-');
   await page.emulateMedia({media:'screen'});
   await page.setViewportSize({width:320,height:900});
   await page.goto(base+item.route);
   await ready(page);
   assert.equal(await page.locator('button.pdf-export').count(),0,`${name}: no site export button`);
   assert.equal(await page.locator('#pdf-export-help').count(),0,`${name}: no site export instructions`);
   assert.equal(await page.locator('.print-source').isVisible(),false,`${name}: attribution stays out of screen content`);
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false,`${name}: no overflow at 320px`);
   if(item.filter){
    await page.locator('[data-source-filter="primary"]').click();
    assert.ok(await page.locator('.source-entry[hidden]').count(),`${name}: source filter fixture is active`);
   }
   if(item.ocr){
    await page.locator('#ocr-tab').click();
    assert.ok((await page.locator('#ocr-text').innerText()).length>100,`${name}: selected OCR has content`);
   }
   const stateBefore=await page.evaluate(()=>({
    details:[...document.querySelectorAll('details')].map(detail=>detail.open),
    hiddenSources:[...document.querySelectorAll('.source-entry[hidden]')].map(source=>source.id),
   }));
   const title=await page.locator('h1').innerText();
   const canonical=await page.locator('link[rel=canonical]').getAttribute('href');
   const tail=item.tail && await page.locator(item.tail).count()?await page.locator(item.tail).last().innerText():null;
   await page.setViewportSize({width:794,height:1123});
   await page.emulateMedia({media:'print'});
   await page.evaluate(()=>window.dispatchEvent(new Event('beforeprint')));
   assert.equal(await page.locator('h1').isVisible(),true,`${name}: title remains visible`);
   assert.equal(await page.locator('.print-source').count(),1,`${name}: one source attribution`);
   assert.equal(await page.locator('.print-source').isVisible(),true,`${name}: attribution prints`);
   assert.match(await page.locator('.print-source').innerText(),/Aguri Heritage/,`${name}: project credit prints`);
   assert.ok((await page.locator('.print-source').innerText()).includes(canonical),`${name}: canonical source URL prints`);
   for(const element of await page.locator(hiddenUI).all()){
    assert.equal(await element.isVisible(),false,`${name}: print excludes ${await element.evaluate(node=>node.tagName+'.'+node.className)}`);
   }
   const clipped=await page.locator('.data-table,.origins-timeline-visual,.ocr-text').evaluateAll(elements=>elements.filter(element=>{
    if(!element.getClientRects().length)return false;
    const style=getComputedStyle(element);
    return (element.scrollWidth>element.clientWidth+2 && ['auto','scroll','hidden','clip'].includes(style.overflowX)) ||
     (element.scrollHeight>element.clientHeight+2 && ['auto','scroll','hidden','clip'].includes(style.overflowY));
   }).map(element=>element.className));
   assert.deepEqual(clipped,[],`${name}: print content has no scroll clipping`);
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+2),false,`${name}: print content fits page width`);
   if(item.filter){
    assert.equal(await page.locator('.source-entry:visible').count(),await page.locator('.source-entry').count(),`${name}: every source prints despite the active filter`);
   }
   if(item.ocr){
    assert.equal(await page.locator('#ocr-panel').isVisible(),true,`${name}: selected reader content prints`);
    assert.equal(await page.locator('#notes-panel').isVisible(),false,`${name}: other reader tab stays hidden`);
   }

   const pdf=path.join(output,name+'.pdf');
   await page.pdf({path:pdf,format:'A4',preferCSSPageSize:true,printBackground:false,displayHeaderFooter:false});
   const extracted=execFileSync('pdftotext',['-layout',pdf,'-'],{encoding:'utf8'});
   const compact=normalize(extracted);
   assert.ok(compact.includes('AguriHeritage'),`${name}: PDF contains project attribution`);
   assert.ok(compact.includes(normalize(canonical)),`${name}: PDF contains the canonical source URL`);
   assert.ok(compact.includes(normalize(title)),`${name}: PDF contains its page title`);
   if(tail)assert.ok(compact.includes(normalize(tail)),`${name}: PDF retains the final substantive paragraph`);
   assert.equal(compact.includes('Independentheritageproject·Englishedition·2026'),false,`${name}: website footer excluded from PDF`);
   assert.equal(extracted.includes('file:///'),false,`${name}: no local file path in PDF`);
   const info=execFileSync('pdfinfo',[pdf],{encoding:'utf8'});
   const pages=Number(info.match(/^Pages:\s+(\d+)/m)?.[1]);
   assert.ok(pages>0,`${name}: readable PDF produced`);
   const fonts=execFileSync('pdffonts',[pdf],{encoding:'utf8'});
   if(item.route.startsWith('bn/') || item.ocr){
    assert.match(fonts,/NotoSerifBengali.*\byes\s+yes\s+yes\b/,`${name}: searchable Bengali font is embedded`);
    assert.match(extracted,/[\u0980-\u09ff]/u,`${name}: Bengali PDF text is extractable`);
   }
   // First/last pages expose title/attribution and article truncation errors for visual review.
   for(const number of new Set([1,pages])){
    execFileSync('pdftoppm',['-f',String(number),'-l',String(number),'-singlefile','-r','100','-png',pdf,path.join(output,`${name}-page-${number}`)]);
   }
   await page.evaluate(()=>window.dispatchEvent(new Event('afterprint')));
   await page.emulateMedia({media:'screen'});
   const stateAfter=await page.evaluate(()=>({
    details:[...document.querySelectorAll('details')].map(detail=>detail.open),
    hiddenSources:[...document.querySelectorAll('.source-entry[hidden]')].map(source=>source.id),
   }));
   assert.deepEqual(stateAfter,stateBefore,`${name}: browser printing preserves screen details and source filter`);
   summary.pdfs.push({page:item.route,path:path.relative(root,pdf),pages,bytes:fs.statSync(pdf).size});
   summary.checks.push(`${name}: mobile layout, absence of site export controls, clean browser print layout, source attribution, actual PDF text/font checks and restored screen state passed.`);
  }
  assert.deepEqual(summary.issues,[],'No JavaScript errors');
 }finally{
  await browser.close();
 }
 summary.passed=true;
 fs.writeFileSync(path.join(output,'summary.json'),JSON.stringify(summary,null,2)+'\n');
 console.log(JSON.stringify(summary,null,2));
})().catch(error=>{
 summary.passed=false;
 summary.issues.push(error.stack||String(error));
 fs.mkdirSync(output,{recursive:true});
 fs.writeFileSync(path.join(output,'summary.json'),JSON.stringify(summary,null,2)+'\n');
 console.error(error);
 process.exitCode=1;
});
