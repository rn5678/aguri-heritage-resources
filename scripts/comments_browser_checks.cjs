/* Local browser tests only: all comments and Google responses are mocked. */
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
(async () => {
  const browser = await chromium.launch({executablePath:process.env.CHROME_PATH || '/usr/bin/chromium',headless:true,args:['--no-sandbox']});
  try {
    for (const lang of ['en','bn']) {
      const context = await browser.newContext({viewport:{width:390,height:844}}), page = await context.newPage();
      let enabled=true, outage=false, signedIn=false, googleRequests=0, posted=[], deleted=false;
      const own = () => posted.map((p,i)=>({id:'own-'+i,page:p.page,name:'Test Reader',body:p.body,created_at:'2026-11-09T10:00:00Z',status:'pending'}));
      await context.route('**/*',async route=>{
        const url=new URL(route.request().url()), request=route.request();
        if(url.hostname==='accounts.google.com') {
          googleRequests++;
          return route.fulfill({contentType:'application/javascript',body:`window.google={accounts:{id:{initialize(options){window.gisOptions=options;},renderButton(target){const b=document.createElement('button');b.textContent='Mock Google';b.onclick=()=>window.gisOptions.callback({credential:'test-only-credential'});target.append(b);},disableAutoSelect(){}}}};`});
        }
        if(url.pathname.startsWith('/api/comments')) {
          if(outage)return route.fulfill({status:503,body:'{}'});
          const p=url.pathname.slice('/api/comments'.length);let result={};
          if(p==='/config')result={available:enabled,google_client_id:'test-client',terms_version:'comments-2026-11-09',max_length:2000};
          else if(p==='/me')result=signedIn?{user:{id:'reader',name:'Test Reader'},csrf_token:'test-csrf'}:{user:null};
          else if(p==='/auth/nonce')result={nonce:'nonce-test'};
          else if(p==='/auth/google'){assert.deepEqual(request.postDataJSON(),{credential:'test-only-credential',nonce:'nonce-test'});signedIn=true;result={user:{id:'reader',name:'Test Reader'},csrf_token:'test-csrf'};}
          else if(p==='/auth/logout'){assert.equal(request.headers()['x-csrf-token'],'test-csrf');signedIn=false;}
          else if(p==='/mine')result={comments:deleted?[]:own()};
          else if(p===''&&request.method()==='GET'){assert.equal(url.searchParams.get('page'),'index');result={comments:[{id:'public-1',name:'<img src=x onerror=alert(1)>',body:'<script>alert(1)</script>',created_at:'2026-11-09T10:00:00Z'}],next_cursor:null};}
          else if(p===''&&request.method()==='POST'){const body=request.postDataJSON();assert.equal(request.headers()['x-csrf-token'],'test-csrf');assert.equal(body.consent,true);assert.equal(body.terms_version,'comments-2026-11-09');assert.equal(body.page,'index');assert.match(body.client_id,/^[a-f0-9-]{36}$/);posted.push(body);result={id:'own-0',status:'pending'};}
          else if(request.method()==='DELETE')deleted=true;
          else if(p.endsWith('/report'))assert.equal(request.postDataJSON().reason,'Test report');
          else throw new Error('Unexpected API '+p);
          return route.fulfill({contentType:'application/json',body:JSON.stringify(result)});
        }
        if(url.pathname.startsWith('/api/'))return route.fulfill({status:404,body:'{}'});
        const filename=path.join(root,'site',decodeURIComponent(url.pathname));
        if(fs.existsSync(filename)&&fs.statSync(filename).isFile())return route.fulfill({path:filename});
        return route.fulfill({status:404,body:''});
      });
      const url='https://aguri.test/'+(lang==='bn'?'bn/':'')+'index.html';
      await page.goto(url); const comments=page.locator('[data-comments]');await comments.waitFor({state:'visible'});
      await page.waitForFunction(()=>document.querySelector('.comment-body'));
      assert.equal(googleRequests,0,'Google not loaded on page visit');
      assert.equal(await comments.locator('img, script').count(),0,'Untrusted comment remains text');
      assert.equal(await comments.locator('textarea').isVisible(),false);
      await comments.getByRole('button',{name:lang==='bn'?'Google দিয়ে সাইন ইন করুন':'Sign in with Google',exact:true}).click();
      await comments.getByRole('button',{name:'Mock Google'}).click();
      await comments.locator('textarea').waitFor({state:'visible'});
      assert.equal(await page.evaluate(()=>window.gisOptions.nonce),'nonce-test');
      await comments.locator('textarea').fill('A source-based comment');
      await comments.locator('input[type=checkbox]').check();
      await comments.locator('button[type=submit]').click();
      await page.waitForFunction(()=>document.querySelector('[data-comments] textarea').value==='');
      assert.equal(posted.length,1);assert.equal(await comments.locator('textarea').getAttribute('maxlength'),'2000');
      await page.waitForFunction(()=>document.querySelector('[data-comments]').textContent.includes('A source-based comment'));
      page.once('dialog',dialog=>dialog.accept('Test report'));
      await comments.getByRole('button',{name:lang==='bn'?'অভিযোগ করুন':'Report',exact:true}).click();
      page.once('dialog',dialog=>dialog.accept());
      await comments.getByRole('button',{name:lang==='bn'?'আমার মন্তব্য মুছুন':'Delete my comment'}).click();
      await page.waitForFunction(()=>!document.querySelector('[data-comments]').textContent.includes('A source-based comment'));
      assert.equal(deleted,true);
      await comments.locator('textarea').fill('Keep this draft'); await comments.locator('input[type=checkbox]').check();outage=true;
      await comments.locator('button[type=submit]').click();await page.waitForFunction(()=>document.querySelector('[data-comments] [role=status]').textContent.length>0);
      assert.equal(await comments.locator('textarea').inputValue(),'Keep this draft');
      assert.ok(await page.locator('main').innerText(),'Article remains available on outage');
      outage=false;await comments.getByRole('button',{name:lang==='bn'?'সাইন আউট':'Sign out',exact:true}).click();
      await comments.locator('textarea').waitFor({state:'hidden'});
      assert.equal(await page.evaluate(()=>JSON.stringify({...localStorage,...sessionStorage}).includes('test-only-credential')),false,'No identity tokens in browser storage');
      enabled=false;await page.reload();await page.waitForTimeout(200);assert.equal(await comments.isVisible(),false);
      assert.ok(await page.locator('h1').innerText());
      await context.close();
    }
    // Structural checks include special layouts and excluded utility pages.
    for(const language of ['', 'bn/']) {
      for(const file of fs.readdirSync(path.join(root,'site',language)).filter(p=>p.endsWith('.html'))) {
        const html=fs.readFileSync(path.join(root,'site',language,file),'utf8');
        const excluded=['404.html','contact.html','contribute.html','review.html','editor.html','admin.html'].includes(file);
        assert.equal(html.includes('data-comments hidden'),!excluded,file+' comment mount');
      }
    }
    console.log('Comments: bilingual browser flows, consent, nonce login, XSS safety, deletion/reporting, outages, disabled UI and page coverage passed.');
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
