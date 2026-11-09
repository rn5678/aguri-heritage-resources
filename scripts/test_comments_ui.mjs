import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
const source=readFileSync(new URL('../assets/comments.js',import.meta.url),'utf8');
class Node {
  constructor(tag='div',text=''){this.tagName=tag;this.children=[];this.attrs={};this.listeners={};this.hidden=false;this.disabled=false;this.value='';this.checked=false;this._text=text;}
  set textContent(v){this._text=v;this.children=[];} get textContent(){return this._text+this.children.map(n=>n.textContent).join('');}
  append(...nodes){this.children.push(...nodes);} replaceChildren(...nodes){this._text='';this.children=nodes;} setAttribute(k,v){this.attrs[k]=v;} removeAttribute(k){delete this.attrs[k];}
  addEventListener(k,fn){this.listeners[k]=fn;} reportValidity(){return true;} focus(){} remove(){}
  async fire(name){await this.listeners[name]?.({currentTarget:this,preventDefault(){}});}
}
const find=(root,predicate)=>[root,...root.children.flatMap(n=>find(n,predicate))].filter(predicate);
const settle=()=>new Promise(resolve=>setTimeout(resolve,20));
async function setup({lang='en',available=true,outage=false}={}) {
  const root=new Node(),head=new Node('head'),calls=[];root.hidden=true;let signedIn=false,posted=[],fail=outage;
  const window={confirm:()=>true,prompt:()=> 'report reason'};
  const document={querySelector:()=>root,documentElement:{lang},body:{dataset:{page:'history'}},createElement:tag=>new Node(tag),createTextNode:text=>new Node('#text',text),head};
  const fetch=async(path,options={})=>{
    calls.push({path,options});if(fail)return {ok:false,status:503};
    let data={};
    if(path.endsWith('/config'))data={available,google_client_id:'client',terms_version:'comments-2026-11-09-direct-v1'};
    else if(path.endsWith('/me'))data={user:null};
    else if(path.endsWith('/nonce'))data={nonce:'nonce'};
    else if(path.endsWith('/google')){signedIn=true;data={user:{id:'user',name:'Reader'},csrf_token:'csrf'};}
    else if(path.includes('/mine') && path.includes('cursor=older'))data={comments:[{id:'older',name:'Reader',body:'Older comment',status:'approved',created_at:'2026-11-08'}],next_cursor:null};
    else if(path.includes('/mine'))data={next_cursor:posted.length?'older':null,comments:posted.map((c,i)=>({...c,id:'own'+i,name:'Reader',status:'approved',created_at:'2026-11-09'}))};
    else if(path==='/api/comments'&&options.method==='POST'){assert.ok(signedIn);posted.push(JSON.parse(options.body));data={id:'own0',status:'approved'};}
    else if(path.startsWith('/api/comments?page='))data={comments:[{id:'public',name:'<img src=x>',body:'<script>bad()</script>',created_at:'2026-11-09'},...posted.map((c,i)=>({...c,id:'own'+i,name:'Reader',created_at:'2026-11-09'}))],next_cursor:null};
    return {ok:true,status:200,json:async()=>data};
  };
  vm.runInNewContext(source,{document,window,fetch,setTimeout,clearTimeout,AbortController,Date,crypto:{randomUUID:()=> '12345678-1234-1234-1234-123456789abc'}});
  await settle();
  return {root,head,calls,window,posted,fail:()=>{fail=true;},find:predicate=>find(root,predicate)};
}
for(const lang of ['en','bn'])test(`Comments ${lang}: delayed Google, nonce, safe text, consent submission, draft retention`,async()=>{
  const ui=await setup({lang});assert.equal(ui.root.hidden,false);assert.equal(ui.head.children.length,0);
  assert.ok(ui.root.textContent.includes('<script>bad()</script>'));assert.equal(ui.find(n=>n.tagName==='script').length,0);
  const sign=ui.find(n=>n.tagName==='button'&&n.textContent.includes('Google'))[0];
  const signing=sign.fire('click');await settle();assert.equal(ui.head.children.length,1);
  let options;
  ui.window.google={accounts:{id:{initialize:v=>{options=v;},renderButton(){},disableAutoSelect(){}}}};
  ui.head.children[0].onload();await signing;assert.equal(options.nonce,'nonce');
  await options.callback({credential:'id-token'});assert.ok(ui.calls.some(c=>c.path.endsWith('/google')));
  const form=ui.find(n=>n.tagName==='form')[0],input=ui.find(n=>n.tagName==='textarea')[0],checkbox=ui.find(n=>n.tagName==='input')[0];
  assert.equal(form.hidden,false);input.value='Reader comment';checkbox.checked=true;const pending=form.fire('submit');assert.equal(input.disabled,true);assert.equal(checkbox.disabled,true);await pending;
  const loadOwn=ui.find(n=>n.tagName==='button'&&(n.textContent==='Load more of your comments'||n.textContent==='আপনার আরও মন্তব্য দেখুন'))[0];assert.equal(loadOwn.hidden,false);await loadOwn.fire('click');assert.ok(ui.root.textContent.includes('Older comment'));assert.equal(loadOwn.hidden,true);
  assert.equal(input.disabled,false);assert.equal(checkbox.disabled,false);
  assert.equal(ui.posted[0].consent,true);assert.equal(ui.posted[0].terms_version,'comments-2026-11-09-direct-v1');assert.equal(ui.posted[0].page,'history');assert.equal(input.value,'');assert.equal(ui.find(n=>n.tagName==='p'&&n.textContent==='Reader comment').length,2,'Posted comment is immediately shown in both public and own lists');
  const post=ui.calls.find(c=>c.path==='/api/comments'&&c.options.method==='POST');assert.equal(post.options.headers['X-CSRF-Token'],'csrf');
  input.value='Preserve draft';ui.fail();await form.fire('submit');assert.equal(input.value,'Preserve draft');assert.equal(form.attrs['aria-busy'],undefined);
});
test('Disabled or absent backend leaves comments hidden and does not load Google',async()=>{
  for(const options of [{available:false},{outage:true}]) {const ui=await setup(options);assert.equal(ui.root.hidden,true);assert.equal(ui.head.children.length,0);assert.equal(ui.calls.length,1);}
});
test('Moderation uses editor authorization, optimistic version, safe report text, and clears private queue on lock',async()=>{
  Node.prototype.querySelectorAll=function(selector){return find(this,n=>n.tagName===selector);};
  Node.prototype.querySelector=function(selector){return this.querySelectorAll(selector)[0];};
  const root=new Node(),calls=[];root.hidden=true;
  const doc={querySelector:()=>root,documentElement:{lang:'en'},createElement:tag=>new Node(tag)};
  let changed=false, queueLoads=0;
  const fetch=async(path,options={})=>{
    calls.push({path,options});
    if(path.includes('/review?'))queueLoads++;
    const data=path.endsWith('/config')?{available:true}:options.method==='PATCH'?(changed=true,{status:'approved'}):{comments:changed?[]:[{id:'test',page:'history',name:'Reader',body:'<script>no()</script>',created_at:'2026-11-09',version:3,reports:[{reason:'<img src=x>'}]}],next_cursor:changed?null:'older'};
    return {ok:true,status:200,json:async()=>data};
  };
  vm.runInNewContext(readFileSync(new URL('../assets/comments-review.js',import.meta.url),'utf8'),{document:doc,window:{confirm:()=>true,addEventListener(){}},fetch});await settle();
  const form=find(root,n=>n.tagName==='form')[0],input=find(root,n=>n.tagName==='input')[0];input.value='test-editor';await form.fire('submit');
  assert.equal(input.value,'');assert.ok(calls.some(c=>c.path.includes('status=approved')));assert.ok(root.textContent.includes('<img src=x>'));assert.equal(find(root,n=>n.tagName==='img').length,0);
  await find(root,n=>n.tagName==='button'&&n.textContent==='Load more')[0].fire('click');
  assert.equal(queueLoads,2);
  await find(root,n=>n.tagName==='button'&&n.textContent==='Hide')[0].fire('click');
  assert.equal(queueLoads,3,'Moderation of an earlier page row refreshes after pagination');
  const patch=calls.find(c=>c.options.method==='PATCH');assert.equal(JSON.parse(patch.options.body).version,3);assert.equal(patch.options.headers.Authorization,'Bearer test-editor');
  await find(root,n=>n.tagName==='button'&&n.textContent==='Lock comments')[0].fire('click');assert.equal(form.hidden,false);assert.equal(root.textContent.includes('<script>no()</script>'),false);
});
test('Direct publication disclosures replace approval promises in both editions',()=>{
  assert.ok(source.includes('will be published immediately'));
  assert.ok(source.includes("'Post comment', 'মন্তব্য প্রকাশ করুন'"));
  assert.ok(source.includes("'Your comment has been published.','আপনার মন্তব্য প্রকাশিত হয়েছে।'"));
  assert.equal(/after editorial approval|awaiting editorial approval|Submit for review/.test(source),false);
  const management=readFileSync(new URL('../assets/comments-review.js',import.meta.url),'utf8');
  assert.ok(management.includes("filter.value='approved'"));
  assert.ok(management.includes('hide or remove inappropriate comments'));
});
