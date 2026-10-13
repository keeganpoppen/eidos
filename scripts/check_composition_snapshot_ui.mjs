// Real Chromium acceptance over the explicitly synthetic persisted snapshot demo.
// Start demo API :8765, Vite :5173, and dedicated Chromium debugging :9222.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';

const fixturePath = process.env.NEMA_COMPOSITION_FIXTURE ?? 'docs/evidence/COMPOSITION_SNAPSHOT_SYNTHETIC_2026_10_13.json';
const prefix = process.env.NEMA_COMPOSITION_UI_PREFIX ?? 'docs/evidence/composition_snapshot_ui_2026_10_13';
const fixture = JSON.parse(await fs.readFile(fixturePath, 'utf8'));
const origin = process.env.NEMA_UI_ORIGIN ?? 'http://127.0.0.1:5173';
const apiOrigin = process.env.NEMA_API_ORIGIN ?? 'http://127.0.0.1:8765';
const debug = process.env.NEMA_DEBUG_ORIGIN ?? 'http://127.0.0.1:9222';
const label = crypto.randomUUID().slice(0, 8);
const requests = [], exceptions = [], contexts = [], clients = [];

async function connect(url) {
  const socket = new WebSocket(url);
  await new Promise(resolve => socket.addEventListener('open', resolve, {once: true}));
  let sequence = 0;
  const pending = new Map();
  const client = {socket, event: () => {}, rpc: (method, params = {}) => new Promise((resolve, reject) => {
    const id = ++sequence; pending.set(id, {resolve, reject}); socket.send(JSON.stringify({id, method, params}));
  })};
  socket.addEventListener('message', event => {
    const message = JSON.parse(event.data);
    if (!message.id) { client.event(message); return; }
    const waiting = pending.get(message.id); pending.delete(message.id);
    message.error ? waiting.reject(Error(JSON.stringify(message.error))) : waiting.resolve(message.result);
  });
  return client;
}
const browser = await connect((await (await fetch(debug + '/json/version')).json()).webSocketDebuggerUrl);
let page;
async function fresh(name) {
  const {browserContextId} = await browser.rpc('Target.createBrowserContext');
  contexts.push(browserContextId);
  const {targetId} = await browser.rpc('Target.createTarget', {url: 'about:blank', browserContextId});
  const target = (await (await fetch(debug + '/json/list')).json()).find(item => item.id === targetId);
  const client = await connect(target.webSocketDebuggerUrl);
  clients.push(client); page = client;
  client.name = name; client.loads = 0; client.losePost = ''; client.lost = []; client.missingOwner = ''; client.reads = [];
  const network = new Map();
  client.event = message => {
    const value = message.params;
    if (message.method === 'Page.loadEventFired') client.loads++;
    if (message.method === 'Runtime.exceptionThrown') exceptions.push({context: name, details: value.exceptionDetails});
    if (message.method === 'Network.requestWillBeSent') {
      const url = new URL(value.request.url);
      if (url.pathname.startsWith('/api/')) {
        const entry = {context: name, path: url.pathname, query: url.search, method: value.request.method, body: value.request.postData};
        requests.push(entry); network.set(value.requestId, entry);
      }
    }
    if (message.method === 'Network.responseReceived' && network.has(value.requestId)) network.get(value.requestId).status = value.response.status;
    if (message.method === 'Network.loadingFinished' && network.has(value.requestId)) {
      const entry = network.get(value.requestId);
      client.reads.push(client.rpc('Network.getResponseBody', {requestId: value.requestId}).then(result => {
        const body = result.base64Encoded ? Buffer.from(result.body, 'base64') : Buffer.from(result.body);
        entry.bodyBytes = body.length;
        try { entry.response = JSON.parse(body.toString()); } catch { /* Preserve response status for non-JSON failures. */ }
      }).catch(() => {}));
    }
    if (message.method === 'Fetch.requestPaused') {
      const path = new URL(value.request.url).pathname;
      if (value.responseStatusCode && value.request.method === 'POST' && path === client.losePost) {
        client.losePost = ''; client.lost.push({path, body: value.request.postData, committedStatus: value.responseStatusCode});
        void client.rpc('Fetch.failRequest', {requestId: value.requestId, errorReason: 'Failed'});
      } else if (!value.responseStatusCode && client.missingOwner && path === `/api/investigations/${client.missingOwner}/view`) {
        void client.rpc('Fetch.fulfillRequest', {requestId: value.requestId, responseCode: 404,
          responseHeaders: [{name: 'Content-Type', value: 'application/json'}],
          body: Buffer.from(JSON.stringify({error: 'Synthetic source unavailable response'})).toString('base64')});
      } else void client.rpc('Fetch.continueRequest', {requestId: value.requestId});
    }
  };
  await Promise.all([client.rpc('Page.enable'), client.rpc('Runtime.enable'), client.rpc('Network.enable')]);
  await client.rpc('Fetch.enable', {patterns: [{urlPattern: '*/api/*', requestStage: 'Request'}, {urlPattern: '*/api/*', requestStage: 'Response'}]});
  await client.rpc('Emulation.setDeviceMetricsOverride', {width: 1600, height: 1100, deviceScaleFactor: 1, mobile: false});
  await client.rpc('Page.navigate', {url: origin});
  await wait("!!document.querySelector('#saved-investigation')");
  return client;
}
async function evaluate(expression) {
  const result = await page.rpc('Runtime.evaluate', {expression, awaitPromise: true, returnByValue: true});
  if (result.exceptionDetails) throw Error(JSON.stringify(result.exceptionDetails));
  return result.result.value;
}
async function wait(expression) {
  for (let n = 0; n < 120; n++) { if (await evaluate(expression)) return; await new Promise(resolve => setTimeout(resolve, 100)); }
  throw Error(`Rendered condition did not arrive: ${expression}`);
}
const click = async selector => {
  await wait(`document.querySelector(${JSON.stringify(selector)}) && !document.querySelector(${JSON.stringify(selector)}).disabled`);
  await evaluate(`document.querySelector(${JSON.stringify(selector)}).click()`);
};
const clickText = async (text, root = 'document') => {
  const expression = `[...${root}.querySelectorAll('button')].find(e => e.textContent.trim() === ${JSON.stringify(text)} && !e.disabled)`;
  await wait(`!!(${expression})`); await evaluate(`(${expression}).click()`);
};
const fill = async (selector, value) => evaluate(`(() => {const e=document.querySelector(${JSON.stringify(selector)}); e.value=${JSON.stringify(value)}; e.dispatchEvent(new Event('input',{bubbles:true}));})()`);
const select = async (selector, value) => {
  await wait(`[...document.querySelector(${JSON.stringify(selector)})?.options ?? []].some(e => e.value === ${JSON.stringify(value)})`);
  await evaluate(`(() => {const e=document.querySelector(${JSON.stringify(selector)}); e.value=${JSON.stringify(value)}; e.dispatchEvent(new Event('change',{bubbles:true}));})()`);
};
const local = key => evaluate(`JSON.parse(localStorage.getItem(${JSON.stringify(key)}))`);
const investigationDraft = () => local('nema.investigation-draft.v1');
const comparison = () => local('nema.composition.v1');
const savedDraft = () => local('nema.saved-comparison.v1');
const get = async path => {
  const response = await fetch(apiOrigin + '/api/compositions' + path); const value = await response.json();
  assert(response.ok, JSON.stringify(value)); return value;
};
const screenshot = async suffix => {
  await evaluate('new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))');
  await fs.writeFile(`${prefix}_${suffix}.png`, Buffer.from((await page.rpc('Page.captureScreenshot', {format: 'png'})).data, 'base64'));
};
const reload = async () => {
  const before = page.loads; await page.rpc('Page.reload', {ignoreCache: true});
  for (let n=0; n<120 && page.loads===before; n++) await new Promise(resolve => setTimeout(resolve, 100));
  assert(page.loads>before); await wait("!!document.querySelector('#saved-investigation')");
};
async function browseSnapshot(id) {
  await evaluate("document.querySelector('#saved-comparisons-browser').open = true");
  await select('#saved-composition', id); await click('#preview-comparison');
  await wait(`document.querySelector('.snapshot-preview')?.dataset.compositionId === ${JSON.stringify(id)}`);
}
async function pendingInvestigation(name) {
  await clickText('Investigation');
  await fill('#investigation-title', `Unsaved ${name} ${label}`);
  await fill('#investigation-question', `DIRTY ${name}: do not replace this question when opening a comparison.`);
  await select('#context-artifact-picker', JSON.stringify([fixture.investigations.A, fixture.artifacts.A]));
  await clickText('Add selected result to context');
  await fill(`[data-selected-artifact-id="${fixture.artifacts.A}"] input`, 'Keep this rationale and the pending save identity.');
  page.losePost = '/api/investigations';
  await clickText('Save and preview context');
  await wait("!!JSON.parse(localStorage.getItem('nema.investigation-draft.v1'))?.pendingRequest && !!document.querySelector('.work-error')");
  assert(page.lost.some(item => item.path === '/api/investigations' && item.committedStatus === 201));
  const draft = await investigationDraft(); assert(draft.pendingRequest?.id && !draft.selectedId);
  return draft;
}
async function exactFocus() {
  await wait(`!!document.querySelector('.focus-evidence[data-investigation-id="${fixture.investigations.A}"]')`);
  const current = await comparison();
  assert.equal(current.focus.investigationId, fixture.investigations.A);
  assert.equal(current.focus.contextId, fixture.contexts.A);
  assert.equal(current.focus.seq, fixture.controllingSeq);
  await wait("!!document.querySelector('.focus-evidence .raw-evidence summary')");
  const details = '.focus-evidence .raw-evidence';
  await evaluate(`document.querySelector(${JSON.stringify(details)}).open=true`);
  assert.equal(await evaluate(`document.querySelector(${JSON.stringify(details + ' pre')}).textContent`), fixture.controllingRawRecord.rawText);
}

