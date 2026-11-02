(() => {
  'use strict';
  const root = document.getElementById('review-app');
  if (!root) return;
  const bn = document.documentElement.lang === 'bn';
  const $ = id => document.getElementById(id);
  const text = (en, bengali) => bn ? bengali : en;
  const statuses = {
    received: text('Received', 'গৃহীত'), under_review: text('Under review', 'পর্যালোচনাধীন'),
    needs_information: text('Needs more information', 'আরও তথ্য প্রয়োজন'),
    approved: text('Approved', 'অনুমোদিত'), published: text('Published', 'প্রকাশিত'),
    declined: text('Declined', 'গ্রহণ করা হয়নি')
  };
  const types = {
    story: text('Story or memory', 'ইতিহাস বা স্মৃতি'), photo: text('Photograph', 'আলোকচিত্র'),
    document: text('Document', 'নথি'), correction: text('Suggested correction', 'সংশোধনের প্রস্তাব'),
    translation: text('Translation', 'অনুবাদ'), photograph: text('Photograph', 'আলোকচিত্র'),
    photograph_document: text('Photograph or document', 'আলোকচিত্র বা নথি'),
    rights: text('Private rights or permission enquiry', 'স্বত্ব বা অনুমতি সম্পর্কে ব্যক্তিগত অনুরোধ')
  };
  const credits = {
    yes: text('Name the contributor', 'সহযোগীর নাম প্রকাশ করুন'),
    no: text('Anonymous', 'নাম প্রকাশে অনিচ্ছুক'),
    '': text('Anonymous', 'নাম প্রকাশে অনিচ্ছুক'),
    named: text('Name the contributor', 'সহযোগীর নাম প্রকাশ করুন'),
    name: text('Name the contributor', 'সহযোগীর নাম প্রকাশ করুন'),
    public: text('Name the contributor', 'সহযোগীর নাম প্রকাশ করুন'),
    anonymous: text('Anonymous', 'নাম প্রকাশে অনিচ্ছুক')
  };
  // The editor key and private data exist only in this page's memory.
  let editorKey = '', session = 0, listRequest = 0, detailRequest = 0;
  let selectedId = null, detail = null, cursor = null, items = [], dirty = false;
  const activeRequests = new Set();
  const objectUrls = new Set();
  const isRightsEnquiry = record => record?.type === 'rights';
  const statusLabel = (status, rights = false) => rights && status === 'declined' ? text('Closed', 'বন্ধ') : statuses[status] || status;

  function el(tag, value, className) {
    const node = document.createElement(tag);
    if (value !== undefined && value !== null) node.textContent = String(value);
    if (className) node.className = className;
    return node;
  }
  function message(value, error = false) {
    const node = $('review-message');
    node.textContent = value || '';
    node.hidden = !value;
    node.dataset.error = String(error);
  }
  function formatDate(value) {
    if (!value) return text('Not recorded', 'নথিভুক্ত হয়নি');
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? String(value) : new Intl.DateTimeFormat(bn ? 'bn-IN' : 'en-IN', {
      dateStyle: 'medium', timeStyle: 'short'
    }).format(date);
  }
  const number = value => new Intl.NumberFormat(bn ? 'bn-IN' : 'en-IN').format(value);
  function safeLink(value, sameSite = false) {
    try {
      const url = new URL(value, location.origin);
      if (!/^https?:$/.test(url.protocol) || url.username || url.password) return null;
      if (sameSite && url.origin !== location.origin) return null;
      return url;
    } catch (_) { return null; }
  }
  function clearDetail() {
    detailRequest++;
    selectedId = null;
    detail = null;
    dirty = false;
    $('review-record').hidden = true;
    $('review-empty').hidden = false;
    $('review-decision').reset();
    setDecisionBusy(false);
    $('review-published-url').setCustomValidity('');
    ['review-record-type', 'review-record-title', 'review-record-reference', 'review-metadata',
      'review-description', 'review-files', 'review-replies', 'review-history', 'review-save-status', 'review-consent-warning']
      .forEach(id => $(id).replaceChildren());
    $('review-consent-warning').hidden = true;
    $('review-detail').removeAttribute('aria-busy');
  }
  function setDecisionBusy(busy) {
    for (const control of $('review-decision').elements) control.disabled = busy;
    if (isRightsEnquiry(detail?.submission)) $('review-published-url').disabled = true;
    $('review-decision').setAttribute('aria-busy', String(busy));
  }
  function lock(notice = '') {
    session++;
    listRequest++;
    editorKey = '';
    for (const controller of activeRequests) controller.abort();
    activeRequests.clear();
    for (const url of objectUrls) URL.revokeObjectURL(url);
    objectUrls.clear();
    items = [];
    cursor = null;
    clearDetail();
    $('review-login').reset();
    $('review-login').querySelector('button').disabled = false;
    $('review-filters').reset();
    $('review-list').replaceChildren();
    $('review-counts').replaceChildren();
    $('review-list-status').textContent = '';
    $('review-more').hidden = true;
    $('review-more').disabled = false;
    $('review-workspace').hidden = true;
    $('review-access').hidden = false;
    root.removeAttribute('aria-busy');
    message(notice);
  }
  async function request(path, options = {}, binary = false) {
    if (!editorKey) throw new Error('locked');
    const thisSession = session;
    const controller = new AbortController();
    activeRequests.add(controller);
    try {
      const response = await fetch(path, {
        ...options, headers: { ...(options.headers || {}), Authorization: `Bearer ${editorKey}` },
        cache: 'no-store', credentials: 'omit', redirect: 'error', signal: controller.signal
      });
      if (thisSession !== session) throw new DOMException('Aborted', 'AbortError');
      if (response.status === 401 || response.status === 403 || response.status === 503) {
        const unavailable = response.status === 503;
        lock();
        message(unavailable
          ? text('The review service is not configured or is temporarily unavailable. Ask the website administrator to check it, then try again.', 'পর্যালোচনার পরিষেবা প্রস্তুত নেই বা সাময়িকভাবে বন্ধ। ওয়েবসাইটের প্রশাসককে পরীক্ষা করতে বলুন, তারপর আবার চেষ্টা করুন।')
          : text('The editor key was not accepted. The workspace has been locked. Enter a valid key to continue.', 'সম্পাদকের প্রবেশসংকেত গ্রহণ করা হয়নি। কর্মক্ষেত্র বন্ধ করা হয়েছে। সঠিক প্রবেশসংকেত দিয়ে আবার চেষ্টা করুন।'), true);
        throw new Error('locked');
      }
      if (!response.ok) {
        const error = new Error('request');
        error.status = response.status;
        throw error;
      }
      return binary ? await response.blob() : await response.json();
    } finally { activeRequests.delete(controller); }
  }
  function reportError(error) {
    if (error.name === 'AbortError' || error.message === 'locked') return;
    const msg = error.status === 409
      ? text('Another editor changed this contribution. Your changes were not saved. Copy any notes you want to keep, then choose “Reload contribution” and review the latest version.', 'অন্য একজন সম্পাদক এই সহযোগিতাটি পরিবর্তন করেছেন। আপনার পরিবর্তন সংরক্ষিত হয়নি। প্রয়োজনীয় টীকা অনুলিপি করে রাখুন, তারপর “সহযোগিতাটি আবার লোড করুন” বেছে নিয়ে সর্বশেষ সংস্করণ দেখুন।')
      : error.status === 400 || error.status === 422
        ? text('The review could not be saved. Check the fields and ensure any published link points to an article already live on this website.', 'পর্যালোচনা সংরক্ষণ করা যায়নি। ঘরগুলি পরীক্ষা করুন এবং প্রকাশিত নিবন্ধের লিঙ্কটি এই ওয়েবসাইটে ইতিমধ্যে প্রকাশিত নিবন্ধের কি না দেখুন।')
        : error.status === 404
          ? text('This contribution or file could not be found. Refresh the inbox and try again.', 'এই সহযোগিতা বা ফাইলটি পাওয়া যায়নি। তালিকাটি আবার লোড করে চেষ্টা করুন।')
          : text('The service could not be reached. Check your connection and try again. No success has been confirmed.', 'পরিষেবার সঙ্গে যোগাযোগ করা যায়নি। সংযোগ পরীক্ষা করে আবার চেষ্টা করুন। কাজটি সফল হয়েছে বলে নিশ্চিত করা যাচ্ছে না।');
    message(msg, true);
  }
  function badge(status, rights = false) {
    const node = el('span', statusLabel(status, rights), 'review-badge');
    node.dataset.status = status;
    return node;
  }
  function renderCounts(counts) {
    $('review-counts').replaceChildren();
    for (const [status, label] of Object.entries(statuses)) {
      const button = el('button', null, 'review-count');
      button.type = 'button';
      button.setAttribute('aria-pressed', String($('review-status').value === status));
      button.append(el('strong', number(Number(counts[status]) || 0)), el('span', label));
      button.addEventListener('click', () => {
        $('review-status').value = status;
        loadList().catch(reportError);
      });
      $('review-counts').append(button);
    }
  }
  function renderItems() {
    const list = $('review-list');
    list.replaceChildren();
    for (const item of items) {
      const li = el('li');
      const button = el('button', null, 'review-item');
      button.type = 'button';
      button.setAttribute('aria-current', String(selectedId === item.id));
      button.append(el('span', types[item.type] || item.type, 'review-item-type'),
        el('span', item.title || text('Untitled contribution', 'শিরোনামহীন সহযোগিতা'), 'review-item-title'), badge(item.status, isRightsEnquiry(item)));
      button.append(el('span', `${item.contributor_name || text('Contributor', 'সহযোগী')} · ${formatDate(item.created_at)}`, 'review-item-meta'));
      button.addEventListener('click', () => openDetail(item.id).catch(reportError));
      li.append(button);
      list.append(li);
    }
    if (!items.length) list.append(el('li', text('No contributions match these filters. Try another status or search.', 'এই বাছাইয়ে কোনও সহযোগিতা পাওয়া যায়নি। অন্য অবস্থা বা শব্দ দিয়ে খুঁজুন।'), 'review-no-items'));
    $('review-list-status').textContent = text(`Showing ${number(items.length)} contributions`, `${number(items.length)}টি সহযোগিতা দেখানো হচ্ছে`);
    $('review-more').hidden = !cursor;
  }
  async function loadList(more = false) {
    const token = ++listRequest, thisSession = session;
    const params = new URLSearchParams();
    if ($('review-status').value) params.set('status', $('review-status').value);
    if ($('review-query').value.trim()) params.set('q', $('review-query').value.trim());
    if (more && cursor) params.set('before', cursor);
    $('review-list-status').textContent = text('Loading contributions…', 'সহযোগিতা লোড হচ্ছে…');
    $('review-more').disabled = true;
    try {
      const data = await request(`/api/review?${params}`);
      if (token !== listRequest || thisSession !== session) return;
      if (!Array.isArray(data.items)) throw new Error('format');
      const merged = more ? [...items, ...data.items] : data.items;
      items = [...new Map(merged.map(item => [item.id, item])).values()];
      cursor = data.next_cursor || null;
      renderCounts(data.counts || {});
      renderItems();
      $('review-access').hidden = true;
      $('review-workspace').hidden = false;
    } catch (error) {
      if (token === listRequest) $('review-list-status').textContent = text('The inbox could not be loaded. Apply the filters to try again.', 'তালিকা লোড করা যায়নি। আবার চেষ্টা করতে বাছাই করুন।');
      throw error;
    } finally {
      if (token === listRequest) $('review-more').disabled = false;
    }
  }
  function addMeta(label, value, link = false) {
    const row = el('div'), dt = el('dt', label), dd = el('dd');
    const display = value === null || value === undefined || value === '' ? text('Not provided', 'দেওয়া হয়নি') : String(value);
    const url = link && value ? safeLink(String(value)) : null;
    if (url) {
      const anchor = el('a', display);
      anchor.href = url.href;
      anchor.target = '_blank';
      anchor.rel = 'noopener noreferrer';
      dd.append(anchor);
    } else dd.textContent = display;
    row.append(dt, dd);
    $('review-metadata').append(row);
  }
  function openFileTab() {
    const preview = window.open('about:blank', '_blank');
    if (!preview) {
      message(text('Your browser blocked the new tab. Allow pop-ups for this website, then choose Open again.', 'ব্রাউজার নতুন ট্যাব খুলতে দেয়নি। এই ওয়েবসাইটের জন্য পপ-আপের অনুমতি দিয়ে আবার খুলুন।'), true);
      return null;
    }
    preview.opener = null;
    preview.document.body.textContent = text('Opening file…', 'ফাইল খোলা হচ্ছে…');
    return preview;
  }
  function openBlob(blob, name, preview = openFileTab()) {
    if (!preview) return;
    const type = blob.type.split(';')[0].toLowerCase();
    if (!['image/jpeg', 'image/png', 'image/webp', 'application/pdf', 'text/plain', 'application/json'].includes(type)) {
      preview.close();
      message(text('This file type cannot be opened safely in the browser.', 'এই ধরনের ফাইল ব্রাউজারে নিরাপদে খোলা যায় না।'), true);
      return;
    }
    const url = URL.createObjectURL(blob);
    objectUrls.add(url);
    try {
      preview.document.title = String(name || 'contribution');
      preview.location.replace(url);
    } catch (_) {
      preview.close();
      URL.revokeObjectURL(url);
      objectUrls.delete(url);
      message(text('The file could not be opened. Try Open again.', 'ফাইলটি খোলা যায়নি। আবার খুলুন।'), true);
      return;
    }
    const cleanup = setInterval(() => {
      if (preview.closed || !objectUrls.has(url)) {
        clearInterval(cleanup);
        if (objectUrls.delete(url)) URL.revokeObjectURL(url);
      }
    }, 1000);
  }
  function renderFiles(files, id) {
    const list = $('review-files');
    list.replaceChildren();
    for (const file of files) {
      const li = el('li'), button = el('button', text(`Open ${file.name}`, `${file.name} খুলুন`), 'review-file-button');
      button.type = 'button';
      button.addEventListener('click', async () => {
        // Reserve the tab during this user gesture, before authentication/fetch
        // yields. No editor key is placed in a URL or exposed to the new tab.
        const preview = openFileTab();
        if (!preview) return;
        const thisSession = session;
        button.disabled = true;
        try {
          const blob = await request(`/api/review/${encodeURIComponent(id)}/files/${encodeURIComponent(file.id)}`, {}, true);
          if (thisSession === session && !preview.closed) openBlob(blob, file.name, preview);
          else preview.close();
        } catch (error) { preview.close(); reportError(error); }
        finally { button.disabled = false; }
      });
      const size = Number(file.size) || 0;
      li.append(button, el('span', `${file.type || text('File', 'ফাইল')} · ${number(Math.ceil(size / 1024))} KB`, 'review-hint'));
      list.append(li);
    }
    if (!files.length) list.append(el('li', text('No files attached.', 'কোনও ফাইল সংযুক্ত নেই।'), 'review-hint'));
  }
  function renderTimeline(id, rows, replies = false) {
    const list = $(id);
    list.replaceChildren();
    for (const row of rows) {
      const li = el('li');
      if (!replies) li.append(badge(row.status, isRightsEnquiry(detail?.submission)));
      const time = el('time', formatDate(row.created_at));
      if (row.created_at) time.dateTime = row.created_at;
      li.append(time);
      if (replies ? row.message : row.note) li.append(el('p', replies ? row.message : row.note));
      if (!replies && row.internal_note) li.append(el('p', `${text('Internal note', 'অভ্যন্তরীণ টীকা')}: ${row.internal_note}`));
      list.append(li);
    }
    if (!rows.length) list.append(el('li', replies ? text('No replies yet.', 'এখনও কোনও উত্তর আসেনি।') : text('No review history yet.', 'এখনও পর্যালোচনার ইতিহাস নেই।'), 'review-hint'));
  }
  function renderDetail(data) {
    const s = data.submission;
    const rights = isRightsEnquiry(s);
    const consent = data.consent_info;
    detail = data;
    dirty = false;
    $('review-record-type').textContent = types[s.type] || s.type;
    $('review-record-title').textContent = s.title || text('Untitled contribution', 'শিরোনামহীন সহযোগিতা');
    $('review-record-reference').textContent = `${s.id} · ${text('Updated', 'সংশোধিত')} ${formatDate(s.updated_at || s.created_at)}`;
    $('review-metadata').replaceChildren();
    addMeta(text('Status', 'অবস্থা'), statusLabel(s.status, rights));
    addMeta(text('Contributor', 'সহযোগী'), s.contributor_name);
    addMeta(text('Private email', 'ব্যক্তিগত ইমেল'), s.email);
    if (!rights) addMeta(text('Public credit', 'প্রকাশ্যে নামোল্লেখ'), credits[s.credit || ''] || s.credit);
    addMeta(text('Place', 'স্থান'), s.place);
    addMeta(text('Date / period', 'তারিখ / সময়কাল'), s.date_text);
    addMeta(text('Language', 'ভাষা'), s.language === 'bn' ? 'বাংলা' : s.language === 'en' ? text('English', 'ইংরেজি') : s.language);
    addMeta(text('Source / evidence', 'উৎস / প্রমাণ'), s.source_url, true);
    addMeta(text('Related article', 'সংশ্লিষ্ট নিবন্ধ'), s.source_page, true);
    const recordedConsent = consent?.status === 'recorded';
    addMeta(text('Consent record', 'সম্মতির নথি'), recordedConsent ? text('Versioned acceptance recorded', 'সংস্করণসহ সম্মতি নথিভুক্ত') : text('Legacy submission: no versioned acceptance recorded', 'পুরনো জমা: সংস্করণসহ সম্মতি নথিভুক্ত নেই'));
    if (recordedConsent) {
      addMeta(text('Terms version', 'শর্তের সংস্করণ'), consent.terms_version);
      addMeta(text('Consent purpose', 'সম্মতির উদ্দেশ্য'), consent.purpose === 'rights-enquiry' ? text('Private enquiry handling only; no publication grant', 'শুধু ব্যক্তিগত অনুরোধ পরিচালনা; প্রকাশের অনুমতি নয়') : consent.purpose === 'contribution' ? text('Project review, publication, editing and translation; ownership retained', 'প্রকল্পের পর্যালোচনা, প্রকাশ, সম্পাদনা ও অনুবাদ; মালিকানা অক্ষুণ্ণ') : text('Unknown — verify before use', 'অজানা — ব্যবহারের আগে যাচাই করুন'));
      addMeta(text('Accepted at', 'সম্মতির সময়'), formatDate(consent.accepted_at));
      addMeta(text('Consent language', 'সম্মতির ভাষা'), consent.language === 'bn' ? 'বাংলা' : consent.language === 'en' ? text('English', 'ইংরেজি') : consent.language);
    }
    const warning = $('review-consent-warning');
    warning.hidden = recordedConsent && !rights;
    warning.textContent = rights ? text('Private rights enquiry. The enquiry, evidence and replies are not licensed for publication. Record the outcome in the private message and close the enquiry when handling is complete.', 'স্বত্ব সম্পর্কে ব্যক্তিগত অনুরোধ। অনুরোধ, প্রমাণ ও উত্তর প্রকাশের অনুমতি নেই। ব্যক্তিগত বার্তায় ফলাফল লিখুন এবং কাজ সম্পূর্ণ হলে অনুরোধ বন্ধ করুন।') : !recordedConsent ? text('This older submission has no recorded acceptance of the current Contributor Terms. Do not assume a publication, editing or translation grant. Verify and document the necessary permission before publication; a private reply alone does not accept these terms.', 'এই পুরনো জমায় বর্তমান সহযোগিতার শর্তাবলি গ্রহণের নথি নেই। প্রকাশ, সম্পাদনা বা অনুবাদের অনুমতি আছে ধরে নেবেন না। প্রকাশের আগে প্রয়োজনীয় অনুমতি যাচাই ও নথিভুক্ত করুন; শুধু ব্যক্তিগত উত্তর দেওয়া শর্ত গ্রহণ নয়।') : '';
    if ((data.attachments || []).length) addMeta(text('File permission', 'ফাইলের অনুমতি'), s.attachment_rights === 'yes' ? (rights ? text('Evidence for private enquiry handling only', 'শুধু ব্যক্তিগত অনুরোধ পরিচালনার প্রমাণ') : text('Contributor confirmed review and publication permission; verify third-party rights', 'সহযোগী পর্যালোচনা ও প্রকাশের অনুমতি নিশ্চিত করেছেন; তৃতীয় পক্ষের স্বত্ব যাচাই করুন')) : text('Not confirmed — verify permitted use', 'নিশ্চিত নয় — অনুমোদিত ব্যবহার যাচাই করুন'));
    addMeta(text('Received', 'জমা পড়েছে'), formatDate(s.created_at));
    if (!rights && s.published_url) addMeta(text('Published article', 'প্রকাশিত নিবন্ধ'), s.published_url, true);
    $('review-description').textContent = s.description || text('No description provided.', 'কোনও বিবরণ দেওয়া হয়নি।');
    renderFiles(data.attachments || [], s.id);
    renderTimeline('review-replies', data.replies || [], true);
    renderTimeline('review-history', data.history || []);
    for (const option of $('review-decision-status').options) {
      option.hidden = option.disabled = rights && ['approved', 'published'].includes(option.value);
      option.textContent = statusLabel(option.value, rights);
    }
    $('review-decision-status').value = s.status;
    $('review-public-note').value = s.public_note || '';
    $('review-internal-note').value = s.internal_note || '';
    $('review-publication-controls').hidden = rights;
    $('review-published-url').value = rights ? '' : s.published_url || '';
    $('review-published-url').setCustomValidity('');
    $('review-save-status').textContent = '';
    setDecisionBusy(false);
    $('review-empty').hidden = true;
    $('review-record').hidden = false;
  }
  function discardChanges() {
    return !dirty || window.confirm(text('Discard your unsaved review changes?', 'সংরক্ষিত না হওয়া পর্যালোচনার পরিবর্তনগুলি বাতিল করবেন?'));
  }
  async function openDetail(id, reload = false) {
    if (!reload && id === selectedId && detail) return;
    if (!discardChanges()) return;
    clearDetail();
    selectedId = id;
    const token = ++detailRequest, thisSession = session;
    $('review-detail').setAttribute('aria-busy', 'true');
    message(text('Loading the contribution…', 'সহযোগিতাটি লোড হচ্ছে…'));
    renderItems();
    try {
      const data = await request(`/api/review/${encodeURIComponent(id)}`);
      if (token !== detailRequest || thisSession !== session) return;
      if (!data.submission || data.submission.id !== id) throw new Error('format');
      renderDetail(data);
      message('');
      $('review-record-title').focus({preventScroll: true});
      if (matchMedia('(max-width: 720px)').matches) $('review-detail').scrollIntoView({behavior: 'auto', block: 'start'});
    } finally { if (token === detailRequest) $('review-detail').removeAttribute('aria-busy'); }
  }
  $('review-login').addEventListener('submit', async event => {
    event.preventDefault();
    const entered = $('editor-key').value.trim();
    if (!entered) return;
    lock();
    editorKey = entered;
    const thisSession = session;
    $('review-login').querySelector('button').disabled = true;
    root.setAttribute('aria-busy', 'true');
    message(text('Opening the private inbox…', 'ব্যক্তিগত তালিকা খোলা হচ্ছে…'));
    try {
      await loadList();
      if (thisSession === session) message('');
    } catch (error) {
      if (error.message !== 'locked' && error.name !== 'AbortError' && thisSession === session) lock();
      reportError(error);
    } finally {
      if (thisSession === session) {
        $('review-login').querySelector('button').disabled = false;
        root.removeAttribute('aria-busy');
      }
    }
  });
  $('review-lock').addEventListener('click', () => {
    if (!discardChanges()) return;
    lock(text('Workspace locked. Private details have been cleared from this page.', 'কর্মক্ষেত্র বন্ধ হয়েছে। এই পাতা থেকে ব্যক্তিগত তথ্য মুছে দেওয়া হয়েছে।'));
    $('editor-key').focus();
  });
  $('review-filters').addEventListener('submit', event => {
    event.preventDefault();
    message('');
    loadList().catch(reportError);
  });
  $('review-more').addEventListener('click', () => loadList(true).catch(reportError));
  $('review-reload').addEventListener('click', () => { if (selectedId) openDetail(selectedId, true).catch(reportError); });
  $('review-export').addEventListener('click', () => {
    if (!editorKey || !detail) return;
    openBlob(new Blob([JSON.stringify({exported_at: new Date().toISOString(), ...detail}, null, 2)], {type: 'application/json'}), `aguri-contribution-${detail.submission.id}.json`);
  });
  $('review-decision').addEventListener('input', () => {
    dirty = true;
    $('review-published-url').setCustomValidity('');
    $('review-save-status').textContent = text('Unsaved changes', 'পরিবর্তন এখনও সংরক্ষিত হয়নি');
  });
  $('review-decision').addEventListener('submit', async event => {
    event.preventDefault();
    if (!detail || !editorKey || $('review-save').disabled) return;
    const status = $('review-decision-status').value;
    const rights = isRightsEnquiry(detail.submission);
    if (rights && ['approved', 'published'].includes(status)) return;
    const published = rights ? '' : $('review-published-url').value.trim();
    const publishedLink = published ? safeLink(published, true) : null;
    if ((status === 'published' && !published) || (published && (!publishedLink || publishedLink.search || publishedLink.hash))) {
      $('review-published-url').setCustomValidity(text('Enter an article link from this website, without a query or section anchor (for example /history.html).', 'এই ওয়েবসাইটের নিবন্ধের লিঙ্ক লিখুন; অতিরিক্ত অনুসন্ধান বা অংশের চিহ্ন ছাড়া (যেমন /bn/history.html)।'));
      $('review-published-url').reportValidity();
      return;
    }
    const id = selectedId, token = detailRequest, thisSession = session;
    const payload = {status, public_note: $('review-public-note').value.trim(), internal_note: $('review-internal-note').value.trim(), published_url: published, version: detail.submission.version};
    setDecisionBusy(true);
    $('review-save-status').textContent = text('Saving…', 'সংরক্ষণ হচ্ছে…');
    message('');
    try {
      await request(`/api/review/${encodeURIComponent(id)}`, {method: 'PATCH', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)});
      if (thisSession !== session) return;
      if (token === detailRequest && selectedId === id) {
        dirty = false;
        const fresh = await request(`/api/review/${encodeURIComponent(id)}`);
        if (thisSession !== session) return;
        if (token === detailRequest && selectedId === id) {
          renderDetail(fresh);
          $('review-save-status').textContent = text('Review saved.', 'পর্যালোচনা সংরক্ষিত হয়েছে।');
        }
      }
      await loadList();
    } catch (error) {
      if (thisSession === session && token === detailRequest) $('review-save-status').textContent = text('Please check the message above.', 'উপরের বার্তাটি দেখুন।');
      reportError(error);
    } finally {
      if (thisSession === session && token === detailRequest) setDecisionBusy(false);
    }
  });
  // A back/forward-cache restore must never reopen an authenticated workspace.
  window.addEventListener('pagehide', () => lock());
  window.addEventListener('pageshow', event => { if (event.persisted) lock(); });
  window.addEventListener('beforeunload', event => {
    if (dirty) { event.preventDefault(); event.returnValue = ''; }
  });
  // Keep the password form unavailable when JavaScript is disabled, so a key
  // can never fall back to a native form submission or appear in a URL.
  $('review-login').hidden = false;
})();
