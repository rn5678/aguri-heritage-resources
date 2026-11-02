(() => {
  'use strict';
  const form = document.getElementById('contact-form');
  if (!form) return;
  const $ = id => document.getElementById(id);
  const bn = document.documentElement.lang === 'bn';
  const words = (en, bengali) => bn ? bengali : en;
  const send = $('contact-send');
  const status = $('contact-status');
  const error = $('contact-error');
  const retry = $('contact-retry');
  const captcha = $('contact-captcha');
  const captchaStatus = $('contact-captcha-status');
  const preview = $('contact-preview');
  const loopback = ['localhost', '127.0.0.1', '[::1]', '::1'].includes(location.hostname);
  const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
  let available = false;
  let loading = false;
  let sending = false;
  let received = false;
  let token = '';
  let widget = null;
  let scriptPromise = null;
  let request = null;

  const text = {
    checking: words('Checking message service availability…', 'বার্তা পাঠানোর পরিষেবা চালু আছে কি না দেখা হচ্ছে…'),
    unavailable: words('Contact messages are temporarily unavailable. Please try again later. Your text will stay here while this page is open.', 'বার্তা পাঠানোর পরিষেবা আপাতত বন্ধ আছে। পরে আবার চেষ্টা করুন। এই পাতা খোলা থাকলে আপনার লেখা এখানেই থাকবে।'),
    ready: words('Complete the security check, then send your message.', 'নিরাপত্তা যাচাই সম্পূর্ণ করে আপনার বার্তা পাঠান।'),
    loadingCaptcha: words('Loading the security check…', 'নিরাপত্তা যাচাই চালু হচ্ছে…'),
    captchaReady: words('Security check complete. You can send your message.', 'নিরাপত্তা যাচাই সম্পূর্ণ হয়েছে। এখন বার্তা পাঠাতে পারেন।'),
    captchaExpired: words('The security check expired. Complete it again before sending.', 'নিরাপত্তা যাচাইয়ের মেয়াদ শেষ হয়েছে। পাঠানোর আগে আবার যাচাই করুন।'),
    captchaUnavailable: words('The security check is unavailable. Your message has been kept here. Choose Try again to reload it.', 'নিরাপত্তা যাচাই এখন কাজ করছে না। আপনার লেখা এখানেই আছে। আবার চালু করতে “আবার চেষ্টা করুন” বেছে নিন।'),
    sending: words('Sending your message…', 'আপনার বার্তা পাঠানো হচ্ছে…'),
    invalid: words('Check the required fields and your email address, then try again.', 'আবশ্যক ঘরগুলি ও ইমেল ঠিকানা দেখে আবার চেষ্টা করুন।'),
    uncertain: words('We could not confirm receipt. Your message is still here. Complete a new security check and retry the same message.', 'বার্তা পাওয়া গেছে কি না নিশ্চিত করা যায়নি। আপনার লেখা এখানেই আছে। নতুন করে নিরাপত্তা যাচাই সম্পূর্ণ করে একই বার্তা আবার পাঠান।'),
    conflict: words('This request could not be safely retried. Keep a copy of your message, then refresh this page before sending again.', 'এই অনুরোধটি নিরাপদে আবার পাঠানো যায়নি। আপনার বার্তার একটি কপি রেখে পাতা রিফ্রেশ করুন, তারপর আবার পাঠান।'),
    rateLimited: words('Too many attempts. Please wait before trying again. Your message is still here.', 'অল্প সময়ে অনেকবার চেষ্টা হয়েছে। কিছুক্ষণ অপেক্ষা করে আবার চেষ্টা করুন। আপনার লেখা এখানেই আছে।'),
    invalidCaptcha: words('The security check was not accepted. Complete a new check and try again. Your message is still here.', 'নিরাপত্তা যাচাই গ্রহণ করা হয়নি। নতুন করে যাচাই সম্পূর্ণ করে আবার চেষ্টা করুন। আপনার লেখা এখানেই আছে।'),
    unsupported: words('This browser could not complete the security check. Try a supported, up-to-date browser. Your message is still here.', 'এই ব্রাউজারে নিরাপত্তা যাচাই সম্পূর্ণ করা যায়নি। হালনাগাদ ও সমর্থিত ব্রাউজারে চেষ্টা করুন। আপনার লেখা এখানেই আছে।'),
    previewReceived: words('Local test completed. No email was sent.', 'স্থানীয় পরীক্ষা সম্পূর্ণ হয়েছে। কোনও ইমেল পাঠানো হয়নি।'),
    received: words('Your message has been received. Reference: ', 'আপনার বার্তা পাওয়া গেছে। প্রাপ্তিস্বীকার নম্বর: ')
  };

  function updateSend() {
    send.disabled = !available || loading || sending || received || !token;
    retry.disabled = loading || sending;
  }

  function showError(message, focus = false) {
    error.textContent = message;
    error.hidden = !message;
    if (message && focus) error.focus();
  }

  function clearToken(message = '') {
    token = '';
    captchaStatus.textContent = message;
    updateSend();
  }

  function removeWidget() {
    clearToken();
    if (widget !== null && window.turnstile?.remove) {
      try { window.turnstile.remove(widget); } catch { /* Keep submission disabled. */ }
    }
    widget = null;
    captcha.replaceChildren();
    captcha.hidden = true;
  }

  function resetWidget() {
    clearToken(available ? text.ready : '');
    if (widget !== null && window.turnstile?.reset) {
      try { window.turnstile.reset(widget); }
      catch {
        captchaStatus.textContent = text.captchaUnavailable;
        retry.hidden = false;
      }
    }
  }

  async function jsonRequest(url, options = {}, timeout = 15000) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);
    try {
      const response = await fetch(url, { ...options, signal: controller.signal, credentials: 'same-origin', cache: 'no-store' });
      const data = await response.json();
      if (!data || typeof data !== 'object' || Array.isArray(data)) throw new Error('Invalid response');
      return { response, data };
    } finally { clearTimeout(timer); }
  }

  function loadTurnstile() {
    if (window.turnstile?.render) return Promise.resolve();
    if (scriptPromise) return scriptPromise;
    scriptPromise = new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit';
      script.async = true;
      const timer = setTimeout(() => { script.remove(); reject(new Error('Verification unavailable')); }, 15000);
      script.onload = () => {
        clearTimeout(timer);
        if (window.turnstile?.render) resolve();
        else { script.remove(); reject(new Error('Verification unavailable')); }
      };
      script.onerror = () => { clearTimeout(timer); script.remove(); reject(new Error('Verification unavailable')); };
      document.head.append(script);
    }).catch(reason => { scriptPromise = null; throw reason; });
    return scriptPromise;
  }

  async function configure() {
    // This reviewed design release deliberately does not activate delivery.
    // Keep the form closed even if unrelated service configuration changes.
    if (form.dataset.contactState === 'disabled') {
      available = false;
      for (const field of form.elements) field.disabled = true;
      preview.hidden = true;
      retry.hidden = true;
      status.textContent = words(
        'This contact form is not available yet. Please use the contribution form for a source or correction, or check back later for general enquiries.',
        'যোগাযোগের এই ফর্মটি এখনও চালু হয়নি। উৎস বা সংশোধন জানাতে সহযোগিতার ফর্ম ব্যবহার করুন। সাধারণ প্রশ্নের জন্য পরে আবার এই পাতায় আসুন।');
      updateSend();
      return;
    }
    if (loading || sending || received) return;
    loading = true;
    available = false;
    showError('');
    removeWidget();
    preview.hidden = true;
    retry.hidden = true;
    status.textContent = text.checking;
    updateSend();
    try {
      const { response, data } = await jsonRequest('/api/contact/config');
      const sitekey = typeof data.turnstile_site_key === 'string' ? data.turnstile_site_key.trim() : '';
      // Preview is restricted to loopback. Public pages never treat a test flag as availability.
      if (data.preview === true && loopback) preview.hidden = false;
      if (!response.ok || data.available !== true || !sitekey || sitekey.length > 256 || (data.preview === true && !loopback)) {
        status.textContent = text.unavailable;
        retry.hidden = false;
        return;
      }
      available = true;
      status.textContent = text.ready;
      captcha.hidden = false;
      captchaStatus.textContent = text.loadingCaptcha;
      await loadTurnstile();
      const captchaSize = captcha.getBoundingClientRect().width < 300 ? 'compact' : 'flexible';
      widget = window.turnstile.render(captcha, {
        sitekey, action: 'contact', theme: 'light', size: captchaSize, language: 'auto',
        'response-field': false,
        callback: value => {
          if (!available || sending || received || typeof value !== 'string' || !value || value.length > 2048) return;
          token = value;
          captchaStatus.textContent = text.captchaReady;
          retry.hidden = true;
          updateSend();
        },
        'expired-callback': () => clearToken(text.captchaExpired),
        'error-callback': () => { clearToken(text.captchaUnavailable); retry.hidden = false; return true; },
        'timeout-callback': () => { clearToken(text.captchaExpired); retry.hidden = false; },
        'unsupported-callback': () => { clearToken(text.unsupported); retry.hidden = false; }
      });
    } catch {
      status.textContent = available ? text.captchaUnavailable : text.unavailable;
      clearToken();
      retry.hidden = false;
    } finally {
      loading = false;
      updateSend();
    }
  }

  function draft() {
    const value = name => String(form.elements.namedItem(name)?.value || '').trim();
    return { name: value('name'), email: value('email'), subject: value('subject'), message: value('message'),
      language: bn ? 'bn' : 'en', website: value('website'), consent: form.elements.namedItem('consent')?.checked ? 'yes' : '' };
  }

  function newRequestId() {
    if (window.crypto?.randomUUID) return window.crypto.randomUUID();
    if (!window.crypto?.getRandomValues) throw new Error('Secure request ID unavailable');
    const bytes = window.crypto.getRandomValues(new Uint8Array(16));
    bytes[6] = (bytes[6] & 15) | 64;
    bytes[8] = (bytes[8] & 63) | 128;
    return Array.from(bytes, (byte, index) => ([4, 6, 8, 10].includes(index) ? '-' : '') + byte.toString(16).padStart(2, '0')).join('');
  }

  form.addEventListener('input', event => {
    if (event.target?.setCustomValidity) event.target.setCustomValidity('');
    if (request && JSON.stringify(draft()) !== request.signature) request = null;
  });
  form.addEventListener('change', () => {
    if (request && JSON.stringify(draft()) !== request.signature) request = null;
  });
  form.addEventListener('invalid', () => showError(text.invalid), true);
  retry.addEventListener('click', configure);

  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (sending || loading || received) return;
    showError('');
    const body = draft();
    for (const field of ['name', 'subject', 'message']) {
      form.elements.namedItem(field).setCustomValidity(body[field] ? '' : text.invalid);
    }
    if (!form.reportValidity()) { resetWidget(); return; }
    if (!available || !token) {
      showError(available ? text.ready : text.unavailable, true);
      resetWidget();
      return;
    }
    const signature = JSON.stringify(body);
    try {
      if (!request || request.signature !== signature) request = { signature, id: newRequestId() };
    } catch {
      showError(text.unsupported, true);
      resetWidget();
      return;
    }
    const submittedToken = token;
    sending = true;
    clearToken();
    status.textContent = text.sending;
    form.setAttribute('aria-busy', 'true');
    const enabled = [...form.elements].filter(field => !field.disabled);
    for (const field of enabled) field.disabled = true;
    updateSend();
    try {
      const { response, data } = await jsonRequest('/api/contact', {
        method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify({ ...body, token: submittedToken, request_id: request.id })
      }, 25000);
      if ([200, 201].includes(response.status) && data.received === true && typeof data.reference === 'string' && uuid.test(data.reference)) {
        received = true;
        const testing = !preview.hidden && loopback;
        status.textContent = testing ? text.previewReceived : text.received;
        if (testing) status.append(document.createTextNode(words(' Test reference: ', ' পরীক্ষার নম্বর: ')));
        const reference = document.createElement('span');
        reference.className = 'contact-reference';
        reference.lang = 'en';
        reference.dir = 'ltr';
        reference.textContent = data.reference;
        status.append(reference);
        form.reset();
        form.hidden = true;
        retry.hidden = true;
        status.tabIndex = -1;
        status.focus();
      } else {
        const messages = { validation: text.invalid, invalid_field: text.invalid, invalid_captcha: text.invalidCaptcha,
          captcha_unavailable: text.captchaUnavailable, rate_limited: text.rateLimited,
          service_unavailable: text.unavailable, submission_conflict: text.conflict };
        showError(messages[data.error] || text.uncertain, true);
        status.textContent = text.ready;
        if (data.error === 'captcha_unavailable') retry.hidden = false;
        if (data.error === 'service_unavailable') {
          available = false;
          status.textContent = text.unavailable;
          retry.hidden = false;
        }
      }
    } catch {
      showError(text.uncertain, true);
      status.textContent = text.ready;
    } finally {
      sending = false;
      form.removeAttribute('aria-busy');
      for (const field of enabled) field.disabled = false;
      // Tokens are single-use. Every attempt requires a fresh challenge, including retries.
      if (received) removeWidget();
      else resetWidget();
      updateSend();
    }
  });

  configure();
})();
