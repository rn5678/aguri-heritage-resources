(() => {
  'use strict';
  const root = document.querySelector('[data-comments]');
  if (!root) return;
  const bn = document.documentElement.lang === 'bn';
  const t = (en, bengali) => bn ? bengali : en;
  const page = document.body.dataset.page;
  let config, session = {user: null}, cursor = null, busy = false, nonce, gisPromise;
  let ownIds = new Set(), ownCursor = null;
  const el = (tag, text, attrs = {}) => {
    const node = document.createElement(tag);
    if (text) node.textContent = text;
    Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, value));
    return node;
  };
  const button = (text, handler) => { const node = el('button', text, {type: 'button', class: 'button secondary'}); node.addEventListener('click', handler); return node; };
  const status = el('p', '', {role: 'status', 'aria-live': 'polite'});
  const account = el('div'), list = el('div'), mine = el('div'), form = el('form');
  const input = el('textarea', '', {id: 'comment-text', maxlength: '2000', required: '', rows: '4'});
  const agreement = el('input', '', {type: 'checkbox', required: ''});
  const consentLabel = el('label', '', {class: 'comment-consent'});
  consentLabel.append(agreement, document.createTextNode(t('I agree that my Google display name and comment may be published on this page after editorial approval. Do not include private information.', 'আমি সম্মত যে সম্পাদকের অনুমোদনের পরে আমার Google নাম ও মন্তব্য এই পাতায় প্রকাশিত হতে পারে। ব্যক্তিগত তথ্য দেবেন না।')));
  const submit = el('button', t('Submit for review', 'পর্যালোচনার জন্য জমা দিন'), {type:'submit', class:'button'});
  form.append(el('label', t('Your comment (up to 2,000 characters)', 'আপনার মন্তব্য (সর্বোচ্চ ২,০০০ অক্ষর)'), {for:'comment-text'}), input, consentLabel, submit);
  const more = button(t('Load more comments', 'আরও মন্তব্য দেখুন'), () => loadPublic(true).catch(showError));
  more.hidden = true;
  const moreMine = button(t('Load more of your comments', 'আপনার আরও মন্তব্য দেখুন'), () => loadMine(true).catch(showError));
  moreMine.hidden = true;
  root.append(el('h2', t('Comments', 'মন্তব্য'), {id:'comments-heading'}), el('p', t('Join the discussion in English or Bengali. Comments appear only after editorial approval. Please be respectful and cite sources where possible.', 'ইংরেজি বা বাংলায় আলোচনায় যোগ দিন। সম্পাদকের অনুমোদনের পরেই মন্তব্য প্রকাশিত হয়। শালীন ভাষা ব্যবহার করুন এবং সম্ভব হলে তথ্যসূত্র দিন।')), list, more, account, mine, moreMine, form, status);
  function showError(error) {
    status.textContent = error.status === 401 ? t('Your session has expired. Please sign in again. Your draft is still here.', 'আপনার সেশনের মেয়াদ শেষ। আবার সাইন ইন করুন। আপনার খসড়া এখানেই আছে।') : error.status === 429 ? t('Too many requests. Please wait a few minutes and try again.', 'অনেক অনুরোধ হয়েছে। কয়েক মিনিট পরে আবার চেষ্টা করুন।') : t('Comments are temporarily unavailable. Please try again later. Your draft has not been cleared.', 'মন্তব্য পরিষেবা এখন পাওয়া যাচ্ছে না। পরে চেষ্টা করুন। আপনার খসড়া মুছে যায়নি।');
    if (error.status === 401) { session = {user:null}; renderAccount(); mine.replaceChildren(); }
  }
  async function api(path, options = {}) {
    const controller = new AbortController(), timer = setTimeout(() => controller.abort(), 15000);
    try {
      const response = await fetch('/api/comments' + path, {credentials:'same-origin', cache:'no-store', ...options, signal:controller.signal,
        headers:{'Content-Type':'application/json', ...(session.csrf_token ? {'X-CSRF-Token':session.csrf_token} : {}), ...options.headers}});
      if (!response.ok) { const error = new Error('Comment request failed'); error.status = response.status; throw error; }
      return response.status === 204 ? {} : await response.json();
    } finally { clearTimeout(timer); }
  }
  function commentNode(comment, own = false) {
    const article = el('article', '', {class:'comment-item'});
    article.append(el('strong', comment.name), el('p', comment.body, {class:'comment-body'}));
    const date = new Date(comment.created_at);
    if (!Number.isNaN(date.getTime())) article.append(el('time', date.toLocaleDateString(bn ? 'bn-IN':'en-IN'), {datetime:date.toISOString()}));
    if (own) {
      const labels = {pending:t('Awaiting review','পর্যালোচনার অপেক্ষায়'), approved:t('Published','প্রকাশিত'), rejected:t('Not approved','অনুমোদিত হয়নি'), hidden:t('Hidden','লুকানো হয়েছে')};
      article.append(el('p', labels[comment.status] || t('Not published','প্রকাশিত নয়')));
      article.append(button(t('Delete my comment','আমার মন্তব্য মুছুন'), async event => {
        if (!window.confirm(t('Delete this comment?','এই মন্তব্য মুছবেন?'))) return;
        const control = event.currentTarget; control.disabled = true;
        try { await api('/' + encodeURIComponent(comment.id), {method:'DELETE'}); await refresh(); status.textContent = t('Comment deleted.','মন্তব্য মুছে ফেলা হয়েছে।'); }
        catch (error) { showError(error); control.disabled = false; }
      }));
    } else if (session.user && !ownIds.has(comment.id)) {
      article.append(button(t('Report','অভিযোগ করুন'), async event => {
        const reason = window.prompt(t('Why should an editor review this comment? (up to 500 characters)','কেন সম্পাদক এই মন্তব্যটি দেখবেন? (সর্বোচ্চ ৫০০ অক্ষর)'));
        if (!reason?.trim()) return;
        if (reason.length > 500) { status.textContent = t('Please limit your report to 500 characters.','অভিযোগ ৫০০ অক্ষরের মধ্যে লিখুন।'); return; }
        const control = event.currentTarget; control.disabled = true;
        try { await api('/' + encodeURIComponent(comment.id) + '/report', {method:'POST', body:JSON.stringify({reason:reason.trim()})}); status.textContent = t('Report sent to the editors.','অভিযোগ সম্পাদকদের কাছে পাঠানো হয়েছে।'); }
        catch (error) { showError(error); control.disabled = false; }
      }));
    }
    return article;
  }
  async function loadPublic(append = false) {
    more.disabled = true;
    try {
      const data = await api('?page=' + encodeURIComponent(page) + (append && cursor ? '&cursor=' + encodeURIComponent(cursor) : ''));
      if (!append) list.replaceChildren();
      for (const comment of data.comments) list.append(commentNode(comment));
      if (!append && !data.comments.length) list.append(el('p', t('No published comments yet.','এখনও কোনো মন্তব্য প্রকাশিত হয়নি।')));
      cursor = data.next_cursor; more.hidden = !cursor;
    } finally { more.disabled = false; }
  }
  async function loadMine(append = false) {
    if (!append) { mine.replaceChildren(); ownIds = new Set(); ownCursor = null; moreMine.hidden = true; }
    if (!session.user) return;
    moreMine.disabled = true;
    const owner = session.user;
    try {
      const data = await api('/mine?page=' + encodeURIComponent(page) + (append && ownCursor ? '&cursor=' + encodeURIComponent(ownCursor) : ''));
      if (session.user !== owner) return;
      data.comments.forEach(comment => ownIds.add(comment.id));
      if (!append && data.comments.length) mine.append(el('h3',t('Your comments','আপনার মন্তব্য')));
      data.comments.forEach(comment => mine.append(commentNode(comment, true)));
      ownCursor = data.next_cursor; moreMine.hidden = !ownCursor;
    } finally { moreMine.disabled = false; }
  }
  async function refresh() { await loadMine(); await loadPublic(); }
  function renderAccount() {
    account.replaceChildren(); form.hidden = !session.user;
    if (!session.user) { moreMine.hidden = true; ownIds = new Set(); ownCursor = null; }
    if (session.user) {
      account.append(el('p', t('Signed in as ','সাইন ইন করেছেন: ') + session.user.name));
      account.append(button(t('Sign out','সাইন আউট'), async event => {
        const control = event.currentTarget; control.disabled = true;
        try { await api('/auth/logout',{method:'POST'}); session = {user:null}; renderAccount(); mine.replaceChildren(); window.google?.accounts.id.disableAutoSelect(); await loadPublic(); }
        catch (error) { showError(error); control.disabled = false; }
      }));
    } else {
      account.append(el('p', t('Sign in with Google to comment. Google is contacted only when you choose to sign in. Your email address will not be published.', 'মন্তব্য করতে Google দিয়ে সাইন ইন করুন। আপনি সাইন ইন বেছে নিলেই Google-এর সঙ্গে যোগাযোগ হবে। আপনার ইমেল ঠিকানা প্রকাশিত হবে না।')));
      account.append(button(t('Sign in with Google','Google দিয়ে সাইন ইন করুন'), signIn));
    }
  }
  async function signIn(event) {
    const control = event.currentTarget; control.disabled = true;
    try {
      ({nonce} = await api('/auth/nonce'));
      if (!gisPromise) gisPromise = new Promise((resolve,reject) => {
        const script = el('script'); script.src = 'https://accounts.google.com/gsi/client'; script.async = true;
        const timer = setTimeout(() => { script.remove(); gisPromise = null; reject(new Error('Google timeout')); },15000);
        script.onload = () => {clearTimeout(timer); resolve();}; script.onerror = () => {clearTimeout(timer); script.remove(); gisPromise = null; reject(new Error('Google unavailable'));}; document.head.append(script);
      });
      await gisPromise;
      window.google.accounts.id.initialize({client_id:config.google_client_id, nonce, auto_select:false, callback:async response => {
        try { session = await api('/auth/google',{method:'POST',body:JSON.stringify({credential:response.credential,nonce})}); renderAccount(); status.textContent = t('Signed in. You can now submit a comment.','সাইন ইন হয়েছে। এখন মন্তব্য জমা দিতে পারেন।'); await refresh(); }
        catch(error) { showError(error); }
      }});
      const target = el('div'); account.append(target);
      window.google.accounts.id.renderButton(target, {type:'standard',theme:'outline',size:'large',locale:bn?'bn':'en'});
      control.hidden = true;
      status.textContent = t('Use the Google button to finish signing in.','সাইন ইন সম্পূর্ণ করতে Google বোতাম ব্যবহার করুন।');
    } catch(error) { showError(error); control.disabled = false; }
  }
  let draftId = null, draftBody = null;
  form.addEventListener('submit', async event => {
    event.preventDefault(); if (busy || !form.reportValidity()) return;
    const body = input.value.trim(); if (!body) { input.focus(); return; }
    busy = true; submit.disabled = true; input.disabled = true; agreement.disabled = true; form.setAttribute('aria-busy','true');
    if (body !== draftBody) { draftBody = body; draftId = crypto.randomUUID(); }
    try {
      await api('',{method:'POST',body:JSON.stringify({page,body,client_id:draftId,consent:agreement.checked,terms_version:config.terms_version})});
      input.value = ''; agreement.checked = false; draftId = null; draftBody = null;
      status.textContent = t('Thank you. Your comment is awaiting editorial approval and is not public yet.','ধন্যবাদ। আপনার মন্তব্য সম্পাদকের অনুমোদনের অপেক্ষায় আছে, এখনও প্রকাশিত হয়নি।');
      await loadMine();
    } catch(error) { showError(error); }
    finally { busy = false; submit.disabled = false; input.disabled = false; agreement.disabled = false; form.removeAttribute('aria-busy'); }
  });
  (async () => {
    try {
      config = await api('/config');
      if (!config.available) return;
      root.hidden = false; form.hidden = true;
      session = await api('/me'); renderAccount(); await refresh();
    } catch(error) { if (!root.hidden) showError(error); }
  })();
})();
