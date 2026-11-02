"use strict";

// Pure publishing decisions are shared with the focused UI checks.
const EditorPublishing = (() => {
  const phases = ["idle", "preparing", "ready", "publishing", "review", "deploying", "clean", "success", "error"];
  function githubLink(value) {
    if (typeof value !== "string") return "";
    try {
      const url = new URL(value);
      if (url.origin !== "https://github.com" || url.username || url.password || url.hash) return "";
      if (!/^\/rn5678\/aguri-heritage-resources\/(?:compare\/[A-Za-z0-9._~:%/-]+|pull\/[1-9][0-9]*\/?|actions(?:\/runs\/[1-9][0-9]*(?:\/job\/[1-9][0-9]*)?)?\/?)$/.test(url.pathname)) return "";
      return url.href;
    } catch { return ""; }
  }
  function siteLink(value) {
    try { return new URL(value).href === "https://aguri-heritage.in/" ? "https://aguri-heritage.in/" : ""; }
    catch { return ""; }
  }
  function localBusy(phase) { return ["preparing", "publishing"].includes(phase); }
  function remoteBusy(phase) { return ["review", "deploying"].includes(phase); }
  function pollDelay(phase, disconnected = false) {
    if (disconnected && (localBusy(phase) || remoteBusy(phase))) return 15000;
    return localBusy(phase) ? 1500 : remoteBusy(phase) ? 15000 : null;
  }
  function sourceBlocked(state) {
    return Boolean(state.dirty || state.translationBlocked || state.saving || state.loading || state.readingImage ||
      state.creating || state.creatingType || state.catalogFetching || state.publishRequest || localBusy(state.phase));
  }
  function createRequest(fetcher, initialToken) {
    let currentToken = initialToken;
    let reconnecting = null;
    const reconnectMessage = "The editor could not reconnect. Keep this tab open; your unsaved edits are still here. Reopen the editor app, then try again.";
    async function reconnect() {
      if (!reconnecting) reconnecting = (async () => {
        const response = await fetcher("/", { credentials: "same-origin", cache: "no-store" });
        if (!response.ok) throw new Error(reconnectMessage);
        const html = await response.text();
        const match = html.match(/<meta\s+name=["']editor-token["']\s+content=["']([A-Za-z0-9_-]{20,})["']\s*\/?\s*>/i);
        if (!match) throw new Error(reconnectMessage);
        currentToken = match[1];
      })().finally(() => { reconnecting = null; });
      try { await reconnecting; } catch { throw new Error(reconnectMessage); }
    }
    return async function request(url, options = {}) {
      const headers = new Headers(options.headers || {});
      const authenticated = headers.has("X-Editor-Token");
      if (authenticated) headers.set("X-Editor-Token", currentToken);
      let response = await fetcher(url, { credentials: "same-origin", ...options, headers });
      // A rejected request has not mutated source. Renew only this explicit 403;
      // never retry a failed network request that might already have saved/pushed.
      if (response.status === 403 && authenticated) {
        await reconnect();
        headers.set("X-Editor-Token", currentToken);
        response = await fetcher(url, { credentials: "same-origin", ...options, headers });
        if (response.status === 403) throw new Error(reconnectMessage);
      }
      let data;
      try { data = await response.json(); }
      catch { throw new Error("The editor received an unexpected response. Keep this tab open and check that the editor app is running."); }
      if (!data || typeof data !== "object" || Array.isArray(data)) throw new Error("The editor received an unexpected response. Keep this tab open and try again.");
      if (!response.ok || data.ok === false) throw new Error(data.error || data.message || "The request could not be completed.");
      return data;
    };
  }
  return { phases, githubLink, siteLink, localBusy, remoteBusy, pollDelay, sourceBlocked, createRequest };
})();

// Content operations shared by the editor and its isolated regression tests.
const EditorContent = (() => {
  const alignments = new Set(["", "left", "center", "right", "justify"]);
  const formattingTags = new Set(["B", "STRONG", "I", "EM", "U", "S", "STRIKE", "DEL", "SUP", "SUB", "SMALL", "MARK", "FONT"]);
  function alignment(value) { return alignments.has(value) ? value : ""; }
  function removedBlocks(state) {
    const removed = new Set(state.deletedBlocks);
    for (const id of state.deletedImages) {
      for (const child of state.imageMeta.get(id)?.deleteBlockIds || []) removed.add(String(child));
    }
    return removed;
  }
  function dirtyCount(state) {
    const removed = removedBlocks(state);
    const edited = new Set([...state.changedBlocks.keys(), ...state.blockFormats.keys()]);
    return [...edited].filter(id => !removed.has(id) && !state.insertedBlocks.has(id)).length +
      [...state.imageChanges.keys()].filter(id => !state.deletedImages.has(id)).length +
      [...state.deletedBlocks].filter(id => ![...state.deletedImages].some(image =>
        (state.imageMeta.get(image)?.deleteBlockIds || []).map(String).includes(id))).length +
      state.deletedImages.size + state.insertedBlocks.size;
  }
  function saveFields(state, insertions) {
    const removed = removedBlocks(state);
    return {
      blocks: Object.fromEntries([...state.changedBlocks].filter(([id]) => !removed.has(id))),
      blockFormats: Object.fromEntries([...state.blockFormats].filter(([id]) => !removed.has(id) && !state.insertedBlocks.has(id))),
      images: Object.fromEntries([...state.imageChanges].filter(([id]) => !state.deletedImages.has(id))),
      deleteBlocks: [...state.deletedBlocks].filter(id => ![...state.deletedImages].some(image =>
        (state.imageMeta.get(image)?.deleteBlockIds || []).map(String).includes(id))),
      deleteImages: [...state.deletedImages], insertBlocks: insertions,
    };
  }
  function validRange(range, block) {
    return Boolean(range && block?.isConnected && block.contains(range.startContainer) && block.contains(range.endContainer));
  }
  function splitsGeneratedField(text, start, end) {
    return [...text.matchAll(/\{\{[\s\S]*?\}\}/g)].some(match =>
      (start > match.index && start < match.index + match[0].length) ||
      (end > match.index && end < match.index + match[0].length));
  }
  function semanticAttributes(node) {
    return [...node.attributes].filter(attr => ["id", "name", "lang", "dir", "title"].includes(attr.name) || attr.name.startsWith("aria-"));
  }
  function cleanFragment(node, document, mode) {
    if (node.nodeType === 3 || node.nodeType === 8) return node.cloneNode(true);
    if (node.nodeType === 1 && node.classList.contains("editor-citation")) return node.cloneNode(true);
    const unwrap = node.nodeType === 1 && (mode === "unlink" ? node.tagName === "A" : formattingTags.has(node.tagName));
    const semantic = unwrap ? semanticAttributes(node) : [];
    const result = node.nodeType === 11 || (unwrap && !semantic.length) ? document.createDocumentFragment() :
      unwrap ? document.createElement(mode === "unlink" && node.hasAttribute("name") ? "a" : "span") : node.cloneNode(false);
    if (unwrap && semantic.length) for (const attr of semantic) result.setAttribute(attr.name, attr.value);
    if (mode === "clear" && result.nodeType === 1) result.removeAttribute("style");
    for (const child of node.childNodes) result.append(cleanFragment(child, document, mode));
    return result;
  }
  function clearedSelectionHTML(block, range, mode = "clear") {
    if (!validRange(range, block) || range.collapsed) return null;
    const doc = block.ownerDocument;
    const before = doc.createRange(); before.selectNodeContents(block); before.setEnd(range.startContainer, range.startOffset);
    const after = doc.createRange(); after.selectNodeContents(block); after.setStart(range.endContainer, range.endOffset);
    let selected = range.cloneContents();
    let ancestor = range.commonAncestorContainer.nodeType === 1 ? range.commonAncestorContainer : range.commonAncestorContainer.parentElement;
    while (ancestor && ancestor !== block) {
      const shell = ancestor.cloneNode(false); shell.append(selected); selected = shell; ancestor = ancestor.parentElement;
    }
    const output = doc.createElement("div");
    output.append(before.cloneContents(), cleanFragment(selected, doc, mode), after.cloneContents());
    // Splitting a named wrapper around a selection must not duplicate its target.
    const ids = new Set(), names = new Set();
    for (const node of output.querySelectorAll("[id],a[name]")) {
      if (node.hasAttribute("id")) { const id = node.getAttribute("id"); if (ids.has(id)) node.removeAttribute("id"); else ids.add(id); }
      if (node.tagName === "A" && node.hasAttribute("name")) { const name = node.getAttribute("name"); if (names.has(name)) node.removeAttribute("name"); else names.add(name); }
    }
    return output.innerHTML;
  }
  return { alignment, removedBlocks, dirtyCount, saveFields, validRange, splitsGeneratedField, cleanFragment, clearedSelectionHTML };
})();

// Editor application.
(() => {
  const $ = (selector) => document.querySelector(selector);
  const ui = {
    list: $("#page-list"), search: $("#page-search"), title: $("#document-title"),
    eyebrow: $("#document-eyebrow"), heading: $("#document-heading"), panel: $("#editor-panel"),
    content: $("#document-content"), status: $("#status"), empty: $("#empty-state"),
    save: $("#save-button"), preview: $("#preview-button"), reset: $("#reset-button"),
    count: $("#change-count"), dialog: $("#link-dialog"), linkUrl: $("#link-url"), linkError: $("#link-error"),
    publish: $("#publish-button"), publicationStatus: $("#publication-status"), publishDialog: $("#publish-dialog"),
    publishTitle: $("#publish-title"), publishMessage: $("#publish-message"), publishReview: $("#publish-review"),
    publishCounts: $("#publish-counts"), publishPrepared: $("#publish-prepared"), publishDetail: $("#publish-detail"),
    publishConfirm: $("#publish-confirm"), publishRetry: $("#publish-retry"), publishLive: $("#publish-live"),
    publishPrepare: $("#publish-prepare"), publishGithub: $("#publish-github"), publishChecks: $("#publish-checks"),
    publishSteps: $("#publish-steps"), publishHandoff: $("#publish-handoff"), publishNextStep: $("#publish-next-step"),
    publishStatusNotice: $("#publish-status-notice"),
    publishFiles: $("#publish-files"), publishFilesPanel: $("#publish-files-panel"), publishBranch: $("#publish-branch"),
    translationCard: $("#translation-card"), translationEnabled: $("#translation-enabled"),
    translationStatus: $("#translation-status"), translationPublishNote: $("#translation-publish-note"),
    translationRetry: $("#translation-retry"), translationUsage: $("#translation-usage"),
    translationUsageTotal: $("#translation-usage-total"), translationUsageLast: $("#translation-usage-last"),
    translationUsageModel: $("#translation-usage-model"), translationReviewDocuments: $("#translation-review-documents"),
    translationAccept: $("#translation-accept"), translationReloadNote: $("#translation-reload-note"),
    translationReloadMessage: $("#translation-reload-message"), translationReload: $("#translation-reload"),
    addTextBlock: $("#add-text-block"), blockSelect: $("#block-select"), undoBlock: $("#undo-block-change"),
    addPage: $("#add-page"), pageTypes: $("#manage-page-types"), createDialog: $("#create-page-dialog"),
    createForm: $("#create-page-form"), createFields: $("#create-page-fields"), createStatus: $("#create-page-status"),
    createSubmit: $("#create-page-submit"), createCancel: $("#create-page-cancel"), createRetry: $("#create-page-retry"),
    createAddType: $("#create-page-add-type"), newType: $("#new-page-type"), newSection: $("#new-page-section"),
    newTitle: $("#new-page-title"), newSlug: $("#new-page-slug"), typeDescription: $("#new-page-type-description"),
    typesDialog: $("#page-types-dialog"), typesForm: $("#page-types-form"), typesFields: $("#page-types-fields"),
    typesList: $("#page-types-list"), typesStatus: $("#page-types-status"), typesSubmit: $("#page-types-submit"),
    typesCancel: $("#page-types-cancel"), typesRetry: $("#page-types-retry")
  };
  const state = {
    pages: [], types: [], sections: [], catalogLoaded: false, catalogFetching: false, catalogError: "",
    creating: false, creatingType: false, slugEdited: false,
    doc: null, lang: "en", loading: false, saving: false, readingImage: false, loadId: 0,
    blocks: new Map(), blockOriginals: new Map(), changedBlocks: new Map(),
    blockMeta: new Map(), blockWrappers: new Map(), deletedBlocks: new Set(), insertedBlocks: new Map(),
    blockHistory: [], structuralUndoPending: false,
    imageChanges: new Map(), imageOriginals: new Map(), imageMeta: new Map(), imageWrappers: new Map(), deletedImages: new Set(),
    blockFormats: new Map(), formatOriginals: new Map(), activeBlock: null, selection: null,
    publication: { phase: "idle" }, publishRequest: false, publishTimer: null, publishConnectionError: "",
    publishFetching: false, publishSerial: 0, savedSincePreparation: false,
    translation: { enabled: true, phase: "idle", pending: 0, reviewCount: 0 }, translationLoaded: false,
    translationRequest: false, translationFetching: false, translationTimer: null, translationSerial: 0,
    translationConnectionError: "", bengaliFetching: false, bengaliReloadNeeded: null
  };
  const allowedTags = new Set(["P", "H1", "H2", "H3", "H4", "H5", "H6", "LI", "BLOCKQUOTE", "DIV", "FIGCAPTION", "DT", "DD"]);
  const token = $("meta[name='editor-token']")?.content || "";
  const isMac = /Mac|iPhone|iPad/.test(navigator.platform);
  $(".shortcut").textContent = isMac ? "⌘S" : "Ctrl S";

  function dirtyCount() {
    return EditorContent.dirtyCount(state);
  }
  function blockRemoved(id) { return EditorContent.removedBlocks(state).has(id); }
  function publishingBusy() { return EditorPublishing.localBusy(state.publication.phase); }
  function sourceActionBlocked() {
    return EditorPublishing.sourceBlocked({ ...state, phase: state.publication.phase,
      dirty: dirtyCount(), translationBlocked: translationBlocksPublication() });
  }
  function publishingLocked() { return state.publishRequest || publishingBusy() || (ui.publishDialog.open && state.publication.phase === "ready"); }
  function editingBusy() { return state.saving || state.loading || state.readingImage || state.translationRequest || state.creating || state.creatingType || state.catalogFetching || publishingLocked(); }
  function contentDialogOpen() { return ui.createDialog.open || ui.typesDialog.open; }
  function translationBusy() { return ["queued", "running"].includes(state.translation.phase); }
  function translationBlocksPublication() {
    if (state.translationRequest) return true;
    if (!state.translation.enabled) return false;
    return !state.translationLoaded || Boolean(state.translationConnectionError) || translationBusy() ||
      Number(state.translation.pending) > 0 || Number(state.translation.reviewCount) > 0 || ["error", "review"].includes(state.translation.phase);
  }
  function translationPublishInstruction() {
    if (!translationBlocksPublication()) return "";
    if (!state.translationLoaded || state.translationConnectionError) return "Check the Bengali update status before publishing.";
    if (state.translation.phase === "error") return "Retry the Bengali update before publishing, or turn off automatic updates to publish manually.";
    if (state.translation.phase === "review" || Number(state.translation.reviewCount) > 0) return "Update and check the Bengali pages listed below before publishing, or turn off automatic updates to publish manually.";
    return "Publishing will be available when the Bengali updates finish. All updates stay local until you publish.";
  }
  function setStatus(message, kind = "") {
    ui.status.textContent = message;
    ui.status.className = "status" + (kind ? ` ${kind}` : "");
    ui.status.setAttribute("role", kind === "error" ? "alert" : "status");
  }
  function updateControls() {
    const count = dirtyCount();
    const busy = editingBusy();
    ui.save.disabled = !state.doc || !count || busy;
    ui.preview.disabled = !state.doc || busy;
    // Viewing a sent update never depends on the selected page or translation work.
    ui.publish.disabled = false;
    ui.publish.title = "Prepare a GitHub update or view publishing progress";
    ui.publishConfirm.disabled = sourceActionBlocked() || state.savedSincePreparation || state.publication.phase !== "ready" || Boolean(state.publishConnectionError);
    ui.publishPrepare.disabled = sourceActionBlocked() || Boolean(state.publishConnectionError);
    ui.reset.hidden = !count;
    ui.reset.disabled = busy;
    ui.search.disabled = busy;
    ui.addPage.disabled = busy;
    ui.pageTypes.disabled = busy;
    ui.createFields.disabled = busy;
    ui.createSubmit.disabled = busy || !state.catalogLoaded || !state.types.length || !state.sections.length;
    ui.createCancel.disabled = state.creating;
    ui.createRetry.disabled = busy;
    ui.createSubmit.textContent = state.creating ? "Creating page…" : "Create page";
    ui.typesFields.disabled = busy;
    ui.typesSubmit.disabled = busy || !state.catalogLoaded;
    ui.typesCancel.disabled = state.creatingType;
    ui.typesRetry.disabled = busy;
    ui.typesSubmit.textContent = state.creatingType ? "Adding type…" : "Add page type";
    ui.list.inert = busy;
    $(".brand").inert = busy;
    $(".format-toolbar").inert = busy;
    ui.blockSelect.disabled = busy;
    ui.addTextBlock.disabled = busy || !findInsertionTarget();
    ui.addTextBlock.title = ui.addTextBlock.disabled ? "This page has no available place for a new text block." : "Add a paragraph beside the selected text block";
    ui.undoBlock.hidden = !state.blockHistory.length;
    ui.undoBlock.disabled = busy;
    ui.undoBlock.title = state.blockHistory.at(-1)?.label || "";
    ui.count.textContent = count ? `${count} unsaved ${count === 1 ? "change" : "changes"}` : "No unsaved changes";
    ui.publicationStatus.textContent = count && !publishingBusy() ? "Unsaved changes" : ({ preparing: "Preparing update…", ready: "Ready for GitHub", publishing: "Sending to GitHub…", review: "GitHub review", deploying: "Cloudflare publishing…", clean: "No new source changes", success: "Live on website", error: "Publishing needs attention" })[state.publication.phase] || "Saved locally";
    if (!count && state.savedSincePreparation && ["ready", "clean", "success"].includes(state.publication.phase)) ui.publicationStatus.textContent = "New changes saved locally";
    if (!count && state.publication.phase === "idle" && translationBlocksPublication()) ui.publicationStatus.textContent = translationBusy() ? "Updating Bengali…" : "Bengali needs attention";
    ui.translationEnabled.disabled = busy;
    ui.translationRetry.disabled = state.translationRequest || state.translationFetching || busy;
    const reviewPage = (state.translation.reviewDocuments || []).some((page) => page.id === state.doc?.id);
    ui.translationAccept.hidden = !reviewPage || state.lang !== "bn";
    ui.translationAccept.disabled = Boolean(count) || busy || state.translationRequest;
    ui.translationAccept.title = count ? "Save your Bengali edits before marking this page as checked." : "";
    const reloadNeeded = state.bengaliReloadNeeded?.id === state.doc?.id && state.lang === "bn";
    ui.translationReloadNote.hidden = !reloadNeeded;
    ui.translationReload.disabled = Boolean(count) || busy || state.bengaliFetching;
    ui.translationReloadMessage.textContent = count ? "Bengali was updated in the background. Your draft is still here; copy any edits you want to keep before discarding it and reloading." : "An updated Bengali version is ready. Reload it when you have finished reviewing this text.";
    document.body.classList.toggle("saving", state.saving);
    document.body.classList.toggle("loading", state.loading);
    document.body.classList.toggle("publishing", publishingLocked());
    ui.content.inert = busy;
    document.title = `${count ? "• " : ""}${state.doc?.title || "Aguri Heritage"} · Content editor`;
    document.querySelectorAll(".language").forEach((button) => {
      button.classList.toggle("active", button.dataset.lang === state.lang);
      button.setAttribute("aria-pressed", String(button.dataset.lang === state.lang));
      button.disabled = busy;
    });
    updateFormattingControls();
  }
  function markChanged(block) {
    const id = block.dataset.blockId;
    if (state.blocks.get(id) !== block) return;
    state.structuralUndoPending = false;
    updateEmptyBlock(block);
    if (state.insertedBlocks.has(id)) {
      state.insertedBlocks.get(id).html = block.innerHTML;
      block.classList.add("dirty");
      updateBlockOption(id);
      updateControls();
      setStatus("You have unsaved changes. Save when you’re ready.");
      return;
    }
    const changed = block.innerHTML !== state.blockOriginals.get(id);
    if (changed) state.changedBlocks.set(id, block.innerHTML);
    else state.changedBlocks.delete(id);
    block.classList.toggle("dirty", changed || state.blockFormats.has(id));
    updateBlockOption(id);
    updateControls();
    setStatus(dirtyCount() ? "You have unsaved changes. Save when you’re ready." : "All changes saved on this computer.");
  }
  const request = EditorPublishing.createRequest((...args) => fetch(...args), token);
  function publishPost(url, body = {}) {
    return request(url, { method: "POST", headers: { "Content-Type": "application/json", "X-Editor-Token": token }, body: JSON.stringify(body) });
  }
  function renderTranslation() {
    const translation = state.translation;
    ui.translationEnabled.checked = translation.enabled;
    const fallback = !translation.enabled ? "Automatic Bengali updates are off. You can edit and publish both languages manually." : ({
      idle: "New English edits will update Bengali after you save. Existing content is the starting point.",
      queued: "Your saved English changes are waiting for a Bengali update…",
      running: "Updating the changed Bengali text. You can keep editing; changes stay local.",
      success: "The Bengali update is saved locally. Preview it before publishing.",
      error: "The Bengali update could not finish. Your saved English changes are safe.",
      review: "Some Bengali text needs your review. Open the listed pages, update and check them, then use the saved Bengali version."
    })[translation.phase];
    const message = state.translationConnectionError || translation.message || fallback;
    if (ui.translationStatus.textContent !== message) ui.translationStatus.textContent = message;
    ui.translationStatus.className = "translation-status" + (translationBusy() && translation.enabled ? " busy" : "") + (state.translationConnectionError || ["error", "review"].includes(translation.phase) ? " attention" : "");
    ui.translationRetry.hidden = !state.translationConnectionError && translation.phase !== "error";
    ui.translationRetry.textContent = state.translationConnectionError ? "Check again" : "Retry update";
    const instruction = translationPublishInstruction();
    ui.translationPublishNote.hidden = !instruction;
    ui.translationPublishNote.textContent = instruction;
    ui.translationReviewDocuments.replaceChildren();
    const reviews = Array.isArray(translation.reviewDocuments) ? translation.reviewDocuments : [];
    ui.translationReviewDocuments.hidden = !reviews.length;
    for (const page of reviews) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "translation-review-page";
      button.textContent = `Open Bengali: ${page.title || page.id}${Number(page.count) > 0 ? ` (${page.count})` : ""}`;
      button.addEventListener("click", () => {
        if (editingBusy()) return;
        if (state.doc?.id === page.id && state.lang === "bn") { ui.content.scrollIntoView({ block: "start", behavior: "smooth" }); return; }
        if (discardAllowed()) loadDocument(page.id, "bn");
      });
      ui.translationReviewDocuments.append(button);
    }
    function usageText(usage) {
      const number = (key) => usage[key] != null && Number.isFinite(Number(usage[key])) ? Math.max(0, Number(usage[key])).toLocaleString() : "—";
      return `${number("input_tokens")} input · ${number("output_tokens")} output · ${number("cached_input_tokens")} cached input tokens`;
    }
    ui.translationUsage.hidden = !translation.usage && !translation.lastUsage;
    ui.translationUsageTotal.hidden = !translation.usage;
    ui.translationUsageTotal.textContent = translation.usage ? `Total: ${usageText(translation.usage)}` : "";
    ui.translationUsageLast.hidden = !translation.lastUsage;
    ui.translationUsageLast.textContent = translation.lastUsage ? `Latest update: ${usageText(translation.lastUsage)}` : "";
    ui.translationUsageModel.hidden = !translation.model;
    ui.translationUsageModel.textContent = translation.model ? `Model: ${translation.model}. This is translation activity, not your remaining account allowance.` : "";
    updateControls();
    if (ui.publishDialog.open) renderPublication();
  }
  function acceptTranslation(data) {
    if (!data || typeof data.enabled !== "boolean" || !["idle", "queued", "running", "success", "error", "review"].includes(data.phase)) throw new Error("The Bengali update status could not be read. Please check again.");
    state.translation = data;
    state.translationLoaded = true;
    state.translationConnectionError = "";
    renderTranslation();
    if (data.phase === "success") checkBengaliDocument();
  }
  function scheduleTranslationPoll() {
    clearTimeout(state.translationTimer);
    state.translationTimer = setTimeout(refreshTranslation, translationBusy() ? 2000 : 15000);
  }
  async function refreshTranslation(force = false) {
    if (state.translationRequest || (state.translationFetching && !force)) { scheduleTranslationPoll(); return; }
    const serial = ++state.translationSerial;
    state.translationFetching = true;
    try {
      const data = await request("/api/translation/status", { headers: { "X-Editor-Token": token }, cache: "no-store" });
      if (serial === state.translationSerial) acceptTranslation(data);
    } catch {
      if (serial === state.translationSerial) {
        state.translationConnectionError = "Bengali update status is unavailable. Keep the editor app running and choose Check again.";
        renderTranslation();
      }
    } finally {
      if (serial === state.translationSerial) state.translationFetching = false;
      updateControls();
      scheduleTranslationPoll();
    }
  }
  async function changeTranslation(url, body = {}) {
    if (state.translationRequest || editingBusy()) return;
    const serial = ++state.translationSerial;
    state.translationRequest = true;
    state.translationFetching = false;
    clearTimeout(state.translationTimer);
    updateControls();
    try {
      const data = await publishPost(url, body);
      if (serial === state.translationSerial) acceptTranslation(data);
    } catch (error) {
      state.translationConnectionError = error.message || "The Bengali update setting could not be changed. Please try again.";
      renderTranslation();
    } finally { state.translationRequest = false; renderTranslation(); scheduleTranslationPoll(); }
  }
  async function checkBengaliDocument(force = false) {
    const owner = state.doc;
    if (!owner || owner.lang !== "bn" || state.bengaliFetching || editingBusy()) return;
    state.bengaliFetching = true;
    try {
      const latest = await request(`/api/document?id=${encodeURIComponent(owner.id)}&lang=bn`, { cache: "no-store" });
      if (state.doc !== owner || state.lang !== "bn") return;
      if (latest.version === owner.version) { state.bengaliReloadNeeded = null; return; }
      state.bengaliReloadNeeded = { id: owner.id, version: latest.version };
      const textInUse = ui.content.contains(document.activeElement);
      if (dirtyCount() || editingBusy() || ui.dialog.open || ui.publishDialog.open || contentDialogOpen() || (!force && textInUse)) return;
      const scrollY = window.scrollY;
      renderDocument(latest);
      window.scrollTo({ top: scrollY, behavior: "instant" });
      setStatus("The updated Bengali version is loaded. Your public website changes only when you publish.", "success");
    } catch {
      if (force) setStatus("The updated Bengali page could not be loaded. Your current text is still here; try again.", "error");
    } finally { state.bengaliFetching = false; updateControls(); }
  }
  ui.translationEnabled.addEventListener("change", () => changeTranslation("/api/translation/settings", { enabled: ui.translationEnabled.checked }));
  ui.translationRetry.addEventListener("click", () => state.translationConnectionError ? refreshTranslation() : changeTranslation("/api/translation/retry"));
  ui.translationAccept.addEventListener("click", () => {
    if (dirtyCount() || editingBusy() || state.translationRequest || state.lang !== "bn" || !(state.translation.reviewDocuments || []).some((page) => page.id === state.doc?.id)) return;
    if (window.confirm("Have you updated and checked the Bengali version of this page? This marks its current English changes as handled.")) changeTranslation("/api/translation/accept", { id: state.doc.id });
  });
  ui.translationReload.addEventListener("click", () => { if (!dirtyCount() && !editingBusy()) checkBengaliDocument(true); });
  function formatPublicationTime(value) {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? "Just now" : date.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
  }
  function noteLocalSourceSave() {
    // Keep a sent update's identity and polling when the author continues editing.
    // A prepared, unsent snapshot must be prepared again after any source save.
    state.savedSincePreparation = true;
    renderPublication();
    schedulePublicationPoll();
  }
  function setPublicationLink(element, value, label) {
    const target = EditorPublishing.githubLink(value);
    element.hidden = !target;
    if (target) element.href = target;
    else element.removeAttribute("href");
    if (label) element.textContent = label;
    return Boolean(target);
  }
  function renderPublication() {
    const { phase, preparation, publication, github = {} } = state.publication;
    const busy = publishingBusy();
    const remote = EditorPublishing.remoteBusy(phase);
    const ready = phase === "ready" && Boolean(preparation?.id);
    const success = phase === "success";
    const error = phase === "error";
    const closedWithoutMerge = state.publication.closedWithoutMerge === true;
    const canPrepareAgain = state.publication.canPrepare === true || closedWithoutMerge;
    const checkState = github.checks?.state;
    const reviewUrl = EditorPublishing.githubLink(github.pullRequestUrl);
    const compareUrl = EditorPublishing.githubLink(github.compareUrl);
    const titles = {
      idle: "Publish through GitHub", preparing: "Preparing your GitHub update", ready: "Ready to send to GitHub",
      publishing: "Sending your source to GitHub", review: reviewUrl ? "Review your GitHub update" : "Create your GitHub review",
      deploying: "Cloudflare is publishing", clean: "No new source changes", success: "Your update is live", error: "Publishing needs attention"
    };
    const messages = {
      idle: "Save your edits and preview both languages. Then prepare all saved website changes for GitHub.",
      preparing: "Building and checking your saved pages, then preparing the source update…",
      ready: "The saved source passed its checks. Review what is included before sending it to GitHub.",
      publishing: "Sending the checked source to an update branch on GitHub…",
      review: "Your source is on GitHub. Review and merge the pull request there to start automatic publishing.",
      deploying: "The change was merged. GitHub is running its production checks and publishing to Cloudflare…",
      clean: "Your saved source has no new changes to send to GitHub.",
      success: "GitHub confirmed a successful production deployment for this update.",
      error: "This update needs attention. Read the details, then check its status before starting another update."
    };
    ui.publishTitle.textContent = titles[phase] || titles.idle;
    if (success && state.savedSincePreparation) ui.publishTitle.textContent = "Earlier update is live";
    ui.publishMessage.textContent = state.publishConnectionError || state.publication.message || messages[phase] || messages.idle;
    if (ready && dirtyCount()) ui.publishMessage.textContent = "Save your unsaved edits, then prepare a fresh update before sending it.";
    else if (ready && state.savedSincePreparation) ui.publishMessage.textContent = "Your saved source changed after this preparation. Prepare the latest changes before sending them to GitHub.";
    else if (ready && translationBlocksPublication()) ui.publishMessage.textContent = translationPublishInstruction();
    ui.publishMessage.className = "publish-message" + (busy || phase === "deploying" ? " busy" : "") + (error || state.publishConnectionError ? " error" : "");
    ui.publishMessage.setAttribute("role", error || state.publishConnectionError ? "alert" : "status");
    const statusNotice = typeof state.publication.statusNotice === "string" ? state.publication.statusNotice : "";
    ui.publishStatusNotice.hidden = !statusNotice;
    ui.publishStatusNotice.textContent = statusNotice;
    const currentStep = ({ idle: 0, preparing: 1, ready: 1, publishing: 1, review: 2, deploying: 3, clean: 0, success: 4 })[phase] ?? (github.headSha ? 2 : 0);
    [...ui.publishSteps.children].forEach((item, index) => {
      item.dataset.state = index < currentStep ? "complete" : index === currentStep ? "current" : "pending";
      if (index === currentStep) item.setAttribute("aria-current", "step");
      else item.removeAttribute("aria-current");
    });
    ui.publishReview.hidden = !preparation || !["ready", "publishing", "review", "deploying", "success"].includes(phase);
    if (preparation) {
      const pages = Number(preparation.pages), files = Number(preparation.files);
      ui.publishCounts.textContent = `${Number.isFinite(pages) ? pages.toLocaleString() : "All"} pages · ${Number.isFinite(files) ? files.toLocaleString() : "all"} source files · English & Bengali`;
      ui.publishPrepared.textContent = formatPublicationTime(preparation.preparedAt);
      ui.publishBranch.textContent = preparation.branch || github.branch || "A new update branch";
      const changed = Array.isArray(preparation.changedFiles) ? preparation.changedFiles : [];
      ui.publishFilesPanel.hidden = !changed.length;
      ui.publishFiles.replaceChildren();
      for (const file of changed.slice(0, 100)) {
        const item = document.createElement("li");
        item.textContent = typeof file === "string" ? file : String(file?.path || "Changed source file");
        ui.publishFiles.append(item);
      }
      if (changed.length > 100) {
        const item = document.createElement("li");
        item.textContent = `And ${(changed.length - 100).toLocaleString()} more files. Review the complete change on GitHub.`;
        ui.publishFiles.append(item);
      }
    }
    ui.publishConfirm.hidden = !ready;
    ui.publishPrepare.hidden = !["idle", "clean", "success", "error"].includes(phase) && !(ready && state.savedSincePreparation) || Boolean(state.publication.uncertain) || (error && Boolean(github.headSha) && !canPrepareAgain);
    ui.publishPrepare.textContent = ready && state.savedSincePreparation ? "Prepare latest changes" : success ? "Prepare another update" : "Prepare GitHub update";
    ui.publishRetry.hidden = !(remote || error || state.publishConnectionError);
    ui.publishRetry.disabled = state.publishRequest || state.publishFetching;
    ui.publishRetry.textContent = state.publishConnectionError ? "Reconnect and check" : "Check progress";
    const hasReview = remote || (error && Boolean(github.headSha));
    const reviewLabel = closedWithoutMerge ? "View closed GitHub review" : !reviewUrl ? "Create review on GitHub" : checkState === "success" ? "Review and merge on GitHub" : "Open GitHub review";
    const hasReviewLink = setPublicationLink(ui.publishGithub, hasReview ? reviewUrl || compareUrl : "", reviewLabel);
    const hasChecksLink = setPublicationLink(ui.publishChecks, (remote || error || success) ? github.checks?.url || github.actionsUrl : "", "View GitHub checks");
    ui.publishHandoff.hidden = !remote && !hasReviewLink && !hasChecksLink;
    ui.publishNextStep.textContent = success
      ? "This update has already been deployed. Its GitHub checks remain available for reference. Prepare another update for new local changes."
      : closedWithoutMerge ? "That pull request was closed without merging. You can prepare a new update from your corrected saved source."
      : phase === "deploying"
      ? "Publishing runs automatically after merging. This panel will confirm when the same update is live."
      : !reviewUrl ? "On GitHub, choose Create pull request. Review the changes, wait for the required check to pass, then merge the pull request. You may need to sign in to GitHub."
      : checkState === "failure" ? "A GitHub check failed. Open the review to see the failure. This source update has not been confirmed live."
      : checkState === "success" ? "The checks passed. Review the changes on GitHub and choose Merge pull request when you are ready. Merging starts the automatic Cloudflare publication."
      : "Review the changes on GitHub while its checks run. Merge becomes available when the required checks pass.";
    ui.publishLive.hidden = !success || !EditorPublishing.siteLink(publication?.url);
    ui.publishLive.href = "https://aguri-heritage.in/";
    ui.publishDetail.textContent = ({
      idle: dirtyCount() ? "Your current page has unsaved edits. Close this panel, save, and preview them first." : translationBlocksPublication() ? translationPublishInstruction() : "Preparation includes all saved website changes, not only the page currently open.",
      preparing: "You can close this panel; checks continue while the editor app is running.",
      ready: "Send to GitHub uploads this checked source for review. The public website changes only after the pull request is merged and production checks pass.",
      publishing: "Keep the editor app running until the source send is confirmed. You can close this panel and return to View progress.",
      review: "The public website has not been confirmed updated. New local edits stay on this Mac for a later update.",
      deploying: "You can keep editing. New local edits are not part of this publication. Checks refresh automatically; GitHub links show the latest status.",
      clean: "This does not report a new deployment. Close the panel to continue editing.",
      success: `Confirmed ${formatPublicationTime(publication?.completedAt)}. New local edits need their own GitHub update.`,
      error: "Your saved local content is still here. Checking progress does not resend or merge an update."
    })[phase] || "";
    ui.publicationStatus.classList.toggle("publication-busy", busy || phase === "deploying");
    ui.publish.textContent = busy || remote || error ? "View progress" : ready ? "Continue publishing" : "Publish via GitHub";
    updateControls();
  }
  function acceptPublication(data) {
    if (!data || !EditorPublishing.phases.includes(data.phase)) throw new Error("The publishing status could not be read. Please check again.");
    if (data.preparation?.siteUrl && !EditorPublishing.siteLink(data.preparation.siteUrl)) throw new Error("The publishing destination does not match this website.");
    if (data.publication?.url && !EditorPublishing.siteLink(data.publication.url)) throw new Error("The published destination does not match this website.");
    for (const value of [data.github?.compareUrl, data.github?.pullRequestUrl, data.github?.actionsUrl, data.github?.checks?.url]) {
      if (value && !EditorPublishing.githubLink(value)) throw new Error("The GitHub review link does not match this project's repository.");
    }
    state.publication = data;
    state.publishConnectionError = "";
    renderPublication();
    schedulePublicationPoll();
  }
  function schedulePublicationPoll() {
    clearTimeout(state.publishTimer);
    state.publishTimer = null;
    const delay = EditorPublishing.pollDelay(state.publication.phase, Boolean(state.publishConnectionError));
    if (delay) state.publishTimer = setTimeout(refreshPublication, delay);
  }
  async function refreshPublication(manual = false) {
    if (state.publishFetching || state.publishRequest) { schedulePublicationPoll(); return; }
    const serial = state.publishSerial;
    state.publishFetching = true;
    try {
      const data = await request(manual === true ? "/api/publish/status?refresh=1" : "/api/publish/status", { headers: { "X-Editor-Token": token }, cache: "no-store" });
      if (serial === state.publishSerial) acceptPublication(data);
    } catch (error) {
      if (serial === state.publishSerial) {
        state.publishConnectionError = error.message || "Progress is unavailable. Keep this tab open and the editor app running, then reconnect.";
        renderPublication();
        schedulePublicationPoll();
      }
    } finally { state.publishFetching = false; renderPublication(); }
  }
  async function preparePublication() {
    if (sourceActionBlocked()) {
      if (dirtyCount()) setStatus("Save and preview your changes before preparing the GitHub update.");
      else if (translationBlocksPublication()) setStatus(translationPublishInstruction());
      renderPublication();
      return;
    }
    state.activeBlock?.blur();
    ++state.publishSerial;
    state.publishRequest = true;
    clearTimeout(state.publishTimer);
    state.publication = { phase: "preparing", message: "Checking all saved website changes for GitHub…" };
    state.savedSincePreparation = false;
    state.publishConnectionError = "";
    renderPublication();
    try {
      acceptPublication(await publishPost("/api/publish/prepare"));
    } catch (error) {
      state.publishConnectionError = error.message || "Preparation could not be confirmed. Check progress before trying again.";
      // Preserve the pending phase: a dropped response may have started the job.
    } finally {
      state.publishRequest = false;
      renderPublication();
      schedulePublicationPoll();
      if (state.publishConnectionError) await refreshPublication();
    }
  }
  async function confirmPublication() {
    const preparationId = state.publication.preparation?.id;
    if (state.publication.phase !== "ready" || !preparationId || state.savedSincePreparation || sourceActionBlocked()) return;
    ++state.publishSerial;
    state.publishRequest = true;
    clearTimeout(state.publishTimer);
    state.publication = { ...state.publication, phase: "publishing", message: "Sending the checked source to GitHub for review…" };
    state.publishConnectionError = "";
    renderPublication();
    try {
      acceptPublication(await publishPost("/api/publish/confirm", { preparationId }));
    } catch (error) {
      state.publishConnectionError = error.message || "The source send could not be confirmed. Check progress before trying again.";
    } finally {
      state.publishRequest = false;
      renderPublication();
      schedulePublicationPoll();
      if (state.publishConnectionError) await refreshPublication();
    }
  }
  ui.publish.addEventListener("click", () => {
    if (!ui.publishDialog.open) ui.publishDialog.showModal();
    renderPublication();
    refreshPublication(true);
  });
  ui.publishPrepare.addEventListener("click", preparePublication);
  ui.publishConfirm.addEventListener("click", confirmPublication);
  ui.publishRetry.addEventListener("click", () => refreshPublication(true));
  $("#publish-close").addEventListener("click", () => ui.publishDialog.close());
  ui.publishDialog.addEventListener("close", updateControls);
  function discardAllowed() {
    return !dirtyCount() || window.confirm("You have unsaved changes. Discard them and open different content?");
  }
  function setDialogStatus(element, message = "", kind = "") {
    element.textContent = message;
    element.hidden = !message;
    element.className = "dialog-status" + (kind ? ` ${kind}` : "");
    element.setAttribute("role", kind === "error" ? "alert" : "status");
    if (kind === "error" && element.closest("dialog").open) {
      element.tabIndex = -1;
      element.focus();
    }
  }
  function parseCatalog(data) {
    if (!Array.isArray(data.pages) || !Array.isArray(data.types) || !Array.isArray(data.sections)) {
      throw new Error("The page options could not be read. Reload the options and try again.");
    }
    const records = (items, label, field) => {
      const seen = new Set();
      return items.map((item) => {
        if (!item || typeof item !== "object" || typeof item.id !== "string" || !item.id.trim() ||
            typeof item[field] !== "string" || !item[field].trim() || seen.has(item.id)) {
          throw new Error(`The ${label} list could not be read. Reload the options and try again.`);
        }
        seen.add(item.id);
        return { ...item };
      });
    };
    const pages = records(data.pages, "pages", "title");
    const types = records(data.types, "page types", "name");
    const sections = records(data.sections, "website sections", "name");
    if (types.some((type) => !["article", "general", "biography"].includes(type.template))) {
      throw new Error("A page type has an unknown starting layout. Reload the options and try again.");
    }
    return { pages, types, sections };
  }
  function applyCatalog(catalog) {
    Object.assign(state, catalog, { catalogLoaded: true, catalogError: "" });
    renderList();
    renderPageOptions();
    ui.createRetry.hidden = true;
    ui.typesRetry.hidden = true;
    updateControls();
  }
  function renderPageOptions(selectedType = ui.newType.value) {
    const selectedSection = ui.newSection.value;
    const fill = (select, options, selected, empty) => {
      select.replaceChildren();
      if (!options.length) select.append(new Option(empty, ""));
      for (const option of options) select.append(new Option(option.name, option.id));
      if (options.some((option) => option.id === selected)) select.value = selected;
    };
    fill(ui.newType, state.types, selectedType, "No page types available");
    fill(ui.newSection, state.sections, selectedSection, "No website sections available");
    renderTypeDescription();
    ui.typesList.replaceChildren();
    if (!state.types.length) {
      const empty = document.createElement("p");
      empty.className = "field-help";
      empty.textContent = "No page types yet. Add the first one below.";
      ui.typesList.append(empty);
    }
    for (const type of state.types) {
      const item = document.createElement("div");
      item.className = "page-type-item";
      const name = document.createElement("strong");
      name.textContent = type.name;
      const layout = document.createElement("span");
      layout.textContent = ({ article: "Article", general: "General page", biography: "Biography" })[type.template];
      item.append(name, layout);
      if (typeof type.description === "string" && type.description.trim()) {
        const description = document.createElement("p");
        description.textContent = type.description;
        item.append(description);
      }
      ui.typesList.append(item);
    }
  }
  function renderTypeDescription() {
    const type = state.types.find((item) => item.id === ui.newType.value);
    ui.typeDescription.textContent = typeof type?.description === "string" ? type.description : "";
    ui.typeDescription.hidden = !ui.typeDescription.textContent;
  }
  async function refreshCatalog() {
    if (state.catalogFetching) return;
    state.catalogFetching = true;
    updateControls();
    if (ui.createDialog.open) setDialogStatus(ui.createStatus, "Loading page types and website sections…", "busy");
    if (ui.typesDialog.open) setDialogStatus(ui.typesStatus, "Loading your page types…", "busy");
    try {
      applyCatalog(parseCatalog(await request("/api/pages", { cache: "no-store" })));
      if (ui.createDialog.open) setDialogStatus(ui.createStatus, !state.sections.length ? "No website sections are available. Reload the options after checking the editor configuration." : !state.types.length ? "Add a page type to create your first page." : "", !state.sections.length ? "error" : "");
      if (!state.sections.length) ui.createRetry.hidden = false;
      if (ui.typesDialog.open) setDialogStatus(ui.typesStatus);
      return true;
    } catch (error) {
      state.catalogError = error.message || "The page options could not be loaded. Check that the local editor is running and try again.";
      ui.createRetry.hidden = false;
      ui.typesRetry.hidden = false;
      if (ui.createDialog.open) setDialogStatus(ui.createStatus, state.catalogError, "error");
      if (ui.typesDialog.open) setDialogStatus(ui.typesStatus, state.catalogError, "error");
      setStatus(state.catalogError, "error");
      return false;
    } finally { state.catalogFetching = false; updateControls(); }
  }
  function openCreateDialog() {
    if (editingBusy()) return;
    setDialogStatus(ui.createStatus);
    renderPageOptions();
    ui.createDialog.showModal();
    if (!state.catalogLoaded || state.catalogError) refreshCatalog();
    else if (!state.sections.length) { setDialogStatus(ui.createStatus, "No website sections are available. Reload the options after checking the editor configuration.", "error"); ui.createRetry.hidden = false; }
    else if (!state.types.length) setDialogStatus(ui.createStatus, "Add a page type to create your first page.");
    else ui.newType.focus();
  }
  function openTypesDialog() {
    if (editingBusy()) return;
    setDialogStatus(ui.typesStatus);
    renderPageOptions();
    ui.typesDialog.showModal();
    if (!state.catalogLoaded || state.catalogError) refreshCatalog();
    else $("#new-type-name").focus();
  }
  function slugFromTitle(title) {
    return title.normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 80).replace(/-+$/g, "");
  }
  function formValues(form) {
    const values = Object.fromEntries(new FormData(form));
    for (const key of Object.keys(values)) values[key] = values[key].trim();
    return values;
  }
  function requireFormText(form, values, status) {
    for (const field of form.querySelectorAll("input[required], textarea[required], select[required]")) {
      if (!values[field.name]) {
        setDialogStatus(status, "Complete each field before continuing.", "error");
        field.focus();
        return false;
      }
    }
    return true;
  }
  function validateCreatedDocument(doc, pages, lang) {
    if (!doc || typeof doc.id !== "string" || !doc.id || typeof doc.title !== "string" || doc.lang !== lang ||
        !Array.isArray(doc.blocks) || !doc.blocks.length || doc.blocks.some((block) => !block || block.id == null || typeof block.html !== "string") ||
        (doc.images != null && (!Array.isArray(doc.images) || doc.images.some((image) => !image || image.id == null || typeof image.src !== "string"))) ||
        (doc.order != null && (!Array.isArray(doc.order) || doc.order.some((entry) => !entry || entry.id == null || !["block", "image"].includes(entry.type)))) ||
        !pages.some((page) => page.id === doc.id)) {
      throw new Error("The page may have been saved, but its content could not be opened. Your current edits are still here. Reload the page options to check for the new page before trying again.");
    }
  }
  function resetPublicationAfterCreation() {
    noteLocalSourceSave();
  }
  ui.addPage.addEventListener("click", openCreateDialog);
  ui.pageTypes.addEventListener("click", openTypesDialog);
  ui.createAddType.addEventListener("click", openTypesDialog);
  ui.newType.addEventListener("change", renderTypeDescription);
  ui.newTitle.addEventListener("input", () => { if (!state.slugEdited) ui.newSlug.value = slugFromTitle(ui.newTitle.value); });
  ui.newSlug.addEventListener("input", () => { state.slugEdited = ui.newSlug.value !== slugFromTitle(ui.newTitle.value); });
  ui.createRetry.addEventListener("click", () => { if (!editingBusy()) refreshCatalog(); });
  ui.typesRetry.addEventListener("click", () => { if (!editingBusy()) refreshCatalog(); });
  ui.createCancel.addEventListener("click", () => { if (!state.creating) ui.createDialog.close(); });
  ui.typesCancel.addEventListener("click", () => { if (!state.creatingType) ui.typesDialog.close(); });
  ui.createDialog.addEventListener("cancel", (event) => { if (state.creating) event.preventDefault(); });
  ui.typesDialog.addEventListener("cancel", (event) => { if (state.creatingType) event.preventDefault(); });
  ui.createDialog.addEventListener("close", updateControls);
  ui.typesDialog.addEventListener("close", () => {
    updateControls();
    if (ui.createDialog.open) ui.newType.focus();
  });
  ui.createForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (editingBusy() || !state.catalogLoaded || !ui.createForm.reportValidity()) return;
    const values = formValues(ui.createForm);
    if (!requireFormText(ui.createForm, values, ui.createStatus)) return;
    if (!state.types.some((type) => type.id === values.type) || !state.sections.some((section) => section.id === values.section)) {
      setDialogStatus(ui.createStatus, "Choose an available page type and website section.", "error");
      return;
    }
    if (!discardAllowed()) return;
    const lang = state.lang;
    state.activeBlock?.blur();
    state.creating = true;
    updateControls();
    setDialogStatus(ui.createStatus, "Creating and checking your English and Bengali pages…", "busy");
    try {
      const data = await publishPost("/api/pages/create", { ...values, lang });
      const catalog = parseCatalog(data);
      validateCreatedDocument(data.document, catalog.pages, lang);
      applyCatalog(catalog);
      ui.search.value = "";
      renderDocument(data.document);
      resetPublicationAfterCreation();
      ui.createDialog.close();
      ui.createForm.reset();
      state.slugEdited = false;
      renderPageOptions();
      setStatus(data.message || "Page created and saved on this computer. Add your content, Preview it, then Publish when you’re ready.", "success");
      ui.title.tabIndex = -1;
      ui.title.focus();
      window.scrollTo({ top: 0, behavior: "instant" });
      await refreshTranslation(true);
    } catch (error) {
      setDialogStatus(ui.createStatus, error.message || "The page could not be created. Your form details and current page edits are still here; please try again.", "error");
      ui.createRetry.hidden = false;
    } finally { state.creating = false; updateControls(); }
  });
  ui.typesForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (editingBusy() || !state.catalogLoaded || !ui.typesForm.reportValidity()) return;
    const values = formValues(ui.typesForm);
    if (!requireFormText(ui.typesForm, values, ui.typesStatus)) return;
    if (state.types.some((type) => type.name.toLocaleLowerCase() === values.name.toLocaleLowerCase())) {
      setDialogStatus(ui.typesStatus, "A page type with this name already exists. Choose a different name.", "error");
      $("#new-type-name").focus();
      return;
    }
    state.creatingType = true;
    updateControls();
    setDialogStatus(ui.typesStatus, "Saving your new page type…", "busy");
    try {
      const data = await publishPost("/api/page-types/create", values);
      const catalog = parseCatalog(data);
      const addedType = catalog.types.find((type) => type.name.toLocaleLowerCase() === values.name.toLocaleLowerCase());
      if (!addedType) throw new Error("The page type may have been saved, but it could not be loaded. Reload the options before trying again.");
      applyCatalog(catalog);
      renderPageOptions(addedType.id);
      resetPublicationAfterCreation();
      ui.typesDialog.close();
      ui.typesForm.reset();
      if (ui.createDialog.open) setDialogStatus(ui.createStatus, `“${addedType.name}” is ready and selected for this page.`, "success");
      else setStatus(data.message || "Page type saved on this computer. Choose Add page to use it.", "success");
    } catch (error) {
      setDialogStatus(ui.typesStatus, error.message || "The page type could not be saved. Your details are still here; please try again.", "error");
      ui.typesRetry.hidden = false;
    } finally { state.creatingType = false; updateControls(); if (ui.createDialog.open && !ui.typesDialog.open) ui.newType.focus(); }
  });
  function renderList() {
    ui.list.replaceChildren();
    const query = ui.search.value.trim().toLocaleLowerCase();
    const filtered = state.pages.filter((page) => `${page.title} ${page.id} ${page.typeName || ""}`.toLocaleLowerCase().includes(query));
    if (!filtered.length) {
      const empty = document.createElement("p");
      empty.className = "sidebar-message";
      empty.textContent = query ? "No matching content. Try a different name." : "No editable pages were found.";
      ui.list.append(empty);
      return;
    }
    for (const [kind, label] of [["profile", "People & biographies"], ["page", "Website pages"]]) {
      const pages = filtered.filter((page) => (page.kind === "profile" ? "profile" : "page") === kind);
      if (!pages.length) continue;
      const group = document.createElement("section");
      group.className = "list-group";
      const heading = document.createElement("h2");
      heading.className = "list-heading";
      heading.append(document.createTextNode(label));
      const number = document.createElement("span");
      number.textContent = pages.length;
      heading.append(number);
      group.append(heading);
      for (const page of pages) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "page-item";
        const dot = document.createElement("span");
        dot.className = "page-dot";
        dot.setAttribute("aria-hidden", "true");
        const title = document.createElement("span");
        title.textContent = page.title;
        title.className = "page-item-label";
        const typeName = page.typeName || state.types.find((type) => type.id === page.type)?.name;
        if (typeName) {
          const type = document.createElement("small");
          type.textContent = typeName;
          title.append(type);
        }
        button.append(dot, title);
        if (page.id === state.doc?.id) {
          button.classList.add("active");
          button.setAttribute("aria-current", "page");
        }
        button.addEventListener("click", () => {
          if (editingBusy() || page.id === state.doc?.id) return;
          if (discardAllowed()) loadDocument(page.id, state.lang);
        });
        group.append(button);
      }
      ui.list.append(group);
    }
  }
  function blockKind(block) {
    if (state.insertedBlocks.has(String(block.id))) return "New text block";
    const tag = String(block.tag || "p").toLowerCase();
    if (/^h[1-6]$/.test(tag)) return "Heading";
    return ({ li: "List item", figcaption: "Photo caption", td: "Table text", th: "Table heading" })[tag] || "Text block";
  }
  function optionLabel(id, index) {
    const block = state.blocks.get(id);
    const meta = state.blockMeta.get(id) || state.insertedBlocks.get(id) || { id, tag: "p" };
    const text = block?.textContent.replace(/\s+/g, " ").trim() || "Empty text";
    return `${index}. ${blockRemoved(id) ? "Removed · " : ""}${blockKind(meta)} — ${text.slice(0, 65)}${text.length > 65 ? "…" : ""}`;
  }
  function updateBlockOption(id) {
    const option = [...ui.blockSelect.options].find((item) => item.value === id);
    if (option) option.textContent = optionLabel(id, [...ui.blockSelect.options].indexOf(option));
  }
  function refreshBlockNavigation() {
    const activeId = state.activeBlock?.dataset.blockId || ui.blockSelect.value;
    ui.blockSelect.replaceChildren(new Option("Choose a block…", ""));
    const wrappers = [...ui.content.querySelectorAll(".content-block")].filter(wrapper => !wrapper.hidden);
    wrappers.forEach((wrapper, index) => {
      const id = wrapper.dataset.blockWrapper;
      ui.blockSelect.add(new Option(optionLabel(id, index + 1), id));
      wrapper.querySelector(".block-label").textContent = `${index + 1} · ${blockKind(state.blockMeta.get(id) || state.insertedBlocks.get(id) || { id })}`;
    });
    if ([...ui.blockSelect.options].some((option) => option.value === activeId)) ui.blockSelect.value = activeId;
  }
  function selectBlock(id, focus = true) {
    const element = state.blocks.get(id);
    const wrapper = state.blockWrappers.get(id);
    if (!element || !wrapper) return;
    ui.content.querySelectorAll(".content-block.selected").forEach((item) => item.classList.remove("selected"));
    wrapper.classList.add("selected");
    ui.blockSelect.value = id;
    if (blockRemoved(id)) {
      state.activeBlock = null;
      state.selection = null;
      if (focus) wrapper.querySelector(".block-restore").focus();
    } else {
      state.activeBlock = element;
      if (focus) element.focus();
    }
    updateControls();
  }
  function findInsertionTarget() {
    const activeId = state.activeBlock?.dataset.blockId;
    const addition = state.insertedBlocks.get(activeId);
    if (addition) return { anchor: addition.anchor, position: addition.position, afterNew: activeId };
    const active = state.blockMeta.get(activeId);
    if (active && !blockRemoved(activeId)) {
      if (active.canInsertAfter) return { anchor: activeId, position: "after" };
      if (active.canInsertBefore) return { anchor: activeId, position: "before" };
    }
    for (const [id, meta] of state.blockMeta) {
      if (blockRemoved(id)) continue;
      if (meta.canInsertBefore) return { anchor: id, position: "before" };
      if (meta.canInsertAfter) return { anchor: id, position: "after" };
    }
    if (state.doc?.insertionTarget) return { anchor: state.doc.insertionTarget.id, position: state.doc.insertionTarget.position };
    if (state.doc && state.blockMeta.size && [...state.blockMeta.keys()].every(blockRemoved)) return { anchor: "document-end", position: "after" };
    return null;
  }
  function placeInsertedBlock(wrapper, insertion, afterNew = null) {
    const anchor = state.blockWrappers.get(insertion.anchor);
    const after = afterNew && state.blockWrappers.get(afterNew);
    if (after?.isConnected) { after.after(wrapper); return; }
    if (!anchor) { if (insertion.anchor === "document-end") ui.content.append(wrapper); return; }
    if (insertion.position === "before") { anchor.before(wrapper); return; }
    let last = anchor;
    while (last.nextElementSibling?.dataset.insertionAnchor === insertion.anchor && last.nextElementSibling.dataset.insertionPosition === "after") last = last.nextElementSibling;
    last.after(wrapper);
  }
  function structuralChange(label, undo) {
    state.blockHistory.push({ label, undo });
    state.structuralUndoPending = true;
    refreshBlockNavigation();
    updateControls();
  }
  function undoBlockChange() {
    if (editingBusy() || !state.blockHistory.length) return;
    const change = state.blockHistory.pop();
    change.undo();
    state.structuralUndoPending = Boolean(state.blockHistory.length);
    refreshBlockNavigation();
    updateControls();
    setStatus(`${change.label} undone. ${dirtyCount() ? "Save when you’re ready." : "No unsaved changes."}`);
  }
  function setBlockDeleted(id, deleted) {
    const wrapper = state.blockWrappers.get(id);
    const block = state.blocks.get(id);
    if (!wrapper || !block) return;
    if (deleted) state.deletedBlocks.add(id);
    else state.deletedBlocks.delete(id);
    wrapper.classList.toggle("removed", deleted);
    block.hidden = deleted;
    block.inert = deleted;
    wrapper.querySelector(".block-controls").hidden = deleted;
    wrapper.querySelector(".block-tombstone").hidden = !deleted;
    if (state.activeBlock === block) {
      state.activeBlock = null;
      state.selection = null;
      window.getSelection()?.removeAllRanges();
    }
    selectBlock(id);
  }
  function deleteBlock(id) {
    if (editingBusy() || !state.blockMeta.get(id)?.canDelete || state.deletedBlocks.has(id)) return;
    setBlockDeleted(id, true);
    structuralChange("Block removal", () => setBlockDeleted(id, false));
    setStatus("Text block removed. Restore it here or use Undo before saving.");
  }
  function restoreBlock(id) {
    if (editingBusy() || !state.deletedBlocks.has(id)) return;
    setBlockDeleted(id, false);
    structuralChange("Block restoration", () => setBlockDeleted(id, true));
    setStatus("Text block restored. Your text edits have been kept.");
  }
  function detachNewBlock(id) {
    const wrapper = state.blockWrappers.get(id);
    const element = state.blocks.get(id);
    const data = state.insertedBlocks.get(id);
    if (!wrapper || !element || !data) return null;
    const snapshot = { wrapper, element, data, next: wrapper.nextSibling };
    if (state.activeBlock === element) {
      state.activeBlock = null;
      state.selection = null;
      window.getSelection()?.removeAllRanges();
    }
    wrapper.remove();
    state.insertedBlocks.delete(id);
    state.blocks.delete(id);
    state.blockWrappers.delete(id);
    state.blockOriginals.delete(id);
    state.changedBlocks.delete(id);
    state.blockFormats.delete(id);
    return snapshot;
  }
  function restoreNewBlock(snapshot) {
    if (!snapshot) return;
    const { wrapper, element, data, next } = snapshot;
    state.insertedBlocks.set(data.id, data);
    state.blocks.set(data.id, element);
    state.blockWrappers.set(data.id, wrapper);
    if (next?.parentNode === ui.content) ui.content.insertBefore(wrapper, next);
    else placeInsertedBlock(wrapper, data);
    selectBlock(data.id);
  }
  function removeNewBlock(id) {
    if (editingBusy() || !state.insertedBlocks.has(id)) return;
    const snapshot = detachNewBlock(id);
    structuralChange("New block removal", () => restoreNewBlock(snapshot));
    ui.undoBlock.focus();
    setStatus("New text block removed. Undo block change can bring it back before you save.");
  }
  function addTextBlock(target = findInsertionTarget()) {
    if (editingBusy() || !target) return;
    const anchor = state.blockMeta.get(target.anchor);
    if (target.anchor !== "document-end" && (!anchor || !(target.position === "before" ? anchor.canInsertBefore : anchor.canInsertAfter))) return;
    const id = `new-${crypto.randomUUID()}`;
    const insertion = { id, anchor: target.anchor, position: target.position, tag: "p", html: "", format: { align: "" } };
    ui.content.querySelector(".empty-content-note")?.remove();
    state.insertedBlocks.set(id, insertion);
    const wrapper = makeBlock(insertion, true);
    wrapper.dataset.newBlock = "true";
    wrapper.dataset.insertionAnchor = insertion.anchor;
    wrapper.dataset.insertionPosition = insertion.position;
    placeInsertedBlock(wrapper, insertion, target.afterNew);
    structuralChange("Text block addition", () => detachNewBlock(id));
    selectBlock(id);
    wrapper.scrollIntoView({ block: "nearest", behavior: "smooth" });
    setStatus("New text block added. Type your paragraph, then save.");
  }
  function serializedInsertions() {
    return [...ui.content.querySelectorAll('.content-block[data-new-block="true"]')].map((wrapper) => {
      const id = wrapper.dataset.blockWrapper;
      return { ...state.insertedBlocks.get(id), html: state.blocks.get(id).innerHTML };
    });
  }
  ui.addTextBlock.addEventListener("click", () => addTextBlock());
  ui.undoBlock.addEventListener("click", undoBlockChange);
  ui.blockSelect.addEventListener("change", () => {
    if (editingBusy()) return;
    const id = ui.blockSelect.value;
    selectBlock(id);
    state.blockWrappers.get(id)?.scrollIntoView({ block: "center", behavior: "smooth" });
  });
  function updateEmptyBlock(block) {
    // Keep the browser's filler <br> intact so clearing text stays undoable.
    block.classList.toggle("is-empty", !block.textContent.trim() && !block.querySelector(".editor-citation"));
  }
  function removeCitation(citation, block) {
    if (editingBusy() || !citation.isConnected) return;
    block.focus();
    state.activeBlock = block;
    const range = document.createRange();
    range.selectNode(citation);
    const selection = window.getSelection();
    selection.removeAllRanges();
    selection.addRange(range);
    // Native deletion keeps the badge in the same undo history as text edits.
    document.execCommand("delete");
    markChanged(block);
    rememberSelection();
    if (!citation.isConnected) setStatus("Source reference removed. Undo can restore it; Save will renumber the remaining references.");
  }
  function makeBlock(block, isNew = false) {
    const id = String(block.id);
    const wrapper = document.createElement("section");
    wrapper.className = "content-block" + (isNew ? " new-block" : "");
    wrapper.dataset.blockWrapper = id;
    const controls = document.createElement("div");
    controls.className = "block-controls";
    const label = document.createElement("span");
    label.className = "block-label";
    label.textContent = blockKind(block);
    const actions = document.createElement("div");
    actions.className = "block-actions";
    function action(text, handler, className = "") {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "block-action " + className;
      button.textContent = text;
      button.addEventListener("click", handler);
      actions.append(button);
      return button;
    }
    if (isNew) action("Remove new block", () => removeNewBlock(id), "block-delete");
    else {
      state.blockMeta.set(id, block);
      if (block.canInsertBefore) action("+ Add above", () => addTextBlock({ anchor: id, position: "before" }));
      if (block.canInsertAfter) action("+ Add below", () => addTextBlock({ anchor: id, position: "after" }));
      if (block.canDelete) action("Delete block", () => deleteBlock(id), "block-delete");
      else if (block.deleteReason) {
        const note = document.createElement("span");
        note.className = "block-protected";
        note.textContent = "Text only";
        note.title = block.deleteReason;
        actions.append(note);
      }
    }
    controls.append(label, actions);
    wrapper.append(controls);
    const requested = String(block.tag || "p").toUpperCase();
    const element = document.createElement(allowedTags.has(requested) ? requested.toLowerCase() : "div");
    element.className = "editable-block";
    element.dataset.blockId = id;
    element.contentEditable = "true";
    element.spellcheck = true;
    element.setAttribute("role", "textbox");
    element.setAttribute("aria-multiline", "true");
    element.setAttribute("aria-label", `${/^H[1-6]$/.test(requested) ? "Heading" : "Text"}: click to edit`);
    element.innerHTML = block.html || "";
    const align = EditorContent.alignment(block.format?.align);
    element.style.textAlign = align;
    if (!isNew) state.formatOriginals.set(id, align);
    element.querySelectorAll(".editor-citation").forEach((citation) => {
      citation.contentEditable = "false";
      citation.tabIndex = 0;
      citation.setAttribute("role", "button");
      const source = citation.title;
      citation.setAttribute("aria-label", `Remove source reference ${citation.textContent.trim()}${source ? `: ${source}` : ""}`);
      citation.title = `${source ? `${source} — ` : ""}Click to remove this reference. Undo can restore it.`;
    });
    updateEmptyBlock(element);
    element.addEventListener("input", () => markChanged(element));
    element.addEventListener("focus", () => { selectBlock(id, false); });
    // Delegate events so citation badges restored by native Undo remain usable.
    element.addEventListener("click", (event) => {
      const citation = event.target.closest?.(".editor-citation");
      if (!citation || !element.contains(citation)) return;
      event.preventDefault();
      removeCitation(citation, element);
    });
    element.addEventListener("keydown", (event) => {
      const citation = event.target.closest?.(".editor-citation");
      if (citation && ["Enter", " ", "Backspace", "Delete"].includes(event.key) && !event.isComposing) {
        event.preventDefault();
        removeCitation(citation, element);
        return;
      }
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "a" && !event.altKey && !event.isComposing) {
        event.preventDefault();
        element.focus();
        state.activeBlock = element;
        const range = document.createRange();
        range.selectNodeContents(element);
        const selection = window.getSelection();
        selection.removeAllRanges();
        selection.addRange(range);
        rememberSelection();
        return;
      }
      if (event.key === "Enter" && !event.isComposing) {
        event.preventDefault();
        document.execCommand("insertLineBreak");
        markChanged(element);
      }
    });
    element.addEventListener("paste", (event) => {
      event.preventDefault();
      const text = event.clipboardData?.getData("text/plain") || "";
      const holder = document.createElement("div");
      holder.textContent = text;
      document.execCommand("insertHTML", false, holder.innerHTML.replace(/\r\n|\r|\n/g, "<br>"));
      markChanged(element);
    });
    element.addEventListener("drop", (event) => event.preventDefault());
    state.blocks.set(id, element);
    if (!isNew) state.blockOriginals.set(id, element.innerHTML);
    state.blockWrappers.set(id, wrapper);
    wrapper.append(element);
    if (!isNew) {
      const tombstone = document.createElement("div");
      tombstone.className = "block-tombstone";
      tombstone.hidden = true;
      const message = document.createElement("span");
      message.textContent = "Text block removed";
      const restore = document.createElement("button");
      restore.type = "button";
      restore.className = "block-restore";
      restore.textContent = "Restore";
      restore.addEventListener("click", () => restoreBlock(id));
      tombstone.append(message, restore);
      wrapper.append(tombstone);
    }
    return wrapper;
  }
  function setImageDeleted(id, deleted) {
    const figure = state.imageWrappers.get(id);
    if (!figure) return;
    if (deleted) state.deletedImages.add(id); else state.deletedImages.delete(id);
    figure.classList.toggle("removed", deleted);
    for (const child of figure.children) child.hidden = child.classList.contains("image-tombstone") ? !deleted : deleted;
    const automatic = new Set();
    for (const image of state.deletedImages) for (const child of state.imageMeta.get(image)?.deleteBlockIds || []) automatic.add(String(child));
    for (const [blockId, wrapper] of state.blockWrappers) {
      wrapper.hidden = automatic.has(blockId);
      if (automatic.has(blockId) && state.activeBlock === state.blocks.get(blockId)) {
        state.activeBlock = null; state.selection = null; window.getSelection()?.removeAllRanges();
      }
    }
    refreshBlockNavigation();
    updateControls();
  }
  function deleteImage(id) {
    if (editingBusy() || state.deletedImages.has(id) || !state.imageMeta.get(id)?.canDelete) return;
    setImageDeleted(id, true);
    structuralChange("Photo removal", () => setImageDeleted(id, false));
    setStatus("Photo and its attached caption removed. Restore or Undo keeps your unsaved edits.");
  }
  function restoreImage(id) {
    if (editingBusy() || !state.deletedImages.has(id)) return;
    setImageDeleted(id, false);
    structuralChange("Photo restoration", () => setImageDeleted(id, true));
    setStatus("Photo restored with its caption and your unsaved edits.");
  }
  function makeImage(image) {
    const id = String(image.id);
    const figure = document.createElement("figure");
    figure.className = "image-card";
    figure.dataset.imageId = id;
    state.imageMeta.set(id, image);
    state.imageWrappers.set(id, figure);
    const stage = document.createElement("div");
    stage.className = "image-stage";
    const photo = document.createElement("img");
    photo.src = image.src;
    photo.alt = image.alt || "";
    stage.append(photo);
    const controls = document.createElement("div");
    controls.className = "image-controls";
    const photoLabel = document.createElement("span");
    photoLabel.className = "photo-label";
    photoLabel.textContent = "Profile / page image";
    const imageStatus = document.createElement("span");
    imageStatus.className = "image-status";
    photoLabel.append(imageStatus);
    const replace = document.createElement("button");
    replace.className = "button button-secondary";
    replace.type = "button";
    replace.textContent = "Replace photo";
    const file = document.createElement("input");
    file.type = "file";
    file.accept = "image/jpeg,image/png,image/webp";
    file.hidden = true;
    replace.addEventListener("click", () => { if (!editingBusy() && !state.deletedImages.has(id)) file.click(); });
    const description = document.createElement("label");
    description.className = "image-description";
    description.textContent = "Image description · for accessibility";
    const alt = document.createElement("input");
    alt.type = "text";
    alt.value = image.alt || "";
    alt.placeholder = "Describe what the photo shows";
    description.append(alt);
    state.imageOriginals.set(id, { alt: image.alt || "", src: image.src });
    function trackImage() {
      state.structuralUndoPending = false;
      let changes = state.imageChanges.get(id) || {};
      if (alt.value !== state.imageOriginals.get(id).alt) changes.alt = alt.value;
      else delete changes.alt;
      if (Object.keys(changes).length) state.imageChanges.set(id, changes);
      else state.imageChanges.delete(id);
      figure.classList.toggle("dirty", state.imageChanges.has(id));
      photo.alt = alt.value;
      imageStatus.textContent = changes.dataUrl ? "New photo · not saved" : "";
      updateControls();
      setStatus(dirtyCount() ? "You have unsaved changes. Save when you’re ready." : "All changes saved on this computer.");
    }
    alt.addEventListener("input", trackImage);
    file.addEventListener("change", async () => {
      const selected = file.files?.[0];
      file.value = "";
      if (!selected) return;
      if (!["image/jpeg", "image/png", "image/webp"].includes(selected.type)) {
        setStatus("Choose a JPEG, PNG or WebP image.", "error");
        return;
      }
      if (selected.size > 10 * 1024 * 1024) {
        setStatus("This photo is too large. Choose an image smaller than 10 MB.", "error");
        return;
      }
      const owner = state.doc;
      state.readingImage = true;
      updateControls();
      setStatus("Opening your selected photo…", "busy");
      try {
        const dataUrl = await new Promise((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = () => resolve(reader.result);
          reader.onerror = () => reject(new Error("The photo could not be read. Please choose it again."));
          reader.readAsDataURL(selected);
        });
        if (state.doc !== owner) return;
        const decoded = new Image();
        decoded.src = dataUrl;
        await decoded.decode();
        if (state.doc !== owner) return;
        state.imageChanges.set(id, { ...(state.imageChanges.get(id) || {}), dataUrl });
        photo.src = dataUrl;
        trackImage();
      } catch { setStatus("This photo could not be opened. Please choose a valid JPEG, PNG or WebP image.", "error"); }
      finally { state.readingImage = false; updateControls(); }
    });
    controls.append(photoLabel, replace, file);
    if (image.canDelete) {
      const remove = document.createElement("button");
      remove.type = "button"; remove.className = "block-action block-delete"; remove.textContent = "Delete photo";
      remove.addEventListener("click", () => deleteImage(id));
      controls.append(remove);
    }
    figure.append(stage, controls, description);
    if (image.caption) {
      const caption = document.createElement("figcaption");
      caption.textContent = image.caption;
      figure.append(caption);
    }
    const tombstone = document.createElement("div");
    tombstone.className = "block-tombstone image-tombstone"; tombstone.hidden = true;
    const removed = document.createElement("span"); removed.textContent = "Photo removed";
    const restore = document.createElement("button"); restore.type = "button"; restore.className = "block-restore"; restore.textContent = "Restore photo";
    restore.addEventListener("click", () => restoreImage(id)); tombstone.append(removed, restore); figure.append(tombstone);
    return figure;
  }
  function renderDocument(doc) {
    state.doc = doc;
    state.lang = doc.lang;
    if (doc.lang !== "bn" || state.bengaliReloadNeeded?.id !== doc.id || state.bengaliReloadNeeded?.version === doc.version) state.bengaliReloadNeeded = null;
    state.changedBlocks.clear();
    state.imageChanges.clear();
    state.imageMeta.clear();
    state.imageWrappers.clear();
    state.deletedImages.clear();
    state.blockFormats.clear();
    state.formatOriginals.clear();
    state.blocks.clear();
    state.blockOriginals.clear();
    state.blockMeta.clear();
    state.blockWrappers.clear();
    state.deletedBlocks.clear();
    state.insertedBlocks.clear();
    state.blockHistory = [];
    state.structuralUndoPending = false;
    state.imageOriginals.clear();
    state.activeBlock = null;
    state.selection = null;
    ui.title.textContent = doc.title;
    const editingNotice = $("#editing-notice");
    editingNotice.textContent = typeof doc.editingNotice === "string" ? doc.editingNotice : "";
    editingNotice.hidden = !editingNotice.textContent;
    const kind = state.pages.find((page) => page.id === doc.id)?.kind === "profile" ? "PROFILE" : "WEBSITE PAGE";
    const page = state.pages.find((item) => item.id === doc.id);
    const typeName = page?.typeName || state.types.find((type) => type.id === page?.type)?.name;
    ui.eyebrow.textContent = `${typeName ? typeName.toLocaleUpperCase() : kind} · ${doc.lang === "bn" ? "বাংলা" : "ENGLISH"}`;
    ui.title.lang = doc.lang;
    ui.content.lang = doc.lang;
    ui.content.replaceChildren();
    const blocks = new Map((doc.blocks || []).map((block) => [String(block.id), block]));
    const images = new Map((doc.images || []).map((image) => [String(image.id), image]));
    const order = doc.order?.length ? doc.order : [...images.keys()].map((id) => ({ type: "image", id })).concat([...blocks.keys()].map((id) => ({ type: "block", id })));
    const rendered = new Set();
    for (const entry of order) {
      const id = String(entry.id);
      const key = `${entry.type}:${id}`;
      if (rendered.has(key)) continue;
      if (entry.type === "image" && images.has(id)) ui.content.append(makeImage(images.get(id)));
      else if (entry.type === "block" && blocks.has(id)) ui.content.append(makeBlock(blocks.get(id)));
      rendered.add(key);
    }
    if (!ui.content.children.length) {
      const note = document.createElement("p");
      note.className = "empty-content-note";
      note.textContent = doc.insertionTarget ? "This page is empty. Choose Add text block to begin." : "This page has no editable text or photos.";
      ui.content.append(note);
    }
    ui.heading.hidden = false;
    ui.panel.hidden = false;
    ui.empty.hidden = true;
    renderList();
    refreshBlockNavigation();
    updateControls();
  }
  async function loadDocument(id, lang) {
    const loadId = ++state.loadId;
    state.loading = true;
    updateControls();
    setStatus("Opening content…", "busy");
    try {
      const doc = await request(`/api/document?id=${encodeURIComponent(id)}&lang=${encodeURIComponent(lang)}`);
      if (loadId !== state.loadId) return;
      renderDocument(doc);
      setStatus("Ready to edit. Your public website changes only when you publish.");
      window.scrollTo({ top: 0, behavior: "instant" });
    } catch (error) {
      if (loadId !== state.loadId) return;
      setStatus(error.message || "Could not open this content. Please try again.", "error");
      if (!state.doc) ui.empty.hidden = false;
    } finally {
      if (loadId === state.loadId) {
        state.loading = false;
        updateControls();
        if (state.lang === "bn" && state.translation.phase === "success") checkBengaliDocument();
      }
    }
  }
  async function save() {
    if (editingBusy() || !state.doc || !dirtyCount()) return;
    const emptyAddition = [...state.insertedBlocks.keys()].find((id) => {
      const text = state.blocks.get(id).cloneNode(true);
      text.querySelectorAll(".editor-citation").forEach((citation) => citation.remove());
      return !text.textContent.trim();
    });
    if (emptyAddition) {
      selectBlock(emptyAddition);
      state.blockWrappers.get(emptyAddition).scrollIntoView({ block: "center", behavior: "smooth" });
      setStatus("Write some text in the new block, or choose Remove new block before saving.", "error");
      return;
    }
    state.saving = true;
    state.activeBlock?.blur();
    updateControls();
    const shortcut = ui.save.querySelector(".shortcut");
    ui.save.firstChild.textContent = "Saving… ";
    if (shortcut) shortcut.hidden = true;
    setStatus("Saving your changes, rebuilding the website and checking links…", "busy");
    try {
      const data = await request("/api/save", {
        method: "POST", headers: { "Content-Type": "application/json", "X-Editor-Token": token },
        body: JSON.stringify({
          id: state.doc.id, lang: state.lang, version: state.doc.version,
          ...EditorContent.saveFields(state, serializedInsertions())
        })
      });
      if (!data.document) throw new Error("Your changes were submitted, but the updated content could not be loaded. Reopen this page before editing further.");
      renderDocument(data.document);
      noteLocalSourceSave();
      setStatus(data.message || "Saved on this computer. The website build and checks passed.", "success");
      await refreshTranslation(true);
    } catch (error) { setStatus(error.message || "Could not save. Your edits are still here; please try again.", "error"); }
    finally {
      state.saving = false;
      ui.save.firstChild.textContent = "Save changes ";
      if (shortcut) shortcut.hidden = false;
      updateControls();
      if (state.lang === "bn" && state.translation.phase === "success") checkBengaliDocument();
    }
  }
  function rememberSelection() {
    const selection = window.getSelection();
    if (!selection?.rangeCount) { state.selection = null; updateFormattingControls(); return; }
    const range = selection.getRangeAt(0);
    const node = range.commonAncestorContainer.nodeType === Node.ELEMENT_NODE ? range.commonAncestorContainer : range.commonAncestorContainer.parentElement;
    const block = node?.closest?.(".editable-block");
    if (!block || !ui.content.contains(block) || blockRemoved(block.dataset.blockId) || !EditorContent.validRange(range, block)) {
      if (node && ui.content.contains(node)) { state.selection = null; updateFormattingControls(); }
      return;
    }
    state.activeBlock = block;
    state.selection = range.cloneRange();
    updateFormattingControls();
  }
  function restoreSelection() {
    if (!EditorContent.validRange(state.selection, state.activeBlock) || blockRemoved(state.activeBlock.dataset.blockId)) return false;
    state.activeBlock.focus();
    const selection = window.getSelection();
    selection.removeAllRanges();
    selection.addRange(state.selection);
    return true;
  }
  function formattingSelection() {
    if (!restoreSelection() || state.selection.collapsed) {
      setStatus("Select words within one text block first."); return false;
    }
    const range = state.selection, block = state.activeBlock;
    for (const endpoint of [range.startContainer, range.endContainer]) {
      const element = endpoint.nodeType === 1 ? endpoint : endpoint.parentElement;
      if (element?.closest?.(".editor-citation")) { setStatus("Select the words beside a source reference to format them."); return false; }
    }
    const before = document.createRange(); before.selectNodeContents(block); before.setEnd(range.startContainer, range.startOffset);
    const start = before.toString().length, end = start + range.toString().length;
    if (EditorContent.splitsGeneratedField(block.textContent, start, end)) {
      setStatus("Keep a generated field together when selecting words to format."); return false;
    }
    return true;
  }
  function updateFormattingControls() {
    const block = state.activeBlock, id = block?.dataset.blockId;
    const available = Boolean(block?.isConnected && !blockRemoved(id) && !editingBusy());
    const selected = available && EditorContent.validRange(state.selection, block) && !state.selection.collapsed;
    const standaloneLink = state.blockMeta.get(id)?.tag === "a";
    document.querySelectorAll("[data-command]").forEach(button => {
      button.disabled = !selected;
      let pressed = false;
      try { pressed = selected && Boolean(document.queryCommandState?.(button.dataset.command)); } catch {}
      button.setAttribute("aria-pressed", String(pressed));
    });
    for (const selector of ["#link-button", "#unlink-button", "#clear-format-button"]) {
      const button = $(selector);
      button.disabled = !selected || (selector !== "#clear-format-button" && standaloneLink);
      if (selector === "#link-button") button.title = standaloneLink ? "This text is already a page link; its destination stays attached to the block." : "Add or edit a link";
    }
    document.querySelectorAll("[data-align]").forEach(button => {
      button.disabled = !available;
      const current = block?.style?.textAlign || "left";
      button.setAttribute("aria-pressed", String(available && current === button.dataset.align));
    });
  }
  function setBlockAlignment(id, value) {
    const block = state.blocks.get(id);
    if (!block || blockRemoved(id)) return;
    const align = EditorContent.alignment(value);
    block.style.textAlign = align;
    if (state.insertedBlocks.has(id)) state.insertedBlocks.get(id).format = { align };
    else if (align !== state.formatOriginals.get(id)) state.blockFormats.set(id, { align });
    else state.blockFormats.delete(id);
    block.classList.toggle("dirty", state.insertedBlocks.has(id) || state.changedBlocks.has(id) || state.blockFormats.has(id));
    updateControls();
  }
  function clearSelectedFormatting(mode) {
    if (editingBusy() || !formattingSelection()) return;
    if (mode === "unlink" && state.blockMeta.get(state.activeBlock.dataset.blockId)?.tag === "a") {
      setStatus("This whole block is a page link. Its destination stays attached to the block."); return;
    }
    const block = state.activeBlock, html = EditorContent.clearedSelectionHTML(block, state.selection, mode);
    if (html === null) return;
    const range = document.createRange(); range.selectNodeContents(block);
    const selection = window.getSelection(); selection.removeAllRanges(); selection.addRange(range);
    // One native replacement retains the browser's text Undo history.
    document.execCommand("insertHTML", false, html);
    markChanged(block); rememberSelection();
    setStatus(mode === "unlink" ? "Selected link removed. Text and references are kept." : "Selected formatting cleared. Links, references and language are kept.");
  }
  document.addEventListener("selectionchange", rememberSelection);
  document.querySelectorAll("[data-command]").forEach((button) => {
    button.addEventListener("mousedown", (event) => event.preventDefault());
    button.addEventListener("click", () => {
      if (editingBusy()) return;
      if (!formattingSelection()) return;
      document.execCommand("styleWithCSS", false, false);
      document.execCommand(button.dataset.command);
      markChanged(state.activeBlock);
      rememberSelection();
    });
  });
  for (const [selector, mode] of [["#clear-format-button", "clear"], ["#unlink-button", "unlink"]]) {
    $(selector).addEventListener("mousedown", event => event.preventDefault());
    $(selector).addEventListener("click", () => clearSelectedFormatting(mode));
  }
  document.querySelectorAll("[data-align]").forEach(button => {
    button.addEventListener("mousedown", event => event.preventDefault());
    button.addEventListener("click", () => {
      const block = state.activeBlock;
      if (editingBusy() || !block?.isConnected || blockRemoved(block.dataset.blockId)) return;
      const id = block.dataset.blockId, before = block.style.textAlign || "";
      if (before === button.dataset.align) return;
      setBlockAlignment(id, button.dataset.align);
      structuralChange("Alignment change", () => setBlockAlignment(id, before));
      setStatus("Block alignment updated. Save when you’re ready.");
    });
  });
  $("#undo-button").addEventListener("mousedown", (event) => event.preventDefault());
  $("#undo-button").addEventListener("click", () => {
    if (!editingBusy() && state.structuralUndoPending && state.blockHistory.length) { undoBlockChange(); return; }
    if (editingBusy() || !restoreSelection()) return;
    document.execCommand("undo");
    for (const [id, block] of state.blocks) if (!blockRemoved(id)) markChanged(block);
    rememberSelection();
  });
  $("#link-button").addEventListener("mousedown", (event) => event.preventDefault());
  $("#link-button").addEventListener("click", () => {
    if (editingBusy()) return;
    if (!formattingSelection()) return;
    if (state.blockMeta.get(state.activeBlock.dataset.blockId)?.tag === "a") {
      setStatus("This whole block is already a page link. Select words in a different text block to add a link."); return;
    }
    const node = state.selection.startContainer.nodeType === Node.ELEMENT_NODE ? state.selection.startContainer : state.selection.startContainer.parentElement;
    ui.linkUrl.value = node?.closest?.("a")?.getAttribute("href") || "";
    ui.linkError.hidden = true;
    ui.dialog.showModal();
    ui.linkUrl.focus();
  });
  $("#link-cancel").addEventListener("click", () => { ui.dialog.close(); restoreSelection(); });
  $("#link-form").addEventListener("submit", (event) => {
    event.preventDefault();
    let url = ui.linkUrl.value.trim();
    if (/^[\w.+-]+@[\w.-]+\.[a-z]{2,}$/i.test(url)) url = `mailto:${url}`;
    else if (/^[\w.-]+\.[a-z]{2,}(?:[/:?#]|$)/i.test(url)) url = `https://${url}`;
    if (!/^(https?:\/\/|mailto:|#|\/(?!\/))/i.test(url) || /[\u0000-\u0020]/.test(url)) {
      ui.linkError.textContent = "Enter a web address beginning with https://, an email address, or a link within this website.";
      ui.linkError.hidden = false;
      return;
    }
    ui.dialog.close();
    if (formattingSelection() && state.blockMeta.get(state.activeBlock.dataset.blockId)?.tag !== "a") {
      document.execCommand("createLink", false, url);
      markChanged(state.activeBlock);
      rememberSelection();
    }
  });
  ui.search.addEventListener("input", renderList);
  document.querySelectorAll(".language").forEach((button) => button.addEventListener("click", () => {
    const lang = button.dataset.lang;
    if (editingBusy() || lang === state.lang || !state.doc) return;
    if (discardAllowed()) loadDocument(state.doc.id, lang);
  }));
  ui.save.addEventListener("click", save);
  ui.reset.addEventListener("click", () => {
    if (!state.doc || editingBusy()) return;
    if (window.confirm("Discard all unsaved changes to this page?")) {
      renderDocument(state.doc);
      setStatus("Unsaved changes discarded. Showing the last saved version.");
    }
  });
  ui.preview.addEventListener("click", () => {
    if (!state.doc || editingBusy()) return;
    if (dirtyCount() && !window.confirm("Preview shows the last saved version. Your unsaved edits will stay here. Open the preview?")) return;
    const target = new URL(state.doc.preview, window.location.origin);
    if (target.origin !== window.location.origin) { setStatus("The preview address must be on this local website.", "error"); return; }
    window.open(target.href, "_blank", "noopener,noreferrer");
  });
  document.addEventListener("keydown", (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "z" && !event.shiftKey && state.structuralUndoPending && state.blockHistory.length && !editingBusy() && !ui.dialog.open && !ui.publishDialog.open && !contentDialogOpen() && (ui.content.contains(document.activeElement) || ui.blockSelect === document.activeElement || ui.undoBlock === document.activeElement || ui.addTextBlock === document.activeElement)) {
      event.preventDefault();
      undoBlockChange();
      return;
    }
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "s") {
      event.preventDefault();
      if (!ui.dialog.open && !ui.publishDialog.open && !contentDialogOpen()) save();
    }
  });
  window.addEventListener("beforeunload", (event) => {
    if (dirtyCount() || state.saving || state.readingImage || state.creating || state.creatingType || publishingBusy() || state.publishRequest) { event.preventDefault(); event.returnValue = ""; }
  });
  async function init() {
    setStatus("Finding your website pages…", "busy");
    await Promise.all([refreshPublication(), refreshTranslation()]);
    if (publishingBusy()) { ui.publishDialog.showModal(); renderPublication(); }
    try {
      if (!await refreshCatalog()) { ui.empty.hidden = false; return; }
      const first = state.pages.find((page) => /konar/i.test(`${page.id} ${page.title}`)) || state.pages.find((page) => page.kind === "profile") || state.pages[0];
      if (first) await loadDocument(first.id, "en");
      else { setStatus("No editable content was found."); ui.empty.hidden = false; }
    } catch (error) {
      setStatus(error.message || "The local editor could not connect. Check that it is running and reload this page.", "error");
      ui.list.replaceChildren();
      ui.empty.hidden = false;
    }
  }
  init();
})();