let original, copied, firstPending, freshPending, retryRequest, freshIsolation;
try {
  const author = await fresh('author');
  firstPending = await pendingInvestigation('author draft');
  await clickText('Compare');
  await wait("!!document.querySelector('#composition-title')");
  // Start from the exact persisted A/C comparison, then focus its actual passage.
  await browseSnapshot(fixture.snapshots.baseline.id);
  await click('#open-comparison');
  await clickText('Inspect support', `document.querySelector('.comparison-aperture[data-aperture="left"]')`);
  await wait("!!document.querySelector('.focus-evidence button[data-evidence-seq]')");
  await click(`.focus-evidence button[data-evidence-seq="${fixture.controllingSeq}"]`);
  await exactFocus();
  assert.deepEqual(await investigationDraft(), firstPending);
  const captured = await comparison();
  await fill('#composition-title', `Recovery snapshot ${label}`);
  page.losePost = '/api/compositions';
  await click('#save-comparison');
  await wait("!!document.querySelector('#retry-comparison-save') && !!document.querySelector('.saved-comparisons .work-error')");
  retryRequest = (await savedDraft()).pending;
  assert(retryRequest.requestId && author.lost.some(item => item.path === '/api/compositions' && item.committedStatus === 201));
  await reload();
  await wait("!!document.querySelector('#retry-comparison-save')");
  assert.deepEqual((await savedDraft()).pending, retryRequest);
  assert.deepEqual(await investigationDraft(), firstPending);
  await click('#retry-comparison-save');
  await wait("!!document.querySelector('[data-saved-composition-id]') && !document.querySelector('#retry-comparison-save')");
  const id = await evaluate("document.querySelector('[data-saved-composition-id]').dataset.savedCompositionId");
  original = (await get('/' + id)).composition;
  assert.deepEqual(original.arrangement, captured.arrangement);
  assert.deepEqual(original.focus, captured.focus);
  assert.equal(original.copiedFrom, fixture.snapshots.baseline.id);
  assert.equal((await get('?q=' + encodeURIComponent(original.title))).compositions.length, 1);
  await exactFocus();
  await evaluate("document.querySelector('.focus-evidence').scrollIntoView({block:'start'})");
  await screenshot('desktop_source');

  await fresh('fresh-browser');
  freshIsolation = await evaluate("localStorage.getItem('nema.composition.v1') === null || JSON.parse(localStorage.getItem('nema.composition.v1')).arrangement === null");
  assert(freshIsolation);
  freshPending = await pendingInvestigation('fresh browser draft');
  await clickText('Compare');
  await wait("!!document.querySelector('#saved-composition')");
  const beforePreview = await comparison();
  await evaluate("document.querySelector('#saved-comparisons-browser').open = true");
  await fill('#composition-search', original.title);
  await clickText('Search', "document.querySelector('#composition-search').closest('form')");
  await select('#saved-composition', original.id);
  assert.deepEqual(await comparison(), beforePreview);
  await click('#preview-comparison');
  await wait(`document.querySelector('.snapshot-preview')?.dataset.compositionId === ${JSON.stringify(original.id)}`);
  assert.deepEqual(await comparison(), beforePreview);
  assert.deepEqual(await investigationDraft(), freshPending);
  await evaluate("document.querySelector('.snapshot-preview').scrollIntoView({block:'start'})");
  await screenshot('desktop_preview');
  await click('#open-comparison');
  assert.deepEqual((await comparison()).arrangement, original.arrangement);
  assert.deepEqual((await comparison()).focus, original.focus);
  assert.deepEqual(await investigationDraft(), freshPending);
  await exactFocus();
  await clickText('Edit arrangement');
  await select('#compare-layout', 'stacked');
  await clickText('Review arrangement'); await clickText('Apply arrangement');
  await fill('#composition-title', `Copy${label}${"W".repeat(148)}`);
  await click('#save-comparison');
  await wait("!!document.querySelector('[data-saved-composition-id]')");
  copied = (await get('/' + await evaluate("document.querySelector('[data-saved-composition-id]').dataset.savedCompositionId"))).composition;
  assert.equal(copied.copiedFrom, original.id); assert.equal(copied.arrangement.layout, 'stacked');
  assert.deepEqual(copied.focus, original.focus);
  assert.deepEqual((await get('/' + original.id)).composition, original);
  assert.deepEqual(await investigationDraft(), freshPending);

  // Opening a saved pending inquiry must not compile its newer terminal receipt.
  await fill('#composition-search', '');
  await clickText('Search', "document.querySelector('#composition-search').closest('form')");
  // A changed applied focus invalidates the old preview until explicitly reviewed
  // again. Selecting another named snapshot discards the preceding preview.
  await browseSnapshot(fixture.snapshots.baseline.id);
  await clickText('Release focus');
  await wait("document.querySelector('#open-comparison')?.disabled === true");
  const afterFocusChange = await comparison();
  await evaluate("document.querySelector('#open-comparison').click()");
  assert.deepEqual(await comparison(), afterFocusChange);
  await click('#preview-comparison');
  await wait("document.querySelector('#open-comparison')?.disabled === false");
  await select('#saved-composition', fixture.snapshots.pending.id);
  assert.equal(await evaluate("document.querySelector('.snapshot-preview') === null"), true);
  assert.deepEqual(await investigationDraft(), freshPending);
  await browseSnapshot(fixture.snapshots.pending.id); await click('#open-comparison');
  await wait("!!document.querySelector('.inquiry-chain')");
  assert.deepEqual((await comparison()).arrangement, fixture.snapshots.pending.arrangement);
  assert.equal(await evaluate("document.querySelector('[data-inquiry-role=requested]').dataset.responseId"), '');
  await wait("document.querySelector('.inquiry-chain').textContent.includes('This arrangement retains its original result binding')");
  assert.deepEqual(await investigationDraft(), freshPending);

  // An unknown renderer preserves names but cannot reuse its block offset as a
  // highlighted passage under the currently installed Markdown parser.
  await page.rpc('Emulation.setDeviceMetricsOverride', {width:390,height:844,deviceScaleFactor:1,mobile:true});
  await browseSnapshot(copied.id);
  await evaluate("document.querySelector('.snapshot-preview').scrollIntoView({block:'start'})");
  const longTitle = await evaluate("({document:document.documentElement.scrollWidth-innerWidth,preview:document.querySelector('.snapshot-preview').scrollWidth-document.querySelector('.snapshot-preview').clientWidth})");
  await screenshot('mobile_long_title');
  assert(longTitle.document<=1 && longTitle.preview<=1,JSON.stringify(longTitle));
  await browseSnapshot(fixture.snapshots.artifactFocus.id);
  await click('#open-comparison');
  await wait("document.querySelector('.focus-evidence')?.textContent.includes('Saved record cited by this result')");
  await exactFocus();
  assert.deepEqual((await comparison()).focus,fixture.snapshots.artifactFocus.focus);
  assert.equal(await evaluate("document.querySelectorAll('.work-block.focused').length"),0);
  assert.deepEqual(await investigationDraft(),freshPending);
  await evaluate("document.querySelector('.focus-evidence').scrollIntoView({block:'start'})");
  await screenshot('mobile_artifact_record');
  await browseSnapshot(fixture.snapshots.unknownRenderer.id);
  await wait("!!document.querySelector('.snapshot-preview [data-unresolved-selector]')");
  await page.rpc('Emulation.setDeviceMetricsOverride', {width:390,height:844,deviceScaleFactor:1,mobile:true});
  await evaluate("document.querySelector('.snapshot-preview').scrollIntoView({block:'start'})");
  await screenshot('mobile_preview');
  await click('#open-comparison');
  await wait("!!document.querySelector('.focus-evidence [data-unresolved-selector]')");
  assert.deepEqual((await comparison()).focus, fixture.snapshots.unknownRenderer.focus);
  assert.equal(await evaluate("document.querySelectorAll('.work-block.focused').length"), 0);
  assert.deepEqual(await investigationDraft(), freshPending);
  await evaluate("document.querySelector('.focus-evidence').scrollIntoView({block:'start'})");
  const mobile = await evaluate(`({width:innerWidth,document:document.documentElement.scrollWidth-innerWidth,
    saved:document.querySelector('.saved-comparisons').scrollWidth-document.querySelector('.saved-comparisons').clientWidth,
    focus:document.querySelector('.focus-evidence').scrollWidth-document.querySelector('.focus-evidence').clientWidth})`);
  assert.equal(mobile.width,390); assert(mobile.document<=1 && mobile.saved<=1 && mobile.focus<=1,JSON.stringify(mobile));
  await screenshot('mobile_unknown_renderer');
  await reload();
  await wait("!!document.querySelector('.focus-evidence [data-unresolved-selector]')");
  assert.deepEqual((await comparison()).focus, fixture.snapshots.unknownRenderer.focus);
  assert.deepEqual(await investigationDraft(), freshPending);

  // Transport-unavailable source is a labelled browser failure fixture. Separate
  // Python tests remove an actual canonical row and verify immutable read/replay.
  const missing = await fresh('missing-source');
  missing.missingOwner = fixture.investigations.A;
  await clickText('Compare'); await wait("!!document.querySelector('#saved-composition')");
  await browseSnapshot(original.id);
  await wait("document.querySelector('.snapshot-preview').textContent.includes('This exact source is unavailable')");
  await click('#open-comparison');
  assert.deepEqual((await comparison()).arrangement, original.arrangement);
  assert.deepEqual((await comparison()).focus, original.focus);
  await clickText('Edit arrangement');
  await select('#compare-left', fixture.investigations.C);
  await wait(`document.querySelector('#compare-left-context').value === ${JSON.stringify(fixture.contexts.C)}`);
  await clickText('Review arrangement'); await clickText('Apply arrangement');
  await clickText('Release focus');
  await fill('#composition-title', `Explicit missing-source repair ${label}`);
  await click('#save-comparison');
  await wait("!!document.querySelector('[data-saved-composition-id]')");
  const repaired = (await get('/' + await evaluate("document.querySelector('[data-saved-composition-id]').dataset.savedCompositionId"))).composition;
  assert.equal(repaired.copiedFrom, original.id); assert.equal(repaired.arrangement.left.investigationId, fixture.investigations.C);
  assert.equal(repaired.focus,null); assert.deepEqual((await get('/' + original.id)).composition, original);
  for(const client of clients) await Promise.allSettled(client.reads);
  assert.equal(exceptions.length,0,JSON.stringify(exceptions));
  const posts=requests.filter(item=>item.method==='POST');
  assert.equal(posts.length,6);
  assert(posts.every(item=>['/api/compositions','/api/investigations'].includes(item.path)));
  const snapshotPosts=posts.filter(item=>item.path==='/api/compositions');
  const retried=snapshotPosts.filter(item=>JSON.parse(item.body).requestId===retryRequest.requestId);
  assert.equal(retried.length,2); assert.deepEqual(JSON.parse(retried[0].body),JSON.parse(retried[1].body));
  const catalogReads=requests.filter(item=>item.path==='/api/compositions' && item.method==='GET' && item.response);
  assert(catalogReads.every(item=>!JSON.stringify(item.response).includes('arrangement')));
  await fs.writeFile(`${prefix}.json`,JSON.stringify({schemaVersion:'nema-composition-rendered/1',classification:'SYNTHETIC_REAL_BROWSER',
    nativeOrModelCalls:0,freshIsolatedBrowserContext:true,original,copied,repaired,
    committedLostReplyRetriedSameRequestId:retryRequest.requestId,duplicateSnapshotCount:0,
    dirtyDraftAndPendingRequestRetained:{author:firstPending.pendingRequest.id,freshBrowser:freshPending.pendingRequest.id},
    exactOriginalRawRecordRecovered:true,pendingInquiryNotRecompiled:true,artifactRecordWithoutBlockPreserved:true,unknownRendererDidNotHighlightOrRebind:true,
    missingSourceFixture:'HTTP404 injected for exact source owner; backend actual-row deletion covered separately',
    stalePreviewBlockedAfterFocusChange:true,selectingAnotherSnapshotClearedPreview:true,longTitle,
    mobile,compositionReads:requests.filter(item=>item.method==='GET' && item.path.startsWith('/api/compositions') && item.response)
      .map(item=>({context:item.context,path:item.path,bodyBytes:item.bodyBytes,status:item.status})),
    mutationRequests:posts.map(item=>({context:item.context,path:item.path,requestId:JSON.parse(item.body).requestId})),
    javascriptExceptions:exceptions,screenshots:['desktop_source','desktop_preview','mobile_long_title','mobile_artifact_record','mobile_preview','mobile_unknown_renderer'].map(name=>`${prefix}_${name}.png`),
    limits:'Same-database scripted synthetic recovery; no authentication, synchronization, native-model, or human-speed claim.'},null,2)+'\n');
  console.log(JSON.stringify({passed:true,original:original.id,copied:copied.id,repaired:repaired.id,evidence:`${prefix}.json`}));
} catch(error) {
  if(page) await screenshot('failure');
  throw error;
} finally {
  for(const client of clients) {await client.rpc('Fetch.disable').catch(()=>{});client.socket.close();}
  for(const browserContextId of contexts) await browser.rpc('Target.disposeBrowserContext',{browserContextId});
  browser.socket.close();
}
