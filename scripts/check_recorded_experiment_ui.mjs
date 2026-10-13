// Real Chromium acceptance of recorded experiments over a synthetic canonical history.
// Start demo API :8765, Vite :5173, and dedicated Chromium debugging :9222.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';

const fixturePath = process.env.NEMA_RECORDED_EXPERIMENT_FIXTURE ?? 'docs/evidence/RECORDED_EXPERIMENT_SYNTHETIC_2026_10_13.json';
const prefix = process.env.NEMA_RECORDED_EXPERIMENT_UI_PREFIX ?? 'docs/evidence/recorded_experiment_ui_2026_10_13';
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
  client.name = name; client.loads = 0; client.losePost = ''; client.lost = []; client.missingOwner = ''; client.reads = []; client.phase = "initial"; client.inflight = new Set(); client.holdPath = ""; client.held = null; client.failPath = "";
  const network = new Map();
  client.event = message => {
    const value = message.params;
    if (message.method === 'Page.loadEventFired') client.loads++;
    if (message.method === 'Runtime.exceptionThrown') exceptions.push({context: name, details: value.exceptionDetails});
    if (message.method === 'Network.requestWillBeSent') {
      const url = new URL(value.request.url);
      if (url.pathname.startsWith('/api/')) {
        client.inflight.add(value.requestId);
        const entry = {context: name, phase: client.phase, path: url.pathname, query: url.search, method: value.request.method, body: value.request.postData};
        requests.push(entry); network.set(value.requestId, entry);
      }
    }
    if (['Network.loadingFinished','Network.loadingFailed'].includes(message.method)) client.inflight.delete(value.requestId);
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
      if (!value.responseStatusCode && client.failPath === path) {
        client.failPath = '';
        void client.rpc('Fetch.fulfillRequest', {requestId:value.requestId,responseCode:503,
          responseHeaders:[{name:'Content-Type',value:'application/json'}],body:Buffer.from(JSON.stringify({error:'Synthetic one-shot read failure'})).toString('base64')});
      } else if (value.responseStatusCode && client.holdPath === path) {
        client.holdPath = ''; client.held = value.requestId;
      } else if (value.responseStatusCode && value.request.method === 'POST' && path === client.losePost) {
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
  await clickText('New investigation');
  await fill('#investigation-title', `Unsaved ${name} ${label}`);
  await fill('#investigation-question', `DIRTY ${name}: do not replace this question when opening a comparison.`);
  await select('#context-artifact-picker', JSON.stringify([fixture.sourceOwner, fixture.sourceArtifact]));
  await clickText('Add selected result to context');
  await fill(`[data-selected-artifact-id="${fixture.sourceArtifact}"] input`, 'Keep this rationale and the pending save identity.');
  page.losePost = '/api/investigations';
  await clickText('Save and preview context');
  await wait("!!JSON.parse(localStorage.getItem('nema.investigation-draft.v1'))?.pendingRequest && !!document.querySelector('.work-error')");
  assert(page.lost.some(item => item.path === '/api/investigations' && item.committedStatus === 201));
  const draft = await investigationDraft(); assert(draft.pendingRequest?.id && !draft.selectedId);
  return draft;
}
async function exactFocus() {
  await wait(`!!document.querySelector('.focus-evidence[data-investigation-id="${fixture.owner}"]')`);
  const current = await comparison();
  assert.equal(current.focus.investigationId, fixture.owner);
  assert.equal(current.focus.contextId, fixture.contexts.C0);
  assert.equal(current.focus.seq, fixture.originalRecord.seq);
  await wait("!!document.querySelector('.focus-evidence .raw-evidence summary')");
  const details = '.focus-evidence .raw-evidence';
  await evaluate(`document.querySelector(${JSON.stringify(details)}).open=true`);
  assert.equal(await evaluate(`document.querySelector(${JSON.stringify(details + ' pre')}).textContent`), fixture.originalRecord.rawText);
}

const setupMutations = [];
const owner = fixture.owner;
const experimentPath = id => `/api/investigations/${owner}/experiments/${id}`;
async function fixturePost(path, body) {
  const response = await fetch(apiOrigin + path, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const value = await response.json(); assert(response.ok,JSON.stringify(value));
  setupMutations.push({path,requestId:body.requestId,status:response.status}); return value;
}
async function setupExperiment(name, context) {
  return fixturePost(`/api/investigations/${owner}/experiments`,{requestId:`browser/${label}/${name}`,
    baselineContextId:fixture.contexts.C0,baselineArtifactId:fixture.artifacts.A1,alternativeContextId:context,
    rationale:`Recorded browser ${name} ${label}: exact historical inputs; synthetic sources and no native execution.`});
}
const experiments = {E1:await setupExperiment('E1',fixture.contexts.C1),E2:await setupExperiment('E2',fixture.contexts.C2)};
const expected = experiment => ({left:{investigationId:owner,contextId:fixture.contexts.C0,artifactId:fixture.artifacts.A1},
  right:{investigationId:owner,contextId:experiment.alternative.contextId},lens:'context',layout:'beside',intent:'alternative-review',experimentId:experiment.id});
async function applied(experiment) {
  await wait(`document.querySelector('.recorded-comparison')?.dataset.experimentId === ${JSON.stringify(experiment.id)}`);
  await wait("!!document.querySelector('.recorded-comparison .experiment-evaluation-summary')");
  assert.deepEqual((await comparison()).arrangement,expected(experiment));
  const pins=await evaluate("[...document.querySelectorAll('.comparison-aperture')].map(e=>({context:e.dataset.contextId,artifact:e.dataset.artifactId}))");
  assert.deepEqual(pins,[{context:fixture.contexts.C0,artifact:fixture.artifacts.A1},{context:experiment.alternative.contextId,artifact:''}]);
}
async function preview(experiment, selectedOwner=owner) {
  await evaluate("document.querySelector('.structured-attention').open=true");
  await fill('#arrangement-request',JSON.stringify({version:1,intent:'alternative-review',investigationId:selectedOwner,experimentId:experiment.id}));
  await clickText('Preview attention request');
}
async function apply(experiment) {
  await wait("!!document.querySelector('.arrangement-review')");
  await clickText('Apply arrangement'); await applied(experiment);
}
async function settle() {
  for(let n=0;n<100;n++) {
    if(page.inflight.size===0) {
      await new Promise(resolve=>setTimeout(resolve,150));
      if(page.inflight.size===0) {await evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))');return;}
    }
    await new Promise(resolve=>setTimeout(resolve,50));
  }
  throw Error('API requests did not settle');
}
async function originalSupport() {
  await click('#inspect-experiment-baseline');
  await wait(`document.querySelector('.artifact-lineage[open] [data-lineage-artifact-id]')?.dataset.lineageArtifactId === ${JSON.stringify(fixture.artifacts.A1)}`);
  await wait(`document.querySelector('.artifact-lineage[open] [data-lineage-context-id]')?.dataset.lineageContextId === ${JSON.stringify(fixture.contexts.C0)}`);
  await wait("!!document.querySelector('.artifact-lineage[open] .lineage-record .raw-evidence')");
  await evaluate("document.querySelector('.artifact-lineage[open] .lineage-record').open=true");
  await evaluate("document.querySelector('.artifact-lineage[open] .lineage-record .raw-evidence').open=true");
  assert.equal(await evaluate("document.querySelector('.artifact-lineage[open] .lineage-record .raw-evidence pre').textContent"),fixture.originalRecord.rawText);
  await screenshot('desktop_exact_source');
  await click(`.artifact-lineage[open] .lineage-input[data-artifact-id="${fixture.sourceArtifact}"]`);
  await wait(`document.querySelector('.artifact-lineage[open] [data-lineage-artifact-id]')?.dataset.lineageArtifactId === ${JSON.stringify(fixture.sourceArtifact)}`);
  await wait("document.querySelector('.artifact-lineage[open]')?.textContent.includes('No matching adoption decision was included in this frozen input.')");
  assert.equal(await evaluate("document.querySelector('.artifact-lineage[open] .source-adoption') === null"),true);
  await clickText('Back to previous result',"document.querySelector('.artifact-lineage[open]')");
  await wait(`document.querySelector('.artifact-lineage[open] [data-lineage-artifact-id]')?.dataset.lineageArtifactId === ${JSON.stringify(fixture.artifacts.A1)}`);
  await clickText('Close result provenance',"document.querySelector('.artifact-lineage[open]')");
}
let saved, pending, freshPending, dirtyOwner, mobile, review;
try {
  await fresh('author'); page.phase='investigation';
  await select('#saved-investigation',owner);
  await wait(`!!document.querySelector('.recorded-experiment[data-experiment-id="${experiments.E1.id}"] .compare-recorded-experiment')`);
  await fill('#investigation-question','DIRTY recorded-owner question: preserve while comparing old inputs.');
  await fill(`[data-selected-artifact-id="${fixture.sourceArtifact}"] input`,'DIRTY inclusion rationale must survive comparison navigation.');
  dirtyOwner=await investigationDraft();
  const prior=await comparison(); page.phase='comparison';
  await click(`.recorded-experiment[data-experiment-id="${experiments.E1.id}"] .compare-recorded-experiment`);
  await wait("!!document.querySelector('.arrangement-review')");
  assert.deepEqual((await comparison()).arrangement,prior?.arrangement ?? null);
  assert.deepEqual(await investigationDraft(),dirtyOwner);
  await apply(experiments.E1);
  assert.deepEqual(await investigationDraft(),dirtyOwner);
  await evaluate("document.querySelector('.comparison-diff').open=true");
  const diff=await evaluate("document.querySelector('.comparison-diff .line-diff').textContent");
  assert(diff.includes('reject') && diff.includes(fixture.sourceArtifact));
  const measurements=await evaluate("document.querySelector('.recorded-comparison .experiment-evaluation-summary').textContent");
  assert(measurements.includes('Changed frozen result inputs: '+fixture.sourceArtifact));
  assert(measurements.includes('Frozen result inputs retained: no'));
  await evaluate("document.querySelector('.recorded-comparison').scrollIntoView({block:'start'})");
  await screenshot('desktop_experiment');
  await originalSupport();
  await evaluate("document.querySelector('.retained-baseline').open=true");
  await clickText('Inspect support',"document.querySelector('.retained-baseline')");
  await click(`.focus-evidence button[data-evidence-seq="${fixture.originalRecord.seq}"]`);
  await exactFocus();
  assert.equal((await comparison()).focus.artifactId,fixture.artifacts.A1);

  page.phase='pending-draft'; pending=await pendingInvestigation('recorded experiment draft');
  await clickText('Compare');page.phase='comparison';
  await applied(experiments.E1);assert.deepEqual(await investigationDraft(),pending);
  const frozenView=await comparison();
  review=await fixturePost(experimentPath(experiments.E1.id)+'/review',{requestId:`browser/${label}/review`,decision:'reject',
    rationale:'Synthetic owner review changed; original comparison targets and snapshot remain fixed.'});
  assert.equal(await evaluate("document.querySelector('.recorded-comparison .current-experiment-review').dataset.reviewStatus"),'evaluated');
  await click('#refresh-recorded-experiment');
  await wait("document.querySelector('.recorded-comparison .current-experiment-review')?.dataset.reviewStatus === 'rejected'");
  assert.deepEqual(await comparison(),frozenView);assert.deepEqual(await investigationDraft(),pending);
  await clickText('Edit arrangement');await select('#compare-lens','result');
  await clickText('Review arrangement');await clickText('Apply arrangement');
  assert.deepEqual((await comparison()).arrangement,{...expected(experiments.E1),lens:'result'});
  assert.equal(await evaluate("document.querySelector('.comparison-aperture[data-aperture=right]').dataset.artifactId"),'');
  await clickText('Edit arrangement');await select('#compare-lens','context');
  await clickText('Review arrangement');await apply(experiments.E1);
  await fill('#composition-title',`Recorded E1 recovery ${label}`);await click('#save-comparison');
  await wait("!!document.querySelector('[data-saved-composition-id]')");
  const id=await evaluate("document.querySelector('[data-saved-composition-id]').dataset.savedCompositionId");
  saved=(await get('/'+id)).composition;
  assert.deepEqual(saved.arrangement,expected(experiments.E1));
  assert.equal(saved.focus.artifactId,fixture.artifacts.A1);

  // An older free-comparison owner read must not overwrite a newer exact
  // experiment proposal when its response arrives after the proposal is ready.
  page.phase='stale-free-bind';
  await clickText('Edit arrangement');
  page.holdPath=`/api/investigations/${fixture.sourceOwner}/view`;
  await select('#compare-left',fixture.sourceOwner);
  for(let n=0;n<100 && !page.held;n++)await new Promise(resolve=>setTimeout(resolve,50));
  assert(page.held,'Free owner lookup was not held');
  await preview(experiments.E2);await wait("!!document.querySelector('.arrangement-review')");
  const oldBinding=page.held;page.held=null;await page.rpc('Fetch.continueRequest',{requestId:oldBinding});
  await settle();
  assert.equal(await evaluate("document.querySelector('#compare-left').value"),owner);
  assert.equal(await evaluate("document.querySelector('#compare-right-context').value"),fixture.contexts.C2);
  await apply(experiments.E2);
  await preview(experiments.E1);await apply(experiments.E1);
  assert.deepEqual(await investigationDraft(),pending);

  // Hold an already completed E1 HTTP response, choose/apply E2, then deliver E1.
  page.phase='stale-response';page.holdPath=experimentPath(experiments.E1.id);
  await preview(experiments.E1);
  for(let n=0;n<100 && !page.held;n++) await new Promise(resolve=>setTimeout(resolve,50));
  assert(page.held,'E1 read was not held');
  await preview(experiments.E2);await apply(experiments.E2);
  const delayed=page.held;page.held=null;await page.rpc('Fetch.continueRequest',{requestId:delayed});
  await settle();await applied(experiments.E2);assert.deepEqual(await investigationDraft(),pending);
  page.phase='failed-read';page.failPath=experimentPath(experiments.E1.id);
  await preview(experiments.E1);
  await wait("document.querySelector('.attention-intents .work-error')?.textContent.includes('Synthetic one-shot read failure')");
  await applied(experiments.E2);
  await clickText('Retry attention preview');await apply(experiments.E1);
  await preview(experiments.E1,fixture.sourceOwner);
  await wait("!!document.querySelector('.attention-intents .work-error')");
  await applied(experiments.E1);
  await preview({id:'comparison_missing'});
  await wait("!!document.querySelector('.attention-intents .work-error')");
  await applied(experiments.E1);assert.deepEqual(await investigationDraft(),pending);
  await preview(experiments.E1);await apply(experiments.E1);
  await reload();await applied(experiments.E1);
  assert.deepEqual(await investigationDraft(),pending);
  assert.deepEqual((await get('/'+saved.id)).composition,saved);

  await fresh('fresh-browser');
  assert.equal((await comparison())?.arrangement ?? null,null);
  page.phase='pending-draft';freshPending=await pendingInvestigation('fresh snapshot draft');
  await clickText('Compare');page.phase='snapshot-recovery';
  const beforePreview=await comparison();
  await evaluate("document.querySelector('#saved-comparisons-browser').open=true");
  await fill('#composition-search',saved.title);await clickText('Search',"document.querySelector('#composition-search').closest('form')");
  await browseSnapshot(saved.id);assert.deepEqual(await comparison(),beforePreview);
  await click('#open-comparison');await applied(experiments.E1);
  await wait("document.querySelector('.recorded-comparison .current-experiment-review')?.dataset.reviewStatus === 'rejected'");
  await exactFocus();assert.deepEqual(await investigationDraft(),freshPending);
  await originalSupport();assert.deepEqual(await investigationDraft(),freshPending);
  await page.rpc('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
  await evaluate("document.querySelector('.recorded-comparison').scrollIntoView({block:'start'})");
  await screenshot('mobile_review');
  await evaluate("document.querySelector('.comparison-diff').open=true;document.querySelector('.comparison-diff').scrollIntoView({block:'start'})");
  await screenshot('mobile_context_diff');
  mobile=await evaluate("({width:innerWidth,document:document.documentElement.scrollWidth-innerWidth,comparison:document.querySelector('.recorded-comparison').scrollWidth-document.querySelector('.recorded-comparison').clientWidth,diff:document.querySelector('.comparison-diff').scrollWidth-document.querySelector('.comparison-diff').clientWidth})");
  assert.equal(mobile.width,390);assert(mobile.document<=1 && mobile.comparison<=1 && mobile.diff<=1,JSON.stringify(mobile));
  await reload();await applied(experiments.E1);assert.deepEqual(await investigationDraft(),freshPending);
  assert.deepEqual((await get('/'+saved.id)).composition,saved);

  await fresh('legacy-authored-fixture');page.phase='legacy-fixture';
  await clickText('Compare');await clickText('Open synthetic inquiry & experiment');
  await click('#arrange-alternative');await wait("!!document.querySelector('.arrangement-review')");
  await clickText('Apply arrangement');await wait("!!document.querySelector('.experiment-heading[data-experiment-id]')");
  assert.equal(await evaluate("document.querySelector('.recorded-comparison') === null"),true);
  for(const client of clients) await Promise.allSettled(client.reads);
  assert.equal(exceptions.length,0,JSON.stringify(exceptions));
  const mutations=requests.filter(item=>item.method==='POST');
  assert.equal(mutations.length,3);
  assert(mutations.every(item=>['/api/investigations','/api/compositions'].includes(item.path)));
  const ownerExperimentLists=requests.filter(item=>item.method==='GET' && /\/investigations\/[^/]+\/experiments$/.test(item.path));
  assert(ownerExperimentLists.every(item=>item.context==='author' && item.phase==='investigation'));
  const report={schemaVersion:'nema-recorded-experiment-rendered/1',classification:'SYNTHETIC_HISTORY_REAL_RECORDED_EXPERIMENT_API',
    nativeOrModelCalls:0,experiments,saved,review,originalRawRecovered:true,frozenSourceReviewNotReplacedByCurrentRejection:true,sameArtifactChangedFrozenReviewVisible:true,
    laterAlternativeResultNotBound:true,laterCurrentBaselineNotBound:true,lensChangePreservedContextOnlyTarget:true,
    currentReviewSeparateFromPins:true,staleE1AfterE2Ignored:true,lateFreeOwnerBindDidNotOverwriteNewExperiment:true,failedReadRetryRetainedAppliedComparison:true,
    wrongOwnerAndMissingExperimentDidNotRebind:true,freshBrowserRecoveredExactSavedExperiment:true,legacyAuthoredFixtureWorks:true,
    draftChecks:{dirtyOwnerFieldsUnchanged:true,authorPendingRequestId:pending.pendingRequest.id,freshPendingRequestId:freshPending.pendingRequest.id},
    mobile,javascriptExceptions:exceptions,fixtureSetupMutations:setupMutations,
    browserMutationRequests:mutations.map(item=>({context:item.context,phase:item.phase,path:item.path,requestId:JSON.parse(item.body).requestId})),
    ownerExperimentLists:ownerExperimentLists.map(item=>({context:item.context,phase:item.phase,path:item.path})),
    experimentReads:requests.filter(item=>item.method==='GET' && /\/experiments\//.test(item.path)).map(({context,phase,path,status,bodyBytes})=>({context,phase,path,status,bodyBytes})),
    sourceReads:requests.filter(item=>item.method==='GET' && /\/source$/.test(item.path)).map(({context,phase,path,status,bodyBytes})=>({context,phase,path,status,bodyBytes})),
    screenshots:['desktop_experiment','desktop_exact_source','mobile_review','mobile_context_diff'].map(name=>`${prefix}_${name}.png`),
    limits:'Synthetic trusted-host history; actual experiment API and browser UI. Held-response and one-shot503 are labelled transport fixtures. No native, reasoning-quality, model-catalog or human-speed claim.'};
  await fs.writeFile(prefix+'.json',JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify({passed:true,evidence:prefix+'.json',snapshot:saved.id}));
} catch(error) {if(page)await screenshot('failure');throw error;}
finally {
  for(const client of clients) {await client.rpc('Fetch.disable').catch(()=>{});client.socket.close();}
  for(const browserContextId of contexts)await browser.rpc('Target.disposeBrowserContext',{browserContextId});
  browser.socket.close();
}
