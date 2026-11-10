(() => {
  'use strict';
  const root = document.querySelector('[data-comments-review]');
  if (!root) return;
  const bn = document.documentElement.lang === 'bn', t = (en,bengali) => bn ? bengali : en;
  let key = '', cursor = null, generation = 0;
  const el = (tag,text,attrs={}) => { const node=document.createElement(tag); node.textContent=text; Object.entries(attrs).forEach(([k,v])=>node.setAttribute(k,v)); return node; };
  const login=el('form',''), password=el('input','',{type:'password',id:'comments-editor-key',required:'',autocomplete:'off'});
  login.append(el('label',t('Editor key for comment management','মন্তব্য পর্যালোচনার সম্পাদক চাবি'),{for:'comments-editor-key'}),password,el('button',t('Unlock comments','মন্তব্য খুলুন'),{type:'submit',class:'button'}));
  const panel=el('div',''), filter=el('select','',{'aria-label':t('Comment status','মন্তব্যের অবস্থা')});
  [['approved','Published','প্রকাশিত'],['hidden','Hidden','লুকানো হয়েছে'],['rejected','Removed','সরানো হয়েছে'],['pending','Unpublished legacy comments','পুরনো অপ্রকাশিত মন্তব্য']].forEach(([value,en,bengali])=>filter.append(el('option',t(en,bengali),{value})));
  filter.value='approved';
  const lock=el('button',t('Lock comments','মন্তব্য তালাবদ্ধ করুন'),{type:'button',class:'button secondary'}), list=el('div',''), more=el('button',t('Load more','আরও দেখুন'),{type:'button',class:'button secondary'}), status=el('p','',{role:'status','aria-live':'polite'});
  panel.append(filter,lock,list,more); panel.hidden=true; more.hidden=true;
  root.append(el('h2',t('Manage page comments','পাতার মন্তব্য পর্যালোচনা'),{id:'comments-review-heading'}),el('p',t('Comments are published immediately. Check reports and hide or remove inappropriate comments. This sign-in is separate from the contribution desk.','মন্তব্য সঙ্গে সঙ্গে প্রকাশিত হয়। অভিযোগ দেখুন এবং অনুপযুক্ত মন্তব্য লুকান বা সরিয়ে দিন। এই সাইন ইন সহযোগিতা ডেস্ক থেকে পৃথক।')),login,panel,status);
  function reset() { generation++; key=''; password.value=''; list.replaceChildren(); panel.hidden=true; login.hidden=false; status.textContent=''; }
  async function api(path,options={}) {
    const response=await fetch('/api/comments/review'+path,{...options,credentials:'same-origin',cache:'no-store',headers:{Authorization:'Bearer '+key,'Content-Type':'application/json'}});
    if (!response.ok) { if(response.status===401 || response.status===403) reset(); const error=new Error('request');error.status=response.status;throw error; }
    return response.json();
  }
  function failure() { status.textContent=t('Could not load or save comments. Check your editor key and try again.','মন্তব্য পড়া বা সংরক্ষণ করা যায়নি। সম্পাদক চাবি দেখে আবার চেষ্টা করুন।'); }
  async function load(append=false) {
    const version=++generation; more.disabled=true;
    try {
      const data=await api('?status='+encodeURIComponent(filter.value)+(append&&cursor?'&cursor='+encodeURIComponent(cursor):''));
      if(version!==generation)return;
      if(!append)list.replaceChildren();
      if(!append&&!data.comments.length)list.append(el('p',t('No comments in this queue.','এই তালিকায় কোনো মন্তব্য নেই।')));
      for(const comment of data.comments) {
        const item=el('article','',{class:'comment-item'});
        item.append(el('strong',comment.name),el('p',comment.page+' · '+comment.created_at),el('p',comment.body,{class:'comment-body'}));
        if(comment.reports?.length) {
          item.append(el('h3',t('Reports','অভিযোগ')));
          comment.reports.forEach(report=>item.append(el('p',report.reason,{class:'comment-body'})));
        }
        for(const [action,en,bengali] of [['approved','Restore','পুনঃপ্রকাশ করুন'],['rejected','Remove','সরান'],['hidden','Hide','লুকান']]) {
          const control=el('button',t(en,bengali),{type:'button',class:'button secondary'});
          control.addEventListener('click',async()=>{
            if(!window.confirm(t('Apply this moderation decision?','এই সিদ্ধান্ত প্রয়োগ করবেন?')))return;
            const decisionGeneration = generation;
            item.querySelectorAll('button').forEach(button=>button.disabled=true);
            try {await api('/'+encodeURIComponent(comment.id),{method:'PATCH',body:JSON.stringify({status:action,note:'',version:comment.version})});if(decisionGeneration===generation)await load();}
            catch(error){if(decisionGeneration!==generation)return;if(error.status===409){await load().catch(failure);status.textContent=t('Another editor changed this comment. The queue has been refreshed.','অন্য সম্পাদক এই মন্তব্য পরিবর্তন করেছেন। তালিকা নতুন করে দেখানো হয়েছে।');}else{failure();item.querySelectorAll('button').forEach(button=>button.disabled=false);}}
          });item.append(control);
        }
        list.append(item);
      }
      cursor=data.next_cursor;more.hidden=!cursor;panel.hidden=false;login.hidden=true;password.value='';
    } finally {more.disabled=false;}
  }
  login.addEventListener('submit',async event=>{event.preventDefault();key=password.value.trim();if(!key)return;const button=login.querySelector('button');button.disabled=true;try{await load();}catch(_){failure();}finally{button.disabled=false;}});
  lock.addEventListener('click',reset); filter.addEventListener('change',()=>load().catch(failure));more.addEventListener('click',()=>load(true).catch(failure));
  window.addEventListener('pagehide',reset);
  fetch('/api/comments/config',{credentials:'same-origin',cache:'no-store'}).then(response=>response.ok?response.json():{}).then(config=>{root.hidden=!config.available;}).catch(()=>{});
})();
