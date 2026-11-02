const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const path=require('node:path');
const fs=require('node:fs');
const root=path.resolve(__dirname,'..'), base='file://'+root+'/site/';
(async()=>{
const browser=await chromium.launch({channel:'chrome',headless:true});
const page=await browser.newPage(); const issues=[],logs=[];
page.on('pageerror',e=>issues.push(e.message));
page.on('console',m=>{if(m.type()==='error')issues.push(m.text());});
const names=fs.readdirSync(path.join(root,'site')).filter(name=>name.endsWith('.html')).map(name=>name.slice(0,-5));
for(const width of [1440,390,320]){
 await page.setViewportSize({width,height:960});
 for(const name of names){await page.goto(base+name+'.html');await page.waitForLoadState('load');await page.evaluate(async()=>{await Promise.all([...document.images].map(i=>{i.loading='eager';return i.decode().catch(()=>{});}));});
  const layout=await page.evaluate(()=>({overflow:document.documentElement.scrollWidth>innerWidth+1,images:[...document.images].filter(i=>!i.complete||!i.naturalWidth).map(i=>i.src)}));
  if(layout.overflow)issues.push(`${name} horizontal overflow at ${width}`);
  if(layout.images.length)issues.push(`${name} broken images: ${layout.images}`);
  assert.equal(await page.locator('h1').count(),1);
 }
 logs.push(`All ${names.length} pages checked at ${width}px.`);
}
await page.setViewportSize({width:1440,height:1000});
await page.goto(base+'index.html');await page.screenshot({path:root+'/research/desktop-home.png',fullPage:true});
await page.getByRole('button',{name:'Search',exact:true}).click();await page.locator('#site-search').fill('electricity');assert.ok(await page.locator('.search-result').count()>0);await page.keyboard.press('Escape');await page.waitForFunction(()=>!document.querySelector('#search-dialog').open);assert.equal(await page.locator('#search-dialog').evaluate(e=>e.open),false);
await page.goto(base+'archives.html?volume=2&scan=1#reader');assert.match(await page.locator('#reader-status').innerText(),/Volume II.*1 of 167/);assert.match(await page.locator('#notes-panel').innerText(),/tells its own story/);
await page.locator('#next-scan').click();assert.match(await page.locator('#reader-status').innerText(),/scan 2 of 167/);
await page.locator('#ocr-tab').click();assert.ok((await page.locator('#ocr-text').innerText()).length>100);
await page.locator('#scan-number').fill('9999');await page.locator('#go-scan').click();assert.equal(await page.locator('#scan-number').inputValue(),'167');assert.equal(await page.locator('#next-scan').isDisabled(),true);
await page.locator('#scan-number').fill('0');await page.locator('#go-scan').click();assert.equal(await page.locator('#scan-number').inputValue(),'1');
await page.locator('#journal-query').fill('electricity');await page.locator('#journal-search-form').getByRole('button',{name:'Search',exact:true}).click();assert.ok(await page.locator('.journal-result').count()>0);await page.locator('.journal-result').filter({hasText:'scan 9'}).first().click();assert.match(await page.locator('#notes-panel').innerText(),/Finding Bengali words/);
await page.locator('#journal-query').fill('সমিতি');await page.locator('#journal-search-form').getByRole('button',{name:'Search',exact:true}).click();assert.ok(await page.locator('.journal-result').count()>0);
await page.locator('#journal-query').fill('zzzxq-no-such-phrase');await page.locator('#journal-search-form').getByRole('button',{name:'Search',exact:true}).click();assert.equal(await page.locator('.journal-result').count(),0);assert.match(await page.locator('#journal-search-status').innerText(),/No matches/);
await page.goto(base+'archives.html?volume=1&scan=9#reader');await page.locator('#reader').scrollIntoViewIfNeeded();await page.locator('#reader').screenshot({path:root+'/research/desktop-reader.png'});
await page.goto(base+'bibliography.html');await page.getByRole('button',{name:'Original journals',exact:true}).click();assert.equal(await page.locator('.source-entry:visible').count(),2);await page.getByRole('button',{name:'All sources',exact:true}).click();assert.equal(await page.locator('.source-entry:visible').count(),Object.keys(JSON.parse(fs.readFileSync(root+'/content/sources.json','utf8'))).length);
await page.setViewportSize({width:390,height:844});await page.goto(base+'index.html');assert.equal(await page.locator('#main-nav').isVisible(),false);await page.getByRole('button',{name:/Menu/}).click();assert.equal(await page.locator('#main-nav').isVisible(),true);await page.getByRole('button',{name:/Menu/}).click();await page.screenshot({path:root+'/research/mobile-home.png'});await page.goto(base+'people.html');await page.getByRole('button',{name:'Search',exact:true}).click();await page.locator('#site-search').fill('Panja');assert.ok(await page.locator('.search-result').filter({hasText:'Lives behind the history'}).count()>0);await page.keyboard.press('Escape');await page.goto(base+'archives.html?volume=1&scan=9#reader');await page.locator('#reader').scrollIntoViewIfNeeded();await page.locator('#reader').screenshot({path:root+'/research/mobile-reader.png'});
logs.push('PASS: site search, Escape/focus dialog, volume switching, page navigation/clamping, both journal searches, empty results, source filters, mobile menu and direct file access.');
const nojs=await browser.newPage({javaScriptEnabled:false});await nojs.goto(base+'archives.html');assert.equal(await nojs.locator('noscript').isVisible(),true);assert.equal(await nojs.getByRole('link',{name:/Open original Volume I PDF/}).count(),1);await nojs.close();logs.push('PASS: original PDFs and reading links accessible without JavaScript.');
await browser.close();fs.writeFileSync(root+'/research/browser-checks.json',JSON.stringify({logs,issues},null,2));console.log(JSON.stringify({logs,issues},null,2));if(issues.length)process.exitCode=1;
})().catch(e=>{console.error(e);process.exit(1);});
