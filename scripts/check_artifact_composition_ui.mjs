// Real rendered acceptance against an authored synthetic A→B→C database.
// Start artifact_composition_demo.py --serve, Vite :5173, and an isolated
// Chromium profile with --remote-debugging-port=9222. No dispatch/model calls.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';

const fixturePath = process.env.NEMA_ARTIFACT_FIXTURE ?? 'docs/evidence/ARTIFACT_COMPOSITION_SYNTHETIC_2026_10_13.json';
const prefix = process.env.NEMA_ARTIFACT_UI_PREFIX ?? 'docs/evidence/artifact_composition_ui_2026_10_13';
const fixture = JSON.parse(await fs.readFile(fixturePath, 'utf8'));
const origin = process.env.NEMA_UI_ORIGIN ?? 'http://127.0.0.1:5173';
const debuggerOrigin = process.env.NEMA_DEBUG_ORIGIN ?? 'http://127.0.0.1:9222';
const apiOrigin = process.env.NEMA_API_ORIGIN ?? 'http://127.0.0.1:8765';
const target = await (await fetch(`${debuggerOrigin}/json/new?about:blank`, { method: 'PUT' })).json();
const socket = new WebSocket(target.webSocketDebuggerUrl);
await new Promise(resolve => socket.addEventListener('open', resolve, { once: true }));
let sequence = 0;
let loads = 0;
const pending = new Map();
const requests = [];
const exceptions = [];
socket.addEventListener('message', event => {
  const message = JSON.parse(event.data);
  if (message.method === 'Page.loadEventFired') loads++;
  if (message.method === 'Runtime.exceptionThrown') exceptions.push(message.params.exceptionDetails);
  if (message.method === 'Network.requestWillBeSent') {
    const request = message.params.request;
    const path = new URL(request.url).pathname;
    if (path.startsWith('/api/')) requests.push({ method: request.method, path, body: request.postData });
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

try {
  await Promise.all([rpc('Page.enable'), rpc('Runtime.enable'), rpc('Network.enable')]);
  await rpc('Emulation.setDeviceMetricsOverride', { width: 1600, height: 1100, deviceScaleFactor: 1, mobile: false });
  await rpc('Storage.clearDataForOrigin', { origin, storageTypes: 'local_storage' });
  await rpc('Page.navigate', { url: origin });
  await wait("document.querySelector('#saved-investigation')?.options.length >= 4");
  await clickText('Investigation');
  await select('#saved-investigation', fixture.investigations.C);
  await wait(`!!document.querySelector('[data-result-artifact-id="${fixture.artifacts.C}"]')`);
  const beforeInspection = await draftIdentity();
  const originals = Object.fromEntries(await Promise.all(Object.entries(fixture.investigations).map(async ([key, id]) => [key, await get('/' + id)])));
  const beforePosts = requests.filter(item => item.method === 'POST').length;
  await clickText('Inspect result provenance', `document.querySelector('[data-result-artifact-id="${fixture.artifacts.C}"]')`);
  const path = [];
  for (const name of ['C', 'B', 'A']) {
    await wait(`document.querySelector('[data-lineage-artifact-id="${fixture.artifacts[name]}"]')?.dataset.lineageContextId === ${JSON.stringify(fixture.contexts[name])}`);
    path.push({ investigationId: fixture.investigations[name], artifactId: fixture.artifacts[name], contextId: fixture.contexts[name] });
    if (name === 'C') await click(`.artifact-lineage .lineage-input[data-artifact-id="${fixture.artifacts.B}"]`);
    if (name === 'B') await click(`.artifact-lineage .lineage-input[data-artifact-id="${fixture.artifacts.A}"]`);
  }
  const record = `.artifact-lineage [data-evidence-seq="${fixture.controllingSeq}"]`;
  await evaluate(`document.querySelector(${JSON.stringify(record)}).closest('details').open = true`);
  await click(`${record} .raw-evidence summary`);
  await wait(`!!document.querySelector(${JSON.stringify(record + ' .raw-evidence pre')})`);
  const recoveredRaw = await evaluate(`document.querySelector(${JSON.stringify(record + ' .raw-evidence pre')}).textContent`);
  assert.equal(recoveredRaw, fixture.controllingRawRecord.rawText);
  assert(recoveredRaw.includes('futureField'));
  await wait(`${lineageRoot}.textContent.includes('Rejected: retry automatically')`);
  await wait(`${lineageRoot}.textContent.includes('Source review when this input was saved: adopted')`);
  await evaluate(`${lineageRoot}.scrollTop = 0`);
  await screenshot('lineage');
  await clickText('Back to previous result', lineageRoot);
  await wait(`!!document.querySelector('[data-lineage-artifact-id="${fixture.artifacts.B}"]')`);
  await clickText('Close result provenance', lineageRoot);
  assert.equal(await draftIdentity(), beforeInspection);
  assert.equal(requests.filter(item => item.method === 'POST').length, beforePosts);

  await clickText('New investigation using this result', `document.querySelector('[data-result-artifact-id="${fixture.artifacts.C}"]')`);
  await wait(`!!document.querySelector('[data-selected-artifact-id="${fixture.artifacts.C}"]') && document.querySelector('#saved-investigation').value === ''`);
  await fill('#investigation-title', 'D · Browser-composed follow-up');
  await fill('#investigation-question', 'Which original decision supports C, and what remains inferred?');
  await clickText('Save and preview context');
  await wait("document.querySelector('#saved-investigation').value && document.querySelector('.context-preview')");
  const draftId = await evaluate("document.querySelector('#saved-investigation').value");
  assert(!Object.values(fixture.investigations).includes(draftId));
  const saved = await get('/' + draftId);
  assert.equal(saved.attempt, null);
  assert.deepEqual(saved.contexts[0].records, []);
  assert.equal(saved.contexts[0].artifactInputs.length, 1);
  assert.deepEqual(saved.contexts[0].artifactInputs[0].artifact, originals.C.artifact);
  assert.equal(saved.contexts[0].artifactInputs[0].sourceAttemptManifestId, originals.C.attempt.manifestId);
  assert(!saved.contexts[0].projectedPrompt.includes('OMITTED_TRANSCRIPT_CANARY'));
  await wait(`!!document.querySelector('[data-frozen-artifact-id="${fixture.artifacts.C}"]')`);
  const savedIdentity = await draftIdentity();
  const previousLoads = loads;
  await rpc('Page.reload');
  for (let attempt = 0; loads === previousLoads && attempt < 100; attempt++) {
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  assert(loads > previousLoads, 'The browser did not finish its reload');
  await wait(`document.querySelector('#saved-investigation')?.value === ${JSON.stringify(draftId)} && document.querySelector('[data-frozen-artifact-id="${fixture.artifacts.C}"]')`);
  assert.equal(await draftIdentity(), savedIdentity);
  assert.deepEqual(await get('/' + draftId), saved);

  await select('#context-artifact-picker', JSON.stringify([fixture.investigations.B, fixture.artifacts.B]));
  await clickText('Add selected result to context');
  await wait(`!!document.querySelector('[data-selected-artifact-id="${fixture.artifacts.B}"]')`);
  await fill('[aria-label="Why include result 2"]', 'Compare B directly with C while keeping their separate attribution.');
  await clickText('Save context revision');
  await wait("document.querySelector('#context-revision')?.options.length === 2");
  const revised = await get('/' + draftId);
  assert.deepEqual(revised.contexts[0], saved.contexts[0]);
  assert.equal(revised.contexts[1].artifactInputs.length, 2);
  assert.equal(revised.attempt, null);
  assert.equal(revised.status, 'draft');
  await evaluate("document.querySelector('.context-preview').scrollIntoView({block: 'start'})");
  await screenshot('preview');

  await rpc('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: true });
  await wait('innerWidth === 390');
  await fill('#investigation-question', 'Unsaved review: preserve this question while I inspect the original sources.');
  await fill('[aria-label="Why include result 1"]', 'Unsaved rationale: retain the distinction between C and its original evidence.');
  await select('#context-artifact-picker', JSON.stringify([fixture.investigations.A, fixture.artifacts.A]));
  const pickerBounds = await reachable('#context-artifact-picker');
  const addBounds = await reachable('.artifact-picker button');
  await screenshot('mobile_picker');
  await clickText('Add selected result to context');
  await wait(`!!document.querySelector('[data-selected-artifact-id="${fixture.artifacts.A}"]')`);
  const dirtyIdentity = await draftIdentity();
  await click(`[data-selected-artifact-id="${fixture.artifacts.C}"] .source-link`);
  await wait(`document.querySelector('[data-lineage-artifact-id="${fixture.artifacts.C}"]')?.dataset.lineageContextId === ${JSON.stringify(fixture.contexts.C)}`);
  await click(`.artifact-lineage[open] .lineage-input[data-artifact-id="${fixture.artifacts.B}"]`);
  await wait(`document.querySelector('[data-lineage-artifact-id="${fixture.artifacts.B}"]')?.dataset.lineageContextId === ${JSON.stringify(fixture.contexts.B)}`);
  await click(`.artifact-lineage[open] .lineage-input[data-artifact-id="${fixture.artifacts.A}"]`);
  await wait(`document.querySelector('[data-lineage-artifact-id="${fixture.artifacts.A}"]')?.dataset.lineageContextId === ${JSON.stringify(fixture.contexts.A)}`);
  await evaluate(`${lineageRoot}.scrollTop = 0`);
  const lineageBounds = await reachable('.artifact-lineage[open] .lineage-close');
  const overflow = await evaluate(`({dialog: ${lineageRoot}.scrollWidth - ${lineageRoot}.clientWidth,
    workbench: document.querySelector('.investigation-pane').scrollWidth - document.querySelector('.investigation-pane').clientWidth,
    document: document.documentElement.scrollWidth - innerWidth})`);
  assert(overflow.dialog <= 1 && overflow.workbench <= 1 && overflow.document <= 1, JSON.stringify(overflow));
  assert.equal(pickerBounds.viewportWidth, 390);
  assert.equal(addBounds.viewportWidth, 390);
  assert.equal(lineageBounds.viewportWidth, 390);
  await screenshot('mobile_lineage');
  await clickText('Back to previous result', lineageRoot);
  await wait(`!!document.querySelector('[data-lineage-artifact-id="${fixture.artifacts.B}"]')`);
  await clickText('Close result provenance', lineageRoot);
  assert.equal(await draftIdentity(), dirtyIdentity);
  const dirtyLoads = loads;
  await rpc('Page.reload');
  for (let attempt = 0; loads === dirtyLoads && attempt < 100; attempt++) await new Promise(resolve => setTimeout(resolve, 100));
  assert(loads > dirtyLoads);
  await wait(`document.querySelector('#saved-investigation')?.value === ${JSON.stringify(draftId)} && document.querySelector('[data-selected-artifact-id="${fixture.artifacts.A}"]')`);
  assert.equal(await draftIdentity(), dirtyIdentity);
  assert.deepEqual(await get('/' + draftId), revised);
  for (const [name, identifier] of Object.entries(fixture.investigations)) assert.deepEqual(await get('/' + identifier), originals[name]);
  const mutations = requests.filter(item => item.method === 'POST');
  assert.equal(mutations.length, 2);
  assert(mutations.every(item => item.path === '/api/investigations' || item.path === `/api/investigations/${draftId}/contexts`));
  assert(!requests.some(item => /\/(dispatch|follow-up|continue|messages|observe)$/.test(item.path)));
  assert.deepEqual(exceptions, []);
  const report = { schemaVersion: 'nema-artifact-composition-browser/1', classification: 'RENDERED_SYNTHETIC_AUTHORED_RESULTS',
    viewport: { width: 1600, height: 1100 }, sourceNavigation: path, controllingSeq: fixture.controllingSeq,
    rawSourceExactlyRecovered: true, unknownFieldsPreserved: true, sourceAdoptionSeparatelyDisplayed: true,
    inspectionPreservedDraft: true, draftId, firstContextId: saved.currentContextId, secondContextId: revised.currentContextId,
    artifactOnlyContextCreated: true, reloadPreservedExactPacket: true, oldContextAndSourceInvestigationsUnchanged: true,
    dirtyQuestionRationaleAndSelectionPreservedThroughLineageAndReload: true,
    mobile: { viewport: {width: 390, height: 844}, pickerBounds, addBounds, lineageBounds, overflow },
    nativeDispatchRequests: 0, nativeOrModelCalls: 0, mutations, javascriptExceptions: exceptions,
    screenshots: ['lineage', 'preview', 'mobile_picker', 'mobile_lineage'].map(name => `${prefix}_${name}.png`),
    limits: ['authored synthetic completions', 'no native transport or provider execution', 'scripted browser, not a human usability measure'] };
  await fs.writeFile(`${prefix}.json`, JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify(report, null, 2));
} finally {
  socket.close();
}
