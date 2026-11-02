(() => {
  'use strict';
  if (!document.querySelector('[data-contribution-page]')) return;
  const bn = document.documentElement.lang === 'bn';
  const words = (en, bengali) => bn ? bengali : en;
  const $ = id => document.getElementById(id);
  const form = $('contribution-form');
  const send = $('contribution-send');
  const files = $('contribution-files');
  const error = $('contribution-error');
  const connection = $('contribution-connection');
  const receiptPanel = $('contribution-receipt');
  const initialReplyText = $('reply-send').textContent;
  const publicationDescriptionHelp = $('description-help').textContent;
  const publicationSourceHelp = $('source-help').textContent;
  const publicationAttachmentConsent = $('attachment-consent').textContent;
  const validStatuses = {
    received: words('Received', 'পাওয়া গেছে'),
    under_review: words('Under review', 'পর্যালোচনা চলছে'),
    needs_information: words('More information needed', 'আরও তথ্য প্রয়োজন'),
    approved: words('Approved for publication', 'প্রকাশের জন্য অনুমোদিত'),
    published: words('Published', 'প্রকাশিত'),
    declined: words('Not accepted for publication', 'প্রকাশের জন্য গৃহীত হয়নি')
  };
  let available = false;
  let checking = false;
  let sending = false;
  let replying = false;
  let loadingReceipt = false;
  let dirty = false;
  let replyDirty = false;
  let clientId = null;
  let receipt = null;
  let maxFiles = 3;
  let maxBytes = 1500000;
  let challengeKey = null;
  let challengeToken = '';
  let challengeWidget = null;
  let challengePromise = null;

  const isRightsEnquiry = () => form.elements.namedItem('type').value === 'rights';
  const sendLabel = () => isRightsEnquiry() ? words('Send private enquiry', 'ব্যক্তিগত অনুরোধ পাঠান') : words('Send for review', 'পর্যালোচনার জন্য পাঠান');

  function updateContributionType(resetConsent = false) {
    const rights = isRightsEnquiry();
    if (resetConsent) {
      $('contribution-consent').checked = false;
      $('contribution-rights').checked = false;
      clientId = null;
    }
    $('consent-publication').hidden = rights;
    $('consent-rights').hidden = !rights;
    $('credit-label').hidden = rights;
    const credit = form.elements.namedItem('credit');
    credit.disabled = rights;
    if (rights) credit.checked = false;
    $('contribution-name').setCustomValidity('');
    $('contribution-form-heading').textContent = rights ? words('Send a private rights enquiry', 'স্বত্ব সম্পর্কে ব্যক্তিগত অনুরোধ পাঠান') : words('Add your contribution', 'আপনার অবদান জানান');
    $('contribution-title').placeholder = rights ? words('For example, permission to reuse a photograph', 'যেমন, একটি ছবি পুনর্ব্যবহারের অনুমতি') : words('For example, our village school in the 1950s', 'যেমন, পঞ্চাশের দশকে আমাদের গ্রামের বিদ্যালয়');
    $('description-help').textContent = rights ? words('Identify the page or item, explain your connection to it and what permission or change you request. Provide relevant evidence; you do not have to own material you are reporting. Your enquiry and evidence are for private review.', 'পাতা বা উপকরণটি চিহ্নিত করুন, এর সঙ্গে আপনার সম্পর্ক এবং কী অনুমতি বা পরিবর্তন চান তা জানান। প্রাসঙ্গিক প্রমাণ দিন; যে উপকরণ সম্পর্কে অভিযোগ করছেন তার মালিক হওয়া আবশ্যক নয়। অনুরোধ ও প্রমাণ গোপনে পর্যালোচনার জন্য।') : publicationDescriptionHelp;
    $('source-help').textContent = rights ? words('Link to the item or relevant evidence. Editors will use it privately to assess your enquiry; this does not give permission to republish it.', 'উপকরণ বা প্রাসঙ্গিক প্রমাণের লিঙ্ক দিন। সম্পাদক তা গোপনে অনুরোধ যাচাই করতে ব্যবহার করবেন; এতে পুনঃপ্রকাশের অনুমতি দেওয়া হয় না।') : publicationSourceHelp;
    $('attachment-consent').textContent = rights ? words('I am providing these files as evidence for private handling of this enquiry. This is not permission to publish them, and I have removed unrelated private details.', 'এই অনুরোধ গোপনে পরিচালনার প্রমাণ হিসেবে ফাইলগুলি দিচ্ছি। এতে প্রকাশের অনুমতি দেওয়া হচ্ছে না এবং অপ্রাসঙ্গিক ব্যক্তিগত তথ্য সরিয়েছি।') : publicationAttachmentConsent;
    if (!sending) send.textContent = sendLabel();
  }

  function setError(message) {
    error.textContent = message;
    error.hidden = !message;
    if (message) error.focus();
  }

  function setAvailability(enabled, message) {
    available = enabled;
    connection.hidden = enabled;
    $('connection-message').textContent = message || '';
    $('connection-retry').hidden = enabled || checking;
    send.disabled = !enabled || sending || (Boolean(challengeKey) && !challengeToken);
    $('reply-send').disabled = !enabled || !receipt || replying || !receipt.loaded;
  }

  function notConnected() {
    if (receipt) return words('The contribution service is not connected right now. Keep your private tracking link and check again later.', 'অবদান জমা দেওয়ার পরিষেবায় এখন সংযোগ নেই। ব্যক্তিগত অগ্রগতির লিঙ্কটি রেখে পরে আবার দেখুন।');
    return words('Online contributions are not connected right now. You can keep writing and open a draft. Nothing is sent until the service is available and you choose “Send for review”.', 'অনলাইনে অবদান জমা দেওয়ার সংযোগ এখন চালু নেই। লিখতে থাকুন এবং খসড়া খুলুন। পরিষেবা চালু হলে “পর্যালোচনার জন্য পাঠান” বেছে নেওয়ার আগে কিছু পাঠানো হবে না।');
  }

  async function request(path, options = {}) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), options.method === 'POST' ? 45000 : 15000);
    try {
      const response = await fetch(path, { cache: 'no-store', credentials: 'omit', redirect: 'error', referrerPolicy: 'no-referrer', ...options, signal: controller.signal });
      const contentType = response.headers.get('content-type') || '';
      const data = contentType.includes('application/json') ? await response.json() : null;
      if (!response.ok || !data || typeof data !== 'object') {
        const failure = new Error('Request failed');
        failure.status = response.status;
        throw failure;
      }
      return data;
    } finally {
      clearTimeout(timer);
    }
  }

  function safeLocalPage(value) {
    if (!value || value.length > 2000 || /^[a-z][a-z0-9+.-]*:/i.test(value) || value.startsWith('//') || /[\\\u0000-\u001f]/.test(value)) return null;
    try {
      const root = new URL(bn ? '../' : './', location.href);
      const result = new URL(value, root);
      if (result.origin !== location.origin || !['http:', 'https:', 'file:'].includes(result.protocol)) return null;
      return result;
    } catch (_) {
      return null;
    }
  }

  function publishedURL(value) {
    if (typeof value !== 'string' || !value.trim() || value.length > 2000) return null;
    try {
      const url = new URL(value, location.href);
      return ['https:', 'http:'].includes(url.protocol) && url.origin === location.origin ? url.href : null;
    } catch (_) {
      return null;
    }
  }

  function prefill() {
    const query = new URLSearchParams(location.search);
    const type = query.get('type');
    if (['story', 'document', 'correction', 'rights'].includes(type)) form.elements.namedItem('type').value = type;
    const page = safeLocalPage(query.get('page'));
    if (!page) return;
    const title = (query.get('title') || page.pathname.split('/').pop() || words('Source page', 'মূল পাতা')).slice(0, 160);
    form.elements.namedItem('source_page').value = page.pathname + page.search + page.hash;
    $('context-page').href = page.href;
    $('context-page').textContent = title;
    $('contribution-context').hidden = false;
    if (type === 'correction') $('contribution-title').value = (words('Correction: ', 'সংশোধন: ') + title).slice(0, 160);
    if (type === 'rights') $('contribution-title').value = (words('Rights enquiry: ', 'স্বত্ব সম্পর্কে অনুরোধ: ') + title).slice(0, 160);
    const volume = (query.get('volume') || '').slice(0, 100);
    const scan = (query.get('scan') || '').slice(0, 100);
    form.elements.namedItem('volume').value = volume;
    form.elements.namedItem('scan').value = scan;
    if (volume || scan) {
      $('context-scan').textContent = [volume ? words('Volume: ', 'খণ্ড: ') + volume : '', scan ? words('Scan: ', 'স্ক্যান: ') + scan : ''].filter(Boolean).join(' · ');
      $('context-scan').hidden = false;
    }
  }

  function uuid() {
    if (crypto.randomUUID) return crypto.randomUUID();
    const bytes = crypto.getRandomValues(new Uint8Array(16));
    bytes[6] = (bytes[6] & 15) | 64;
    bytes[8] = (bytes[8] & 63) | 128;
    const hex = [...bytes].map(byte => byte.toString(16).padStart(2, '0')).join('');
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
  }

  function openJSON(name, data) {
    const preview = window.open('about:blank', '_blank');
    if (!preview) {
      setError(words('Your browser blocked the new tab. Allow pop-ups for this website, then choose Open again.', 'ব্রাউজার নতুন ট্যাব খুলতে দেয়নি। এই ওয়েবসাইটের জন্য পপ-আপের অনুমতি দিয়ে আবার খুলুন।'));
      return;
    }
    preview.opener = null;
    const blob = new Blob([JSON.stringify(data, null, 2) + '\n'], { type: 'application/json;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    try {
      preview.document.title = name;
      preview.location.replace(url);
      setError('');
    } catch (_) {
      preview.close();
      URL.revokeObjectURL(url);
      setError(words('The file could not be opened. Your information is still here; try Open again.', 'ফাইলটি খোলা যায়নি। আপনার তথ্য এখানেই আছে; আবার খুলুন।'));
      return;
    }
    // Keep the local file available for reading, reloading and saving while its
    // tab remains open. It never leaves this browser.
    const cleanup = setInterval(() => {
      if (preview.closed) { URL.revokeObjectURL(url); clearInterval(cleanup); }
    }, 1000);
  }

  function formDraft() {
    const data = Object.fromEntries([...new FormData(form)].filter(([key, value]) => typeof value === 'string' && !['website', 'cf-turnstile-response', 'turnstile_token'].includes(key)));
    data.attachments = [...files.files].map(file => ({ name: file.name, size: file.size, type: file.type }));
    data.consent = $('contribution-consent').checked ? 'yes' : 'no';
    data.attachment_rights = files.files.length ? ($('contribution-rights').checked ? 'yes' : 'no') : 'not_applicable';
    data.consent_purpose = isRightsEnquiry() ? 'rights-enquiry' : 'contribution';
    data.terms_url = new URL(isRightsEnquiry() ? 'rights.html#permission' : 'contributor-terms.html', location.href).href;
    data.reuse_policy_url = new URL('rights.html', location.href).href;
    return { draft: true, saved_at: new Date().toISOString(), note: words('Not submitted. Opening this draft does not accept the terms or grant permission. Consent fields record only your current draft choices. Attachment contents are not included.', 'জমা পড়েনি। এই খসড়া খুললে শর্ত গ্রহণ বা অনুমতি দেওয়া হয় না। সম্মতির ঘরগুলি শুধু খসড়ায় বর্তমান নির্বাচন দেখায়। সংযুক্ত ফাইলের বিষয়বস্তু এতে নেই।'), ...data };
  }

  function validateFiles() {
    const list = [...files.files];
    let message = '';
    if (list.length > maxFiles) message = words(`Choose up to ${maxFiles} files. Remove the selection and choose again.`, `সর্বাধিক ${maxFiles.toLocaleString('bn-IN')}টি ফাইল বাছুন। নির্বাচন সরিয়ে আবার বাছুন।`);
    for (const file of list) {
      const extension = file.name.split('.').pop().toLowerCase();
      if (!['jpg', 'jpeg', 'png', 'webp', 'pdf', 'txt'].includes(extension)) message = words('Choose JPEG, PNG, WebP, PDF or TXT files only.', 'শুধু JPEG, PNG, WebP, PDF বা TXT ফাইল বাছুন।');
      if (file.size > maxBytes) message = words(`Each file must be ${(maxBytes / 1000000).toLocaleString('en-IN')} MB or smaller. Add a source link for larger files.`, `প্রতিটি ফাইল ${(maxBytes / 1000000).toLocaleString('bn-IN')} MB বা তার কম হতে হবে। বড় ফাইলের জন্য উৎসের লিঙ্ক দিন।`);
      if (file.size === 0) message = words('An attached file is empty. Please remove it and choose the original file.', 'একটি সংযুক্ত ফাইল খালি। সেটি সরিয়ে মূল ফাইলটি বাছুন।');
    }
    files.setCustomValidity(message);
    return message;
  }

  function updateFiles() {
    const list = [...files.files];
    const holder = $('file-list');
    holder.replaceChildren();
    for (const file of list) {
      const item = document.createElement('li');
      item.textContent = `${file.name} · ${(file.size / 1000000).toLocaleString(bn ? 'bn-IN' : 'en-IN', { maximumFractionDigits: 2 })} MB`;
      holder.append(item);
    }
    holder.hidden = !list.length;
    $('clear-files').hidden = !list.length;
    $('rights-label').hidden = !list.length;
    $('contribution-rights').required = Boolean(list.length);
    if (!list.length) $('contribution-rights').checked = false;
    const message = validateFiles();
    if (message) setError(message);
    else setError('');
  }

  function validateText() {
    for (const id of ['contribution-title', 'contribution-description']) {
      const input = $(id);
      input.setCustomValidity(input.value.trim() ? '' : words('Please enter some text.', 'অনুগ্রহ করে কিছু লিখুন।'));
    }
    const source = $('contribution-source');
    source.setCustomValidity('');
    if (source.value.trim()) {
      try {
        const url = new URL(source.value.trim());
        if (!['https:', 'http:'].includes(url.protocol) || url.username || url.password) throw new Error('Invalid URL');
      } catch (_) {
        source.setCustomValidity(words('Use a complete http:// or https:// link without a password.', 'পাসওয়ার্ড ছাড়া সম্পূর্ণ http:// বা https:// লিঙ্ক দিন।'));
      }
    }
    const credit = form.elements.namedItem('credit');
    const name = $('contribution-name');
    name.setCustomValidity(credit.checked && !name.value.trim() ? words('Enter the name you would like credited, or leave the credit box unchecked.', 'যে নামে স্বীকৃতি চান তা লিখুন, অথবা স্বীকৃতির ঘরটি ফাঁকা রাখুন।') : '');
  }

  function dateLabel(value) {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? words('Not available', 'পাওয়া যায়নি') : new Intl.DateTimeFormat(bn ? 'bn-IN' : 'en-IN', { dateStyle: 'medium', timeStyle: 'short' }).format(date);
  }

  function trackingLink() {
    const url = new URL(location.href);
    url.search = '';
    url.hash = `receipt=${receipt.id}.${receipt.token}`;
    return url.href;
  }

  function showReceipt(data, isNew = false) {
    receipt = { ...receipt, ...data };
    const rights = receipt.type === 'rights';
    $('contribution-workspace').hidden = true;
    $('contribution-intro').hidden = true;
    receiptPanel.hidden = false;
    $('receipt-eyebrow').textContent = rights ? words('Your private enquiry', 'আপনার ব্যক্তিগত অনুরোধ') : words('Your contribution', 'আপনার অবদান');
    $('receipt-heading').textContent = rights ? (isNew ? words('Private enquiry received', 'ব্যক্তিগত অনুরোধ পাওয়া গেছে') : words('Your enquiry’s progress', 'আপনার অনুরোধের অগ্রগতি')) : (isNew ? words('Contribution received', 'অবদান পাওয়া গেছে') : words('Your contribution’s progress', 'আপনার অবদানের অগ্রগতি'));
    $('receipt-intro').textContent = rights ? words('An editor will privately review your rights or permission enquiry. Receipt does not mean that permission has been granted or a removal request accepted. Check this private link for the response.', 'সম্পাদক আপনার স্বত্ব বা অনুমতি সংক্রান্ত অনুরোধ গোপনে পর্যালোচনা করবেন। প্রাপ্তিস্বীকারের অর্থ অনুমতি দেওয়া বা সরানোর অনুরোধ মেনে নেওয়া নয়। উত্তরের জন্য এই ব্যক্তিগত লিঙ্ক দেখুন।') : (isNew ? words('Thank you for adding to the collection. An editor will review your submission.', 'সংগ্রহ সমৃদ্ধ করার জন্য ধন্যবাদ। সম্পাদক আপনার অবদান পর্যালোচনা করবেন।') : words('Check the latest review status below. You can send additional information to the editors from this page.', 'নিচে পর্যালোচনার সর্বশেষ অবস্থা দেখুন। এই পাতা থেকে সম্পাদকদের অতিরিক্ত তথ্য পাঠাতে পারেন।'));
    $('receipt-id').textContent = receipt.id;
    $('receipt-title').textContent = receipt.title || words('Loading…', 'লোড হচ্ছে…');
    $('receipt-status').textContent = rights && receipt.status === 'declined' ? words('Closed', 'বন্ধ') : validStatuses[receipt.status] || words('Status not loaded', 'অবস্থা লোড হয়নি');
    $('receipt-status').dataset.status = Object.hasOwn(validStatuses, receipt.status || '') ? receipt.status : '';
    $('receipt-updated').textContent = receipt.updated_at || receipt.created_at ? dateLabel(receipt.updated_at || receipt.created_at) : words('Not available', 'পাওয়া যায়নি');
    $('receipt-link').value = trackingLink();
    $('receipt-note').textContent = typeof receipt.public_note === 'string' ? receipt.public_note : '';
    $('receipt-note-panel').hidden = !$('receipt-note').textContent;
    const published = !rights && receipt.status === 'published' ? publishedURL(receipt.published_url) : null;
    $('receipt-publication').hidden = !published;
    if (published) $('receipt-published-link').href = published;
    $('reply-send').disabled = !available || !receipt.loaded || replying;
  }

  function receiptCredentials() {
    const fragment = new URLSearchParams(location.hash.slice(1));
    const value = fragment.get('receipt');
    if (!value) return null;
    const match = /^([A-Za-z0-9_-]{6,100})\.([A-Za-z0-9_-]{20,180})$/.exec(value);
    return match ? { id: match[1], token: match[2], loaded: false } : null;
  }

  async function refreshReceipt(focus = false) {
    if (!receipt || loadingReceipt) return;
    loadingReceipt = true;
    $('refresh-receipt').disabled = true;
    $('receipt-action-status').textContent = words('Checking the latest status…', 'সর্বশেষ অবস্থা দেখা হচ্ছে…');
    try {
      const data = await request(`/api/contributions/${encodeURIComponent(receipt.id)}`, { headers: { Authorization: `Bearer ${receipt.token}` } });
      if (data.id !== receipt.id || !Object.hasOwn(validStatuses, data.status)) throw new Error('Invalid receipt');
      showReceipt({ ...data, loaded: true });
      $('receipt-action-status').textContent = words('Status updated.', 'অবস্থা হালনাগাদ হয়েছে।');
      setError('');
      if (focus) $('receipt-heading').focus();
    } catch (failure) {
      $('receipt-action-status').textContent = '';
      const denied = [401, 403, 404].includes(failure.status);
      setError(denied ? words('This tracking link could not be verified. Check that you copied the complete private link from your receipt.', 'এই অগ্রগতির লিঙ্ক যাচাই করা যায়নি। প্রাপ্তিস্বীকার থেকে সম্পূর্ণ ব্যক্তিগত লিঙ্কটি কপি করেছেন কি না দেখুন।') : words('We could not load the latest status. Keep your private link and try “Refresh status” when the service is available.', 'সর্বশেষ অবস্থা লোড করা যায়নি। ব্যক্তিগত লিঙ্কটি রাখুন এবং পরিষেবা চালু হলে “সর্বশেষ অবস্থা দেখুন” বেছে নিন।'));
    } finally {
      loadingReceipt = false;
      $('refresh-receipt').disabled = false;
    }
  }

  async function setupChallenge(key) {
    if (!key) return;
    if (challengeWidget !== null) {
      if (!challengeToken && window.turnstile) window.turnstile.reset(challengeWidget);
      return;
    }
    if (!challengePromise) {
      challengePromise = new Promise((resolve, reject) => {
        if (window.turnstile) { resolve(); return; }
        const script = document.createElement('script');
        script.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit';
        script.async = true;
        const timer = setTimeout(() => reject(new Error('Verification timed out')), 15000);
        script.onload = () => { clearTimeout(timer); resolve(); };
        script.onerror = () => { clearTimeout(timer); reject(new Error('Verification unavailable')); };
        document.head.append(script);
      }).catch(failure => { challengePromise = null; throw failure; });
    }
    try {
      await challengePromise;
      if (!window.turnstile || challengeWidget !== null) return;
      challengeWidget = window.turnstile.render($('contribution-challenge'), {
        sitekey: key,
        language: bn ? 'bn' : 'en',
        callback: token => { challengeToken = token; send.disabled = !available || sending; },
        'expired-callback': () => { challengeToken = ''; send.disabled = true; },
        'error-callback': () => { challengeToken = ''; setAvailability(false, notConnected()); setError(words('The verification check could not load. Check your connection and try again. Your draft is still here.', 'যাচাইয়ের ধাপ লোড হয়নি। সংযোগ দেখে আবার চেষ্টা করুন। আপনার খসড়া এখানেই আছে।')); }
      });
    } catch (_) {
      setError(words('The verification check could not load. Check your connection and use “Check again”. Your draft is still here.', 'যাচাইয়ের ধাপ লোড হয়নি। সংযোগ দেখে “আবার দেখুন” বেছে নিন। আপনার খসড়া এখানেই আছে।'));
      setAvailability(false, notConnected());
    }
  }

  async function checkConnection() {
    if (checking) return;
    checking = true;
    setAvailability(false, words('Checking whether online contributions are available…', 'অনলাইনে অবদান জমা দেওয়া যাচ্ছে কি না দেখা হচ্ছে…'));
    try {
      const config = await request('/api/config');
      if (config.available !== true) throw new Error('Not configured');
      if (Number.isInteger(config.uploads?.max_files) && config.uploads.max_files > 0) maxFiles = Math.min(3, config.uploads.max_files);
      if (Number.isInteger(config.uploads?.max_file_bytes) && config.uploads.max_file_bytes > 0) maxBytes = Math.min(1500000, config.uploads.max_file_bytes);
      $('files-help').textContent = words(`Up to ${maxFiles} files, ${(maxBytes / 1000000).toLocaleString('en-IN')} MB each. JPEG, PNG, WebP, PDF or TXT. For larger files, add a link under “Add a place, date or source”.`, `সর্বাধিক ${maxFiles.toLocaleString('bn-IN')}টি ফাইল, প্রতিটি ${(maxBytes / 1000000).toLocaleString('bn-IN')} MB। JPEG, PNG, WebP, PDF বা TXT। বড় ফাইলের লিঙ্ক “স্থান, তারিখ বা উৎস যোগ করুন” অংশে দিন।`);
      challengeKey = typeof config.turnstile_site_key === 'string' && config.turnstile_site_key ? config.turnstile_site_key : null;
      checking = false;
      setAvailability(true);
      validateFiles();
      if (challengeKey && !receipt) await setupChallenge(challengeKey);
    } catch (_) {
      checking = false;
      setAvailability(false, notConnected());
    }
  }

  function failureMessage(failure) {
    if (failure.status === 429) return words('There have been too many submissions. Please wait a few minutes before trying again. Your draft is still here.', 'অল্প সময়ে অনেক অবদান এসেছে। কয়েক মিনিট পরে আবার চেষ্টা করুন। আপনার খসড়া এখানেই আছে।');
    if (failure.status === 413) return words('The files are too large to submit. Choose smaller files or include a source link. Your draft is still here.', 'ফাইলগুলি জমা দেওয়ার জন্য বড়। ছোট ফাইল বাছুন বা উৎসের লিঙ্ক দিন। আপনার খসড়া এখানেই আছে।');
    if ([400, 422].includes(failure.status)) return words('Some contribution details were not accepted. Check the required fields, file formats and permissions, then try again.', 'অবদানের কিছু তথ্য গ্রহণ করা যায়নি। আবশ্যক ঘর, ফাইলের ধরন ও অনুমতি দেখে আবার চেষ্টা করুন।');
    if (failure.status === 403) return words('The verification check was not accepted. Please complete it again and retry. Your draft is still here.', 'যাচাই গৃহীত হয়নি। ধাপটি আবার সম্পূর্ণ করে চেষ্টা করুন। আপনার খসড়া এখানেই আছে।');
    return words('We could not confirm that your contribution was received. Keep this page open and try again with the same details; the retry will not create a duplicate. You can also open your draft.', 'আপনার অবদান পাওয়া গেছে কি না নিশ্চিত করা যায়নি। পাতাটি খোলা রেখে একই তথ্য দিয়ে আবার চেষ্টা করুন; এতে একই অবদান দুবার জমা হবে না। খসড়াও খুলতে পারেন।');
  }

  form.addEventListener('invalid', event => {
    const details = event.target.closest('details');
    if (details) details.open = true;
  }, true);
  form.addEventListener('input', event => {
    if (event.target.name === 'website' || event.target.name === 'cf-turnstile-response') return;
    dirty = true;
    clientId = null;
    if ('setCustomValidity' in event.target && event.target !== files) event.target.setCustomValidity('');
    if (event.target.name === 'credit' || event.target.name === 'contributor_name') $('contribution-name').setCustomValidity('');
  });
  files.addEventListener('change', updateFiles);
  form.addEventListener('change', event => { if (event.target.name === 'type') updateContributionType(true); });
  $('clear-files').addEventListener('click', () => { files.value = ''; dirty = true; clientId = null; updateFiles(); });
  $('download-draft').addEventListener('click', () => openJSON('aguri-heritage-contribution-draft.json', formDraft()));
  $('connection-retry').addEventListener('click', checkConnection);
  $('refresh-receipt').addEventListener('click', () => refreshReceipt());
  $('copy-receipt').addEventListener('click', async () => {
    if (!receipt) return;
    try {
      await navigator.clipboard.writeText(trackingLink());
      $('receipt-action-status').textContent = words('Private tracking link copied.', 'ব্যক্তিগত অগ্রগতির লিঙ্ক কপি হয়েছে।');
    } catch (_) {
      $('receipt-link').focus();
      $('receipt-link').select();
      $('receipt-action-status').textContent = words('The link is selected. Use your browser’s Copy command to save it.', 'লিঙ্কটি নির্বাচিত আছে। সংরক্ষণ করতে ব্রাউজারের কপি নির্দেশ ব্যবহার করুন।');
    }
  });
  $('download-receipt').addEventListener('click', () => {
    if (receipt) openJSON(`aguri-heritage-receipt-${receipt.id}.json`, { id: receipt.id, type: receipt.type || '', title: receipt.title || '', status: receipt.status || '', created_at: receipt.created_at || '', tracking_link: trackingLink(), note: words('Keep this private link to check progress and reply to editors. Receipt does not grant reuse or publication permission.', 'অগ্রগতি দেখতে ও সম্পাদকদের উত্তর দিতে এই ব্যক্তিগত লিঙ্কটি রাখুন। প্রাপ্তিস্বীকার পুনর্ব্যবহার বা প্রকাশের অনুমতি নয়।') });
  });

  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (sending || !available) return;
    setError('');
    validateText();
    validateFiles();
    if (!form.reportValidity()) return;
    if (challengeKey && !challengeToken) { setError(words('Please complete the verification check first.', 'আগে যাচাইয়ের ধাপটি সম্পূর্ণ করুন।')); return; }
    const payload = new FormData(form);
    if (!files.files.length) payload.delete('attachments');
    for (const name of ['title', 'description', 'contributor_name', 'place', 'date_text', 'source_url', 'email']) payload.set(name, String(payload.get(name) || '').trim());
    clientId ||= uuid();
    payload.set('client_id', clientId);
    if (challengeToken) payload.set('cf-turnstile-response', challengeToken);
    const submittedTitle = String(payload.get('title'));
    const submittedType = String(payload.get('type'));
    sending = true;
    send.disabled = true;
    send.textContent = isRightsEnquiry() ? words('Sending private enquiry…', 'ব্যক্তিগত অনুরোধ পাঠানো হচ্ছে…') : words('Sending for review…', 'পর্যালোচনার জন্য পাঠানো হচ্ছে…');
    form.setAttribute('aria-busy', 'true');
    const enabledFields = [...form.elements].filter(control => !control.disabled);
    enabledFields.forEach(control => { control.disabled = true; });
    try {
      const data = await request('/api/contributions', { method: 'POST', body: payload });
      if (typeof data.id !== 'string' || !/^[A-Za-z0-9_-]{6,100}$/.test(data.id) || typeof data.token !== 'string' || !/^[A-Za-z0-9_-]{20,180}$/.test(data.token) || !Object.hasOwn(validStatuses, data.status)) throw new Error('Invalid receipt');
      receipt = { ...data, type: data.type || submittedType, title: submittedTitle, loaded: true };
      dirty = false;
      clientId = null;
      history.replaceState(null, '', trackingLink());
      showReceipt(receipt, true);
      form.reset();
      files.value = '';
      $('receipt-heading').focus();
    } catch (failure) {
      setError(failureMessage(failure));
      if (failure.status === 503) setAvailability(false, notConnected());
    } finally {
      sending = false;
      form.removeAttribute('aria-busy');
      enabledFields.forEach(control => { control.disabled = false; });
      if (challengeWidget !== null && window.turnstile) { window.turnstile.reset(challengeWidget); challengeToken = ''; }
      updateContributionType();
      send.disabled = !available || Boolean(challengeKey && !challengeToken);
    }
  });

  $('contribution-reply').addEventListener('input', () => { replyDirty = true; $('contribution-reply').setCustomValidity(''); });
  $('contribution-reply-form').addEventListener('submit', async event => {
    event.preventDefault();
    if (!available || !receipt?.loaded || replying) return;
    const field = $('contribution-reply');
    const message = field.value.trim();
    field.setCustomValidity(message ? '' : words('Please enter a message.', 'অনুগ্রহ করে একটি বার্তা লিখুন।'));
    if (!event.currentTarget.reportValidity()) return;
    replying = true;
    $('reply-send').disabled = true;
    $('reply-send').textContent = words('Sending…', 'পাঠানো হচ্ছে…');
    field.disabled = true;
    $('reply-status').textContent = '';
    setError('');
    try {
      await request(`/api/contributions/${encodeURIComponent(receipt.id)}/reply`, { method: 'POST', headers: { Authorization: `Bearer ${receipt.token}`, 'Content-Type': 'application/json' }, body: JSON.stringify({ message }) });
      field.value = '';
      replyDirty = false;
      $('reply-status').textContent = words('Your additional information has been sent to the editors.', 'আপনার অতিরিক্ত তথ্য সম্পাদকদের কাছে পাঠানো হয়েছে।');
      await refreshReceipt();
    } catch (failure) {
      setError(failure.status === 429 ? words('Please wait a few minutes before sending another reply. Your message is still here.', 'আরেকটি উত্তর পাঠানোর আগে কয়েক মিনিট অপেক্ষা করুন। আপনার বার্তা এখানেই আছে।') : words('We could not confirm your reply was received. Your message is still here; check your connection before trying again.', 'আপনার উত্তর পাওয়া গেছে কি না নিশ্চিত করা যায়নি। বার্তাটি এখানেই আছে; আবার চেষ্টা করার আগে সংযোগ দেখুন।'));
    } finally {
      replying = false;
      field.disabled = false;
      $('reply-send').disabled = !available || !receipt?.loaded;
      $('reply-send').textContent = initialReplyText;
    }
  });

  // No personal draft data is stored in localStorage, sessionStorage or cookies.
  // Keep the browser's normal leave-page warning for both navigation and language changes.
  window.addEventListener('beforeunload', event => {
    if (dirty || replyDirty || sending || replying) { event.preventDefault(); event.returnValue = ''; }
  });
  document.addEventListener('change', event => {
    if (event.target.id !== 'language-picker' || !(dirty || replyDirty || sending || replying)) return;
    event.stopImmediatePropagation();
    if (sending || replying) { event.target.selectedIndex = bn ? 1 : 0; setError(words('Please wait until sending finishes before changing languages.', 'ভাষা বদলানোর আগে পাঠানো শেষ হওয়া পর্যন্ত অপেক্ষা করুন।')); return; }
    const proceed = window.confirm(words('Changing language will leave this draft. Cancel to keep writing or open your draft first. Continue?', 'ভাষা বদলালে এই খসড়া ছেড়ে যেতে হবে। লেখা চালাতে বা আগে খসড়া খুলতে বাতিল করুন। এগিয়ে যাবেন?'));
    if (!proceed) { event.target.selectedIndex = bn ? 1 : 0; return; }
    const destination = new URL(event.target.value, location.href);
    destination.search = location.search;
    destination.hash = location.hash;
    dirty = false;
    replyDirty = false;
    location.assign(destination.href);
  }, true);

  prefill();
  updateContributionType();
  receipt = receiptCredentials();
  if (receipt) showReceipt(receipt);
  else if (new URLSearchParams(location.hash.slice(1)).has('receipt')) setError(words('This tracking link is incomplete. Open the complete private link saved in your receipt.', 'অগ্রগতির এই লিঙ্ক অসম্পূর্ণ। প্রাপ্তিস্বীকারে সংরক্ষিত সম্পূর্ণ ব্যক্তিগত লিঙ্কটি খুলুন।'));
  checkConnection().then(() => { if (receipt) refreshReceipt(true); });
})();
