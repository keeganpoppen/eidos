// Real rendered acceptance over 1,000 synthetic saved owners and exact A→B→C sources.
// Start saved_work_scale_demo.py --serve, Vite :5173, and an isolated
// Chromium profile with --remote-debugging-port=9222. No dispatch/model calls.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';

const fixturePath = process.env.NEMA_SAVED_WORK_FIXTURE ?? 'docs/evidence/SAVED_WORK_SCALE_SYNTHETIC_2026_10_13.json';
const prefix = process.env.NEMA_SAVED_WORK_UI_PREFIX ?? 'docs/evidence/saved_work_ui_2026_10_13';
const fixture = JSON.parse(await fs.readFile(fixturePath, 'utf8'));
const origin = process.env.NEMA_UI_ORIGIN ?? 'http://127.0.0.1:5173';
const debuggerOrigin = process.env.NEMA_DEBUG_ORIGIN ?? 'http://127.0.0.1:9222';
const apiOrigin = process.env.NEMA_API_ORIGIN ?? 'http://127.0.0.1:8765';
const runTitle = `D · Saved-work browser exact-source composition ${crypto.randomUUID().slice(0, 8)}`;
const target = await (await fetch(`${debuggerOrigin}/json/new?about:blank`, { method: 'PUT' })).json();
const socket = new WebSocket(target.webSocketDebuggerUrl);
await new Promise(resolve => socket.addEventListener('open', resolve, { once: true }));
let sequence = 0;
let loads = 0;
const pending = new Map();
const requests = [];
const exceptions = [];
const byRequest = new Map();
const bodyReads = [];
let loseNextSaveReply = false;
let failNextOwnerRead = '';
let lostSaveReply = false;
let failedOwnerRead = false;
socket.addEventListener('message', event => {
  const message = JSON.parse(event.data);
  if (message.method === 'Page.loadEventFired') loads++;
  if (message.method === 'Runtime.exceptionThrown') exceptions.push(message.params.exceptionDetails);
  if (message.method === 'Network.requestWillBeSent') {
    const request = message.params.request;
    const path = new URL(request.url).pathname;
    if (path.startsWith('/api/')) {
      const entry = { method: request.method, path, query: new URL(request.url).search, body: request.postData };
      requests.push(entry); byRequest.set(message.params.requestId, entry);
    }
  }
  if (message.method === 'Network.responseReceived') {
    const entry = byRequest.get(message.params.requestId);
    if (entry) { entry.status = message.params.response.status; entry.headers = message.params.response.headers; }
  }
  if (message.method === 'Network.loadingFinished') {
    const entry = byRequest.get(message.params.requestId);
    if (entry) bodyReads.push(rpc('Network.getResponseBody', {requestId: message.params.requestId}).then(value => {
      const body = value.base64Encoded ? Buffer.from(value.body, 'base64') : Buffer.from(value.body);
      entry.bodyBytes = body.length;
      try { entry.response = JSON.parse(body.toString()); } catch { /* Non-JSON failures stay visible in status. */ }
    }).catch(() => {}));
  }
  if (message.method === 'Fetch.requestPaused') {
    const paused = message.params;
    const path = new URL(paused.request.url).pathname;
    if (loseNextSaveReply && paused.responseStatusCode && paused.request.method === 'POST' && path === '/api/investigations') {
      loseNextSaveReply = false; lostSaveReply = true;
      void rpc('Fetch.failRequest', {requestId: paused.requestId, errorReason: 'Failed'});
    } else if (failNextOwnerRead && !paused.responseStatusCode && path === `/api/investigations/${failNextOwnerRead}/view`) {
      failNextOwnerRead = ''; failedOwnerRead = true;
      void rpc('Fetch.failRequest', {requestId: paused.requestId, errorReason: 'Failed'});
    } else void rpc('Fetch.continueRequest', {requestId: paused.requestId});
  }
  if (!message.id) return;
  const request = pending.get(message.id);
  pending.delete(message.id);
  message.error ? request.reject(Error(JSON.stringify(message.error))) : request.resolve(message.result);
});
const rpc = (method, params = {}) => new Promise((resolve, reject) => {
  const id = ++sequence;
  pending.set(id, { resolve, reject });
  socket.send(JSON.stringify({ id, method, params }));
});
const evaluate = async expression => {
  const result = await rpc('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true });
  if (result.exceptionDetails) throw Error(JSON.stringify(result.exceptionDetails));
  return result.result.value;
};
const wait = async expression => {
  for (let attempt = 0; attempt < 100; attempt++) {
    if (await evaluate(expression)) return;
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  throw Error(`Rendered condition did not arrive: ${expression}`);
};
const click = async selector => {
  await wait(`document.querySelector(${JSON.stringify(selector)}) && !document.querySelector(${JSON.stringify(selector)}).disabled`);
  await evaluate(`document.querySelector(${JSON.stringify(selector)}).click()`);
};
const clickText = async (text, root = 'document') => {
  const expression = `[...${root}.querySelectorAll('button')].find(e => e.textContent.trim() === ${JSON.stringify(text)} && !e.disabled)`;
  await wait(`!!(${expression})`);
  await evaluate(`(${expression}).click()`);
};
const fill = async (selector, value) => evaluate(`(() => {
  const input = document.querySelector(${JSON.stringify(selector)});
  if (!input) throw Error('Missing input');
  input.value = ${JSON.stringify(value)};
  input.dispatchEvent(new Event('input', {bubbles: true}));
})()`);
const select = async (selector, value) => {
  await wait(`[...document.querySelector(${JSON.stringify(selector)})?.options ?? []].some(option => option.value === ${JSON.stringify(value)})`);
  await evaluate(`(() => {
    const input = document.querySelector(${JSON.stringify(selector)});
    input.value = ${JSON.stringify(value)}; input.dispatchEvent(new Event('change', {bubbles: true}));
  })()`);
};
const screenshot = async name => {
  await evaluate('new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))');
  await fs.writeFile(`${prefix}_${name}.png`, Buffer.from((await rpc('Page.captureScreenshot', { format: 'png' })).data, 'base64'));
};
const get = async path => {
  const response = await fetch(apiOrigin + '/api/investigations' + path);
  const value = await response.json();
  assert(response.ok, JSON.stringify(value));
  return value;
};
const draftIdentity = () => evaluate(`JSON.stringify({selected: document.querySelector('#saved-investigation').value,
  title: document.querySelector('#investigation-title').value, question: document.querySelector('#investigation-question').value,
  preview: document.querySelector('#context-revision')?.value,
  results: [...document.querySelectorAll('[data-selected-artifact-id]')].map(e => ({id: e.dataset.selectedArtifactId, rationale: e.querySelector('input').value}))})`);
const lineageRoot = "document.querySelector('.artifact-lineage[open]')";
const reachable = async selector => {
  await evaluate(`document.querySelector(${JSON.stringify(selector)}).scrollIntoView({block: 'center', inline: 'nearest'})`);
  await evaluate('new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))');
  const bounds = await evaluate(`(() => {
    const element = document.querySelector(${JSON.stringify(selector)});
    const rect = element.getBoundingClientRect();
    const hit = document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2);
    return {left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom,
      viewportWidth: innerWidth, viewportHeight: innerHeight,
      hit: element === hit || element.contains(hit), disabled: !!element.disabled};
  })()`);
  assert(bounds.left >= 0 && bounds.right <= bounds.viewportWidth + 1 && bounds.top >= 0 && bounds.bottom <= bounds.viewportHeight, JSON.stringify(bounds));
  assert(bounds.hit && !bounds.disabled, JSON.stringify(bounds));
  return bounds;
};

const pickerRoot = id => `document.querySelector(${JSON.stringify(id)}).closest('.catalog-picker')`;
const search = async (id, text) => {
  await fill(id + '-search', text);
  await clickText('Search', pickerRoot(id));
  await wait(`document.querySelector(${JSON.stringify(id)}).getAttribute('aria-busy') === 'false'`);
};
const reload = async () => {
  const before = loads;
  await rpc('Page.reload', {ignoreCache: true});
  for (let attempt = 0; attempt < 100 && loads === before; attempt++) await new Promise(resolve => setTimeout(resolve, 100));
  assert(loads > before, 'Reload did not complete');
  await wait("!!document.querySelector('#saved-investigation')");
};
const browserDraft = () => evaluate("JSON.parse(localStorage.getItem('nema.investigation-draft.v1'))");
const pinState = () => evaluate("JSON.stringify(JSON.parse(localStorage.getItem('nema.composition.v1'))?.arrangement)");
const overflow = () => evaluate(`({width: innerWidth, document: document.documentElement.scrollWidth - innerWidth,
  dialogs: [...document.querySelectorAll('.artifact-lineage[open]')].map(e => e.scrollWidth - e.clientWidth),
  pickers: [...document.querySelectorAll('.catalog-picker')].filter(e => e.getBoundingClientRect().width > 0).map(e => e.scrollWidth - e.clientWidth)})`);

try {
  await Promise.all([rpc('Page.enable'), rpc('Runtime.enable'), rpc('Network.enable')]);
  await rpc('Fetch.enable', {patterns: [{urlPattern: '*/api/investigations*', requestStage: 'Request'}, {urlPattern: '*/api/investigations*', requestStage: 'Response'}]});
  await rpc('Emulation.setDeviceMetricsOverride', {width: 1600, height: 1100, deviceScaleFactor: 1, mobile: false});
  await rpc('Storage.clearDataForOrigin', {origin, storageTypes: 'local_storage'});
  await rpc('Page.navigate', {url: origin});
  await wait("document.querySelector('#saved-investigation')?.options.length === 21");
  await clickText('Investigation');
  assert.equal(await evaluate(`[...document.querySelector('#saved-investigation').options].some(e => e.value === ${JSON.stringify(fixture.investigations.A)})`), false);
  const firstPage = await evaluate("[...document.querySelector('#saved-investigation').options].map(e => e.value)");
  await clickText('Next page', pickerRoot('#saved-investigation'));
  await wait(`${pickerRoot('#saved-investigation')}.textContent.includes('Page 2')`);
  const secondPage = await evaluate("[...document.querySelector('#saved-investigation').options].map(e => e.value).filter(Boolean)");
  assert(secondPage.every(id => !firstPage.includes(id)));
  await clickText('Previous page', pickerRoot('#saved-investigation'));
  await wait(`${pickerRoot('#saved-investigation')}.textContent.includes('Page 1')`);
  assert.deepEqual(await evaluate("[...document.querySelector('#saved-investigation').options].map(e => e.value)"), firstPage);

  // Search result selection remains pinned when its catalog page changes.
  await search('#context-artifact-picker', 'STRASSE');
  await select('#context-artifact-picker', JSON.stringify([fixture.investigations.A, fixture.artifacts.A]));
  await search('#context-artifact-picker', 'Synthetic archive');
  assert.equal(await evaluate("document.querySelector('#context-artifact-picker').value"), JSON.stringify([fixture.investigations.A, fixture.artifacts.A]));
  await clickText('Add selected result to context');
  await fill('#investigation-title', runTitle);
  await fill('#investigation-question', 'Which original decision controls retry, and which claims remain inferred?');
  const dirtyBeforeInspection = await draftIdentity();
  await click(`[data-selected-artifact-id="${fixture.artifacts.A}"] .source-link`);
  await wait(`!!document.querySelector('[data-lineage-artifact-id="${fixture.artifacts.A}"]')`);
  await clickText('Close result provenance', lineageRoot);
  assert.equal(await draftIdentity(), dirtyBeforeInspection);

  // Server commits the save, then the browser loses only its response. Reload
  // and retry must reuse the persisted request ID rather than create another D.
  loseNextSaveReply = true;
  await clickText('Save and preview context');
  await wait("!!document.querySelector('.work-error') && !!JSON.parse(localStorage.getItem('nema.investigation-draft.v1'))?.pendingRequest");
  assert(lostSaveReply);
  const pending = await browserDraft();
  assert(pending.pendingRequest?.id);
  await reload();
  await wait(`document.querySelector('#investigation-title')?.value === ${JSON.stringify(pending.title)}`);
  assert.deepEqual((await browserDraft()).pendingRequest, pending.pendingRequest);
  await clickText('Save and preview context');
  await wait("!!document.querySelector('#saved-investigation').value && !!document.querySelector('.context-preview')");
  const draftId = await evaluate("document.querySelector('#saved-investigation').value");
  const saved = (await get('/' + draftId + '/view')).investigation;
  const exactA = await get(`/${fixture.investigations.A}/artifacts/${fixture.artifacts.A}/source?contextId=${fixture.contexts.A}`);
  assert.deepEqual(saved.contexts[0].artifactInputs[0].artifact, exactA.artifact);
  assert.equal(saved.contexts[0].artifactInputs[0].sourceAttemptManifestId, exactA.attempt.manifestId);
  assert.equal(saved.attempt, null);
  assert.equal((await get('/catalog?q=' + encodeURIComponent(runTitle))).investigations.length, 1);

  await fill('#investigation-question', 'Revision two adds the source chain without changing the first saved packet.');
  await search('#context-artifact-picker', 'Old chain · C');
  await select('#context-artifact-picker', JSON.stringify([fixture.investigations.C, fixture.artifacts.C]));
  await clickText('Add selected result to context');
  await clickText('Save context revision');
  await wait("document.querySelector('#context-revision')?.options.length === 2");
  const revised = (await get('/' + draftId + '/view')).investigation;
  assert.deepEqual(revised.contexts[0], saved.contexts[0]);
  await select('#context-revision', saved.currentContextId);
  await fill('#investigation-question', 'UNSAVED: retain this wording while inspecting older work and reloading.');
  await fill(`[data-selected-artifact-id="${fixture.artifacts.A}"] input`, 'UNSAVED rationale stays with this exact result.');
  const dirty = await draftIdentity();

  // Exact source hops do not select their owners or replace the dirty draft.
  const lineageStart = requests.length;
  await click(`[data-selected-artifact-id="${fixture.artifacts.C}"] .source-link`);
  const hops = [];
  for (const name of ['C', 'B', 'A']) {
    await wait(`document.querySelector('[data-lineage-artifact-id="${fixture.artifacts[name]}"]')?.dataset.lineageContextId === ${JSON.stringify(fixture.contexts[name])}`);
    hops.push({name, investigationId: fixture.investigations[name], artifactId: fixture.artifacts[name], contextId: fixture.contexts[name]});
    if (name !== 'A') await click(`.artifact-lineage[open] .lineage-input[data-artifact-id="${fixture.artifacts[name === 'C' ? 'B' : 'A']}"]`);
  }
  const record = `.artifact-lineage[open] [data-evidence-seq="${fixture.controllingSeq}"]`;
  await evaluate(`document.querySelector(${JSON.stringify(record)}).closest('details').open = true`);
  await click(`${record} .raw-evidence summary`);
  await wait(`!!document.querySelector(${JSON.stringify(record + ' .raw-evidence pre')})`);
  assert.equal(await evaluate(`document.querySelector(${JSON.stringify(record + ' .raw-evidence pre')}).textContent`), fixture.controllingRawRecord.rawText);
  await evaluate(`${lineageRoot}.scrollTop = 0`);
  await screenshot('desktop_lineage');
  await clickText('Back to previous result', lineageRoot);
  await clickText('Close result provenance', lineageRoot);
  assert.equal(await draftIdentity(), dirty);
  assert(!requests.slice(lineageStart).some(e => /\/investigation_[^/]+\/view$/.test(e.path) && !e.path.includes(draftId)));

  // Bind exact comparison targets through searched catalogs; editing its search
  // and page must not advance either context or artifact pin.
  await clickText('Compare saved work');
  await wait("!!document.querySelector('#compare-left')");
  await search('#compare-left', 'STRASSE');
  await select('#compare-left', fixture.investigations.A);
  await wait(`document.querySelector('#compare-left-context')?.value === ${JSON.stringify(fixture.contexts.A)}`);
  await search('#compare-right', 'Old chain · C');
  await select('#compare-right', fixture.investigations.C);
  await wait(`document.querySelector('#compare-right-context')?.value === ${JSON.stringify(fixture.contexts.C)}`);
  await clickText('Review arrangement');
  await clickText('Apply arrangement');
  const pins = await pinState();
  assert(JSON.parse(pins).left.artifactId === fixture.artifacts.A && JSON.parse(pins).right.artifactId === fixture.artifacts.C);
  await clickText('Edit arrangement');
  await search('#compare-left', 'Synthetic archive');
  await clickText('Next page', pickerRoot('#compare-left'));
  await wait(`${pickerRoot('#compare-left')}.textContent.includes('Page 2')`);
  assert.equal(await evaluate("document.querySelector('#compare-left').value"), fixture.investigations.A);
  assert.equal(await pinState(), pins);
  await clickText('Cancel changes');
  await screenshot('desktop_comparison');
  await clickText('Return to investigation');
  assert.equal(await draftIdentity(), dirty);
  await reload();
  await wait(`document.querySelector('#saved-investigation')?.value === ${JSON.stringify(draftId)} && !!document.querySelector('#context-revision')`);
  assert.equal(await draftIdentity(), dirty);
  assert.equal(await pinState(), pins);

  // Narrow viewport: old-result search, selected option, and source navigation
  // remain readable/reachable without document or picker horizontal overflow.
  await rpc('Emulation.setDeviceMetricsOverride', {width: 390, height: 844, deviceScaleFactor: 1, mobile: true});
  await clickText('Investigation');
  await search('#context-artifact-picker', 'STRASSE');
  await select('#context-artifact-picker', JSON.stringify([fixture.investigations.A, fixture.artifacts.A]));
  const mobilePickerBounds = await reachable('#context-artifact-picker');
  const mobilePickerOverflow = await overflow();
  assert.equal(mobilePickerOverflow.width, 390);
  assert(mobilePickerOverflow.document <= 1 && mobilePickerOverflow.pickers.every(v => v <= 1), JSON.stringify(mobilePickerOverflow));
  await screenshot('mobile_picker');
  await click(`[data-selected-artifact-id="${fixture.artifacts.C}"] .source-link`);
  await wait(`!!document.querySelector('[data-lineage-artifact-id="${fixture.artifacts.C}"]')`);
  await click(`.artifact-lineage[open] .lineage-input[data-artifact-id="${fixture.artifacts.B}"]`);
  await wait(`!!document.querySelector('[data-lineage-artifact-id="${fixture.artifacts.B}"]')`);
  await click(`.artifact-lineage[open] .lineage-input[data-artifact-id="${fixture.artifacts.A}"]`);
  await wait(`!!document.querySelector('[data-lineage-artifact-id="${fixture.artifacts.A}"]')`);
  await evaluate(`${lineageRoot}.scrollTop = 0`);
  const mobileDialogOverflow = await overflow();
  assert(mobileDialogOverflow.document <= 1 && mobileDialogOverflow.dialogs.every(v => v <= 1), JSON.stringify(mobileDialogOverflow));
  await screenshot('mobile_lineage');
  await clickText('Back to previous result', lineageRoot);
  await clickText('Close result provenance', lineageRoot);
  assert.equal(await draftIdentity(), dirty);
  await reload();
  await wait(`document.querySelector('#saved-investigation')?.value === ${JSON.stringify(draftId)} && !!document.querySelector('#context-revision')`);
  assert.equal(await draftIdentity(), dirty);
  assert.equal(await pinState(), pins);

  // Explicit selection failure cannot leave the previous draft actionable under
  // the new owner ID. Retry then resolves exactly the requested saved owner.
  await search('#saved-investigation', 'Old chain · B');
  failNextOwnerRead = fixture.investigations.B;
  await select('#saved-investigation', fixture.investigations.B);
  await wait("[...document.querySelectorAll('button')].some(e => e.textContent.trim() === 'Retry selected investigation')");
  assert(failedOwnerRead);
  assert.equal(await evaluate("[...document.querySelectorAll('button')].some(e => ['Save and preview context','Save context revision'].includes(e.textContent.trim()) && !e.disabled)"), false);
  await clickText('Retry selected investigation');
  await wait(`!!document.querySelector('[data-result-artifact-id="${fixture.artifacts.B}"]')`);
  assert.equal(await evaluate("document.querySelector('#saved-investigation').value"), fixture.investigations.B);

  // Imported browser arrangements can retain missing owners. Their bounded
  // pickers must still be available so an explicit edit can repair the pins.
  await evaluate(`(() => {
    const state = JSON.parse(localStorage.getItem('nema.composition.v1'));
    state.open = true;
    state.arrangement = {...state.arrangement,
      left: {investigationId: 'investigation_missing_saved_work_left', contextId: 'context_missing_left', artifactId: 'artifact_missing_left'},
      right: {investigationId: 'investigation_missing_saved_work_right', contextId: 'context_missing_right', artifactId: 'artifact_missing_right'}};
    localStorage.setItem('nema.composition.v1', JSON.stringify(state));
  })()`);
  await reload();
  await wait("!!document.querySelector('.comparison-surface') || [...document.querySelectorAll('button')].some(e => e.textContent.trim() === 'Edit arrangement')");
  await clickText('Edit arrangement');
  await wait("!!document.querySelector('#compare-left-search') && !!document.querySelector('#compare-right-search')");
  assert.equal(await evaluate("document.querySelector('#compare-left-context').value"), 'context_missing_left');
  await search('#compare-left', 'STRASSE');
  await select('#compare-left', fixture.investigations.A);
  await wait(`document.querySelector('#compare-left-context').value === ${JSON.stringify(fixture.contexts.A)}`);
  await search('#compare-right', 'Old chain · C');
  await select('#compare-right', fixture.investigations.C);
  await wait(`document.querySelector('#compare-right-context').value === ${JSON.stringify(fixture.contexts.C)}`);
  await clickText('Review arrangement');
  await clickText('Apply arrangement');
  assert.equal(await pinState(), pins);
  await new Promise(resolve => setTimeout(resolve, 1800));
  await Promise.allSettled(bodyReads);

  const reads = requests.filter(e => e.method === 'GET' && e.path.startsWith('/api/investigations'));
  assert(!reads.some(e => e.path === '/api/investigations'), 'UI fetched full saved-work catalog');
  assert(!reads.some(e => /^\/api\/investigations\/investigation_[^/]+$/.test(e.path)), 'UI fetched legacy full owner route');
  const details = reads.filter(e => e.path.endsWith('/source') && e.response);
  assert(details.length >= 3 && details.every(e => e.response.context && e.response.artifact && e.response.attempt && !e.response.contexts && !e.response.artifactHistory));
  const idle = reads.filter(e => e.path.endsWith('/view') && e.response?.unchanged);
  assert(idle.length && idle.every(e => e.bodyBytes < 150));
  const posts = requests.filter(e => e.method === 'POST');
  assert.equal(posts.filter(e => e.path === '/api/investigations').length, 2);
  const saves = posts.filter(e => e.path === '/api/investigations').map(e => JSON.parse(e.body));
  assert.deepEqual(saves[0], saves[1]);
  assert(posts.every(e => e.path === '/api/investigations' || e.path === `/api/investigations/${draftId}/contexts`));
  assert.equal(exceptions.length, 0, JSON.stringify(exceptions));
  const final = (await get('/' + draftId + '/view')).investigation;
  assert.deepEqual(final, revised);
  const evidence = {schemaVersion: 'nema-saved-work-rendered/1', classification: 'SYNTHETIC_REAL_BROWSER', seededOwners: fixture.owners,
    nativeOrModelCalls: 0, outOfPageExactResultComposed: fixture.artifacts.A, composedInvestigationId: draftId,
    lostSaveResponseRetriedSameRequestId: pending.pendingRequest.id, duplicateSavedOwners: 0,
    dirtyDraftPreservedThroughLineageComparisonReload: true, historicalPreviewPreserved: saved.currentContextId,
    comparisonPins: JSON.parse(pins), failedSelectionRetriedExactOwner: fixture.investigations.B,
    missingComparisonOwnersRepairedByExplicitSelection: true,
    originalRawEvidenceRecovered: true, lineage: hops, fullCatalogGets: 0, legacyOwnerGets: 0,
    mobilePickerBounds, mobilePickerOverflow, mobileDialogOverflow,
    sourceResponses: details.map(e => ({path: e.path, query: e.query, bodyBytes: e.bodyBytes})),
    selectedViewResponses: reads.filter(e => e.path.endsWith('/view') && e.response).map(e => ({path: e.path, query: e.query,
      status: e.status, bodyBytes: e.bodyBytes, unchanged: e.response.unchanged})),
    unchangedViewReplies: idle.map(e => ({path: e.path, bodyBytes: e.bodyBytes})),
    catalogResponses: reads.filter(e => /\/(catalog|artifacts)$/.test(e.path) && e.response).map(e => ({path: e.path, query: e.query, bodyBytes: e.bodyBytes,
      items: (e.response.investigations ?? e.response.artifacts)?.length, unchanged: e.response.unchanged})),
    mutationRequests: posts.map(e => ({path: e.path, requestId: JSON.parse(e.body).requestId})),
    javascriptExceptions: exceptions, screenshots: ['desktop_lineage','desktop_comparison','mobile_picker','mobile_lineage'].map(name => `${prefix}_${name}.png`),
    limits: 'Scripted synthetic recovery; no human-speed, native execution, aggregate SQL-work, or maximum individual packet-size claim.'};
  await fs.writeFile(`${prefix}.json`, JSON.stringify(evidence, null, 2) + '\n');
  console.log(JSON.stringify({passed: true, draftId, sourceResponses: details.length, unchangedReplies: idle.length, evidence: `${prefix}.json`}));
} catch (error) {
  await screenshot('failure');
  throw error;
} finally {
  await rpc('Fetch.disable');
  socket.close();
}
