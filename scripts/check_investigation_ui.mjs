// Rendered acceptance against the synthetic demo API, never a native account.
// Requires scripts/investigation_demo.py --serve on :8765, Vite :5173, and
// isolated Chromium --remote-debugging-port=9222. No npm dependencies/model calls.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import { extendSyntheticHistory } from './fixtures/reflective_history.mjs';
import { competingInterpretation } from './fixtures/reflective_interpretation.mjs';

const evidencePrefix = process.env.NEMA_UI_EVIDENCE_PREFIX ?? 'docs/evidence/reflective';

const target = await (await fetch('http://127.0.0.1:9222/json/new?http://127.0.0.1:5173', { method: 'PUT' })).json();
const socket = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve) => socket.addEventListener('open', resolve, { once: true }));
let sequence = 0;
let documentLoads = 0;
const pending = new Map();
const apiRequests = [];
const fixtureTransfers = [];
let requestFixture = null;
socket.addEventListener('message', (event) => {
  const message = JSON.parse(event.data);
  if (message.method === 'Page.loadEventFired') documentLoads++;
  if (message.method === 'Network.requestWillBeSent') {
    const request = message.params.request;
    const path = new URL(request.url).pathname;
    if (path.startsWith('/api/')) apiRequests.push({ path, method: request.method });
  }
  if (message.method === 'Fetch.requestPaused') {
    void (async () => {
      const body = requestFixture?.(message.params.request.url);
      if (body) {
        const json = JSON.stringify(body);
        fixtureTransfers.push({ path: new URL(message.params.request.url).pathname, decodedJSONBytes: Buffer.byteLength(json) });
        await rpc('Fetch.fulfillRequest', {
          requestId: message.params.requestId, responseCode: 200,
          responseHeaders: [{ name: 'Content-Type', value: 'application/json' }],
          body: Buffer.from(json).toString('base64')
        });
      } else await rpc('Fetch.continueRequest', { requestId: message.params.requestId });
    })().catch((error) => console.error('Fixture interception failed:', error));
    return;
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
const evaluate = async (expression) => {
  const result = await rpc('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true });
  if (result.exceptionDetails) throw Error(JSON.stringify(result.exceptionDetails));
  return result.result.value;
};
const wait = async (expression) => {
  for (let i = 0; i < 100; i++) {
    if (await evaluate(expression)) return;
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw Error(`UI condition did not arrive: ${expression}`);
};
const clickText = async (text, selector = 'button') => {
  await wait(`[...document.querySelectorAll(${JSON.stringify(selector)})].some(e => e.textContent.trim() === ${JSON.stringify(text)} && !e.disabled)`);
  return evaluate(`(() => {
    const element = [...document.querySelectorAll(${JSON.stringify(selector)})].find(e => e.textContent.trim() === ${JSON.stringify(text)} && !e.disabled);
    element.click();
  })()`);
};
const fill = async (selector, value) => evaluate(`(() => {
  const e = document.querySelector(${JSON.stringify(selector)});
  if (!e) throw Error('Missing input: ' + ${JSON.stringify(selector)});
  e.value = ${JSON.stringify(value)}; e.dispatchEvent(new Event('input', {bubbles:true}));
})()`);
const select = async (selector, value) => {
  await wait(`[...document.querySelector(${JSON.stringify(selector)})?.options ?? []].some(o => o.value === ${JSON.stringify(value)})`);
  return evaluate(`(() => {
    const e = document.querySelector(${JSON.stringify(selector)});
    e.value = ${JSON.stringify(value)}; e.dispatchEvent(new Event('change', {bubbles:true}));
  })()`);
};
const getWork = async (id) => (await fetch(`http://127.0.0.1:8765/api/investigations/${id}`)).json();
const post = async (path, body) => {
  const response = await fetch(`http://127.0.0.1:8765/api/investigations${path}`, {
    method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body)
  });
  const value = await response.json();
  assert(response.ok, JSON.stringify(value));
  return value;
};
const keypress = async (key, code = key, virtualKey = 0) => {
  await rpc('Input.dispatchKeyEvent', { type: 'keyDown', key, code, windowsVirtualKeyCode: virtualKey, ...(key === 'Enter' ? { text: '\r', unmodifiedText: '\r' } : {}) });
  await rpc('Input.dispatchKeyEvent', { type: 'keyUp', key, code, windowsVirtualKeyCode: virtualKey });
};
const screenshot = async (path) => {
  await evaluate(`new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))`);
  await fs.writeFile(path, Buffer.from((await rpc('Page.captureScreenshot', { format: 'png' })).data, 'base64'));
};
const compositionIdentity = () => evaluate(`JSON.stringify([...document.querySelectorAll('[data-aperture]')].map(e => ({ aperture: e.dataset.aperture, investigation: e.dataset.investigationId, context: e.dataset.contextId, artifact: e.dataset.artifactId })))`);
const inquiryIdentity = () => evaluate(`JSON.stringify([...document.querySelectorAll('[data-inquiry-role]')].map(e => ({ role: e.dataset.inquiryRole, context: e.dataset.contextId, artifact: e.dataset.artifactId, inquiry: e.dataset.inquiryId, response: e.dataset.responseId })))`);
const reload = async () => {
  const previous = documentLoads;
  await rpc('Page.reload');
  for (let attempt = 0; attempt < 100; attempt++) {
    if (documentLoads > previous) return;
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw Error('Browser reload did not finish');
};

try {
  await rpc('Page.bringToFront');
  await rpc('Page.enable');
  await rpc('Network.enable');
  await rpc('Emulation.setDeviceMetricsOverride', { width: 1600, height: 1000, deviceScaleFactor: 1, mobile: false });
  await wait(`document.querySelector('#investigation-title') !== null`);
  await evaluate(`localStorage.clear()`);
  await reload();
  await new Promise((resolve) => setTimeout(resolve, 1000));
  await wait(`document.querySelector('.thread-button') !== null && document.querySelector('#investigation-title') !== null`);
  await clickText('Investigation', '.aperture-switch button');
  await clickText('New investigation', '.work-picker button');
  await evaluate(`[...document.querySelectorAll('.thread-button')].find(e => e.textContent.includes('Synthetic design:')).click()`);
  await wait(`document.querySelector('.thread-header')?.textContent.includes('fixture-design')`);
  // A semantic selection retains its two disjoint source ranges.
  await clickText('Evidence map', '.aperture-switch button');
  await wait(`document.querySelector('.semantic-node') !== null`);
  await evaluate(`document.querySelector('.semantic-node').click()`);
  await wait(`document.querySelector('.source-focus-notice')?.textContent.includes('12–12, 38–38')`);
  await clickText('Add selected evidence to context');
  await wait(`document.querySelector('.context-count')?.textContent.includes('2 ranges from 1 thread')`);
  // An exact native item in the second thread joins the same packet.
  await evaluate(`[...document.querySelectorAll('.thread-button')].find(e => e.textContent.includes('Synthetic experiment:')).click()`);
  await wait(`document.querySelector('.thread-header')?.textContent.includes('fixture-experiment')`);
  await evaluate(`document.querySelector('[data-item-id="fixture-experiment-turn-11-answer"] .source-select').click()`);
  await wait(`document.querySelector('.context-count')?.textContent.includes('3 ranges from 2 threads')`);
  await fill('#investigation-title', 'Two-thread recovery acceptance');
  await fill('#investigation-question', 'Compare recovery approaches and identify the unprotected crash window.');
  await clickText('Save and preview context');
  await wait(`document.querySelector('.exact-input') !== null`);
  const identifier = await evaluate(`document.querySelector('#saved-investigation').value`);
  const initial = await (await fetch(`http://127.0.0.1:8765/api/investigations/${identifier}`)).json();
  assert.equal(initial.contexts[0].records.length, 3);
  assert(!initial.contexts[0].projectedPrompt.includes('Routine build note'));
  await clickText(`Exact specialist input · ${initial.contexts[0].projectedPrompt.length.toLocaleString()} characters`, '.exact-input summary');
  assert.equal(await evaluate(`document.querySelector('.exact-input pre').textContent`), initial.contexts[0].projectedPrompt);
  await fill('#investigation-question', 'Compare recovery approaches. Explain why a lost reply cannot justify an automatic retry.');
  await clickText('Save context revision');
  await wait(`document.querySelectorAll('#context-revision option').length === 2`);
  await wait(`document.querySelector('.context-diff')?.textContent.includes('Previous question:')`);
  // Let a server refresh deserialize the saved selections. Object key order
  // changes across POST/GET must not invent an unsaved context revision.
  await new Promise((resolve) => setTimeout(resolve, 1700));
  assert(!await evaluate(`[...document.querySelectorAll('.work-notice')].some(e => e.textContent.includes('Selection or question changed'))`), 'polling must not mark an unchanged saved packet dirty');
  await clickText('Start specialist with this context');
  await wait(`document.querySelector('.work-status')?.textContent.includes('completed')`);
  await wait(`document.querySelector('.investigation-result')?.textContent.includes('Synthetic specialist result')`);
  await reload();
  await new Promise((resolve) => setTimeout(resolve, 1000));
  await wait(`document.querySelector('.investigation-result') !== null`);
  assert.equal(await evaluate(`document.querySelector('#saved-investigation').value`), identifier);
  assert.equal(await evaluate(`document.querySelectorAll('.citation-links button').length`), 3);
  await clickText('Inspect recorded native output');
  await wait(`document.querySelector('.thread-header')?.textContent.includes('fixture-worker-')`);
  await wait(`document.querySelector('[data-item-id="fixture-answer"]')?.classList.contains('highlighted')`);
  await evaluate(`document.querySelector('.citation-links button').click()`);
  await wait(`document.querySelector('.thread-header')?.textContent.includes('fixture-design')`);
  await wait(`document.querySelector('[data-item-id="fixture-design-turn-5-answer"]')?.classList.contains('highlighted')`);
  await fill('#adoption-note', 'Keep a stable attempt and preserve uncertain delivery.');
  await clickText('Adopt conclusion');
  await wait(`document.querySelector('.adoption-receipt')?.textContent.includes('Conclusion adopted')`);
  await reload();
  await new Promise((resolve) => setTimeout(resolve, 1000));
  await wait(`document.querySelector('.adoption-receipt') !== null`);
  await evaluate(`document.querySelector('.investigation-result').scrollIntoView({block:'start'}); document.querySelector('[data-item-id="fixture-design-turn-5-answer"]').scrollIntoView({block:'center'});`);
  await new Promise((resolve) => setTimeout(resolve, 300));
  const final = await (await fetch(`http://127.0.0.1:8765/api/investigations/${identifier}`)).json();
  assert.equal(final.adoption.decision, 'adopt');
  assert.equal(final.contexts.length, 2);
  assert.equal(final.attempt.contextId, final.contexts[1].id);
  assert.equal(final.artifact.contextId, final.contexts[1].id);
  assert.equal(final.artifact.citations.length, 3);
  assert.equal(final.artifact.unsupportedCitations.length, 0);
  assert(await evaluate(`document.querySelector('.investigation-pane').scrollWidth <= document.querySelector('.investigation-pane').clientWidth + 1`), 'work pane must not overflow horizontally');
  // A second server-derived saved work supplies a competing question and packet.
  // The fixture worker returns identical prose for every task; the UI must not
  // manufacture a disagreement between those returned artifacts.
  const alternative = await post('', {
    requestId: crypto.randomUUID(), title: 'Competing interpretation · inner checkpoint sufficiency',
    question: 'Could the inner prepared checkpoint alone be sufficient? Test this interpretation against the crash experiment and state what remains unknown.',
    selections: final.contexts[1].selections.filter((selection) => selection.startSeq !== 38)
  });
  await post(`/${alternative.id}/dispatch`, { contextId: alternative.currentContextId });
  let completedAlternative;
  for (let attempt = 0; attempt < 100; attempt++) {
    completedAlternative = await getWork(alternative.id);
    if (completedAlternative.status === 'completed') break;
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  assert.equal(completedAlternative.status, 'completed');
  const unchangedWorks = JSON.stringify([final, completedAlternative]);
  await reload();
  await wait(`document.querySelector('#saved-investigation')?.value === ${JSON.stringify(identifier)}`);
  await clickText('Compare', '.aperture-switch button');
  await wait(`document.querySelector('.arrangement-editor') !== null`);
  await select('#compare-left', identifier);
  await select('#compare-right', alternative.id);
  await select('#compare-left-context', final.currentContextId);
  await select('#compare-right-context', alternative.currentContextId);
  await select('#compare-lens', 'context');
  await select('#compare-layout', 'beside');
  await clickText('Review arrangement');
  await wait(`document.querySelector('.arrangement-review') !== null`);
  assert.equal(await evaluate(`document.querySelector('.comparison-surface').dataset.layout`), 'beside');
  await clickText('Apply arrangement');
  await wait(`document.querySelector('[data-aperture="right"]')?.dataset.investigationId === ${JSON.stringify(alternative.id)}`);
  await wait(`document.querySelector('.comparison-diff')?.textContent.includes('38')`);
  await evaluate(`document.querySelector('.comparison-diff').open = true; document.querySelector('.comparison-diff').scrollIntoView({block:'center'})`);
  assert(await evaluate(`[...document.querySelectorAll('.comparison-diff .diff-row.removed')].some(e => e.textContent.includes('38'))`));
  assert(await evaluate(`[...document.querySelectorAll('.comparison-diff .diff-row.added')].some(e => e.textContent.includes('Could the inner prepared checkpoint'))`));
  const contextArrangement = await compositionIdentity();
  await fs.mkdir('docs/evidence', { recursive: true });
  await screenshot(`${evidencePrefix}-context-diff.png`);

  // Proposed changes remain reviewable and cancel without altering the surface.
  await clickText('Edit arrangement');
  await select('#compare-layout', 'stacked');
  await clickText('Review arrangement');
  assert.equal(await evaluate(`document.querySelector('.comparison-surface').dataset.layout`), 'beside', 'review must not apply the draft placement');
  assert.equal(await compositionIdentity(), contextArrangement, 'review must not retarget either aperture');
  assert.equal(await evaluate(`JSON.parse(localStorage.getItem('nema.composition.v1')).arrangement.layout`), 'beside', 'draft placement must not be persisted as applied');
  await clickText('Cancel changes');
  assert.equal(await evaluate(`document.querySelector('.comparison-surface').dataset.layout`), 'beside');
  assert.equal(await compositionIdentity(), contextArrangement);
  await clickText('Edit arrangement');
  await select('#compare-layout', 'stacked');
  await clickText('Review arrangement');
  await clickText('Apply arrangement');
  await wait(`document.querySelector('.comparison-surface').dataset.layout === 'stacked'`);
  await clickText('Undo arrangement');
  await wait(`document.querySelector('.comparison-surface').dataset.layout === 'beside'`);
  assert.equal(await compositionIdentity(), contextArrangement);

  // Compare two immutable revisions of the same investigation, not just IDs.
  await clickText('Edit arrangement');
  await select('#compare-right', identifier);
  await select('#compare-left-context', final.contexts[0].id);
  await select('#compare-right-context', final.contexts[1].id);
  await clickText('Review arrangement');
  await clickText('Apply arrangement');
  await wait(`document.querySelector('[data-aperture="left"]')?.dataset.contextId === ${JSON.stringify(final.contexts[0].id)}`);
  assert.equal(await evaluate(`document.querySelector('[data-aperture="right"]').dataset.contextId`), final.contexts[1].id);
  assert(await evaluate(`document.querySelector('.comparison-diff').textContent.includes('lost reply')`));
  await clickText('Undo arrangement');
  await wait(`document.querySelector('[data-aperture="right"]')?.dataset.investigationId === ${JSON.stringify(alternative.id)}`);

  // Show both actual model artifacts and open their support with keyboard input.
  await clickText('Edit arrangement');
  await select('#compare-lens', 'result');
  await clickText('Review arrangement');
  await clickText('Apply arrangement');
  await wait(`[...document.querySelectorAll('[data-aperture="left"] button')].some(e => e.textContent.trim() === 'Inspect support')`);
  await evaluate(`[...document.querySelectorAll('[data-aperture="right"] button')].filter(e => e.textContent.trim() === 'Inspect support').at(-1).click()`);
  await wait(`document.querySelector('.focus-evidence')?.dataset.investigationId === ${JSON.stringify(alternative.id)}`);
  assert.equal(await evaluate(`document.querySelector('.focus-evidence').dataset.contextId`), completedAlternative.artifact.contextId);
  assert.equal(await evaluate(`document.querySelector('.focus-evidence button[data-evidence-seq="38"]')`), null, 'the competing artifact must use its own citations');
  assert(await evaluate(`!!document.querySelector('.focus-evidence button[data-evidence-seq="72"]')`));
  await evaluate(`[...document.querySelectorAll('[data-aperture="left"] button')].filter(e => e.textContent.trim() === 'Inspect support').at(-1).focus()`);
  assert.equal(await evaluate(`document.activeElement.textContent.trim()`), 'Inspect support');
  await keypress('Enter', 'Enter', 13);
  await wait(`document.querySelector('.focus-evidence')?.dataset.investigationId === ${JSON.stringify(identifier)}`);
  await wait(`document.querySelector('.focus-evidence button[data-evidence-seq="12"]') !== null`);
  const resultArrangement = await compositionIdentity();
  await evaluate(`document.querySelector('.focus-evidence button[data-evidence-seq="72"]').click()`);
  await wait(`document.querySelector('.focus-evidence .frozen-record')?.dataset.evidenceSeq === '72'`);
  await evaluate(`document.querySelector('.focus-evidence button[data-evidence-seq="12"]').focus()`);
  await keypress('Enter', 'Enter', 13);
  await wait(`document.querySelector('.focus-evidence .frozen-record')?.dataset.evidenceSeq === '12'`);
  assert(await evaluate(`document.querySelector('.focus-evidence .frozen-record').textContent.includes('Decision: persist a dispatch attempt')`));
  assert.equal(await compositionIdentity(), resultArrangement, 'following evidence must preserve the comparison');
  assert.equal(await evaluate(`document.querySelector('.focus-evidence').dataset.contextId`), final.artifact.contextId);
  await reload();
  await wait(`document.querySelector('.focus-evidence .frozen-record')?.dataset.evidenceSeq === '12'`);
  assert.equal(await compositionIdentity(), resultArrangement, 'reload must restore both immutable references');
  assert.equal(await evaluate(`document.querySelector('.comparison-surface').dataset.layout`), 'beside');
  assert.equal(await evaluate(`document.querySelector('.focus-evidence').dataset.investigationId`), identifier);
  const remembered = await evaluate(`localStorage.getItem('nema.composition.v1')`);
  assert(remembered, 'the browser must retain its presentation references');
  const rememberedObject = JSON.parse(remembered);
  const rememberedStrings = [];
  const inspectStored = (value) => {
    if (typeof value === 'string') rememberedStrings.push(value);
    else if (value && typeof value === 'object') {
      for (const [key, child] of Object.entries(value)) {
        assert(!['rawText', 'text', 'projectedPrompt', 'records', 'contexts', 'artifact'].includes(key), `authoritative field leaked into composition: ${key}`);
        inspectStored(child);
      }
    }
  };
  inspectStored(rememberedObject);
  assert(!rememberedStrings.includes(final.artifact.text), 'composition storage must not cache authoritative artifact prose');
  assert(!rememberedStrings.includes(final.contexts[1].projectedPrompt), 'composition storage must not cache authoritative context');
  assert(await evaluate(`document.querySelector('.comparison-surface').scrollWidth <= document.querySelector('.comparison-surface').clientWidth + 1`), 'comparison must not overflow horizontally');
  await screenshot(`${evidencePrefix}-server-comparison.png`);

  // Stress only rendering through an explicitly labelled browser-only fixture.
  // The saved source records still come from the unchanged synthetic API.
  const originalHistory = await (await fetch('http://127.0.0.1:8765/api/threads/fixture-design')).json();
  const longHistory = extendSyntheticHistory(originalHistory);
  await clickText('Investigation', '.aperture-switch button');
  const heapBeforeHistory = await rpc('Runtime.getHeapUsage');
  const historyTransferStart = fixtureTransfers.length;
  requestFixture = (url) => new URL(url).pathname === '/api/threads/fixture-design' ? longHistory : null;
  await rpc('Fetch.enable', { patterns: [{ urlPattern: '*/api/threads/fixture-design*', requestStage: 'Request' }] });
  await wait(`document.querySelector('.thread-header')?.textContent.includes('1,200 turns')`);
  assert(await evaluate(`document.querySelectorAll('.workspace .turn').length <= 40`), 'large history must bound rendered turns');
  const lastRecord = longHistory.turns.at(-1).endSeq;
  await fill('input[aria-label="Find source record"]', String(lastRecord));
  await clickText('Go to record');
  await wait(`document.querySelector('[data-item-id="browser-fixture-turn-1199-answer"]') !== null`);
  assert(await evaluate(`document.querySelectorAll('.workspace .turn').length <= 40`));
  await clickText('Earlier turns');
  await wait(`document.querySelector('[data-item-id="browser-fixture-turn-1159-answer"]') !== null`);
  await clickText('Later turns');
  await wait(`document.querySelector('[data-item-id="browser-fixture-turn-1199-answer"]') !== null`);
  await evaluate(`document.querySelector('.citation-links button').click()`);
  await wait(`document.querySelector('[data-item-id="fixture-design-turn-5-answer"]')?.classList.contains('highlighted')`);
  assert.equal(await compositionIdentity(), resultArrangement, 'off-page source navigation must preserve apertures');
  assert(await evaluate(`document.querySelectorAll('.workspace .turn').length <= 40`));
  // Measure what the browser actually receives. A small DOM window must not
  // conceal complete repeated JSON deliveries or imply bounded memory use.
  const deliveriesBeforeIdle = fixtureTransfers.slice(historyTransferStart).filter((item) => item.path === '/api/threads/fixture-design').length;
  for (let attempt = 0; attempt < 40; attempt++) {
    if (fixtureTransfers.slice(historyTransferStart).filter((item) => item.path === '/api/threads/fixture-design').length > deliveriesBeforeIdle) break;
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  const historyTransfers = fixtureTransfers.slice(historyTransferStart).filter((item) => item.path === '/api/threads/fixture-design');
  const fullHistoryBytes = Buffer.byteLength(JSON.stringify(longHistory));
  const windowProjectionBytes = Buffer.byteLength(JSON.stringify({ ...longHistory, turns: longHistory.turns.slice(0, 40) }));
  assert(historyTransfers.length > deliveriesBeforeIdle, 'an idle browser must still expose the repeated full-payload poll');
  assert(historyTransfers.every((item) => item.decodedJSONBytes === fullHistoryBytes), 'each fixture poll currently transfers the entire history');
  assert(fullHistoryBytes > windowProjectionBytes * 5, 'the fixture must distinguish DOM bounds from complete payload size');
  const heapAfterHistory = await rpc('Runtime.getHeapUsage');
  const historyRetrieval = {
    source: 'CDP-intercepted synthetic responses; decoded JSON, not compressed wire bytes',
    fullPayloadBytes: fullHistoryBytes, fortyTurnProjectionBytes: windowProjectionBytes,
    observedFullDeliveries: historyTransfers.length,
    totalDecodedBytes: historyTransfers.reduce((total, item) => total + item.decodedJSONBytes, 0),
    browserHeapBefore: heapBeforeHistory, browserHeapAfter: heapAfterHistory,
    limitation: 'Whole-history retrieval and retention remain unbounded. Heap snapshots include browser application activity; this is not a memory bound or leak test.'
  };
  await fs.writeFile(`${evidencePrefix}-retrieval.json`, `${JSON.stringify({ schemaVersion: 1, turns: longHistory.turns.length, renderedTurnLimit: 40, ...historyRetrieval }, null, 2)}\n`);
  await rpc('Fetch.disable');
  requestFixture = null;
  assert.equal(JSON.stringify([await getWork(identifier), await getWork(alternative.id)]), unchangedWorks, 'presentation changes must not mutate saved investigations');

  // Supplementary semantic rendering example. The real synthetic worker returns
  // the same conclusion each time; this separately labelled projection exercises
  // a competing passage, a returned patch and an unsupported citation. Its native
  // output mapping and adoption are cleared, and the API objects remain untouched.
  const projectedAlternative = competingInterpretation(completedAlternative);
  const listed = await (await fetch('http://127.0.0.1:8765/api/investigations')).json();
  requestFixture = (url) => {
    const path = new URL(url).pathname;
    if (path === '/api/investigations') return { ...listed, investigations: listed.investigations.map((item) => item.id === alternative.id ? projectedAlternative : item) };
    if (path === `/api/investigations/${alternative.id}`) return projectedAlternative;
    return null;
  };
  await rpc('Fetch.enable', { patterns: [{ urlPattern: '*/api/investigations*', requestStage: 'Request' }] });
  await clickText('Compare', '.aperture-switch button');
  await wait(`document.querySelector('[data-aperture="right"]')?.textContent.includes('This exact artifact version is unavailable')`);
  await clickText('Edit arrangement');
  await select('#compare-right-artifact', projectedAlternative.artifact.id);
  await clickText('Review arrangement');
  await clickText('Apply arrangement');
  await wait(`document.querySelector('[data-aperture="right"]')?.textContent.includes('Synthetic presentation fixture')`);
  await wait(`document.querySelector('[data-aperture="right"] .native-patch .added') !== null`);
  assert(await evaluate(`document.querySelector('[data-aperture="right"] .native-patch .removed').textContent.includes('launch another specialist')`));
  await evaluate(`[...document.querySelectorAll('[data-aperture="right"] .work-block')].find(e => e.textContent.includes('[evidence:9999]')).querySelector('button.support-action').click()`);
  await wait(`document.querySelector('.focus-evidence button[data-evidence-seq="9999"]')?.disabled === true`);
  assert.equal(await evaluate(`document.querySelector('.focus-evidence .frozen-record')`), null, 'unsupported citation must never resolve to a record');
  assert(await evaluate(`document.querySelector('.focus-evidence').textContent.includes('outside packet')`));
  await evaluate(`[...document.querySelectorAll('[data-aperture="right"] .work-block')].find(e => e.textContent.includes('[evidence:72]')).querySelector('button.support-action').click()`);
  await wait(`document.querySelector('.focus-evidence .frozen-record')?.dataset.evidenceSeq === '72'`);
  assert(await evaluate(`document.querySelector('.focus-evidence .frozen-record').textContent.includes('worker returned before ModelPreparedStep was saved')`));
  for (const width of [900, 390]) {
    await rpc('Emulation.setDeviceMetricsOverride', { width, height: 1000, deviceScaleFactor: 1, mobile: false });
    assert(await evaluate(`document.documentElement.scrollWidth <= ${width} + 1`), `page must not overflow horizontally at ${width}px`);
    assert(await evaluate(`document.querySelector('.comparison-surface').scrollWidth <= document.querySelector('.comparison-surface').clientWidth + 1`), `comparison must wrap at ${width}px`);
  }
  await rpc('Emulation.setDeviceMetricsOverride', { width: 1600, height: 1000, deviceScaleFactor: 1, mobile: false });
  await evaluate(`document.querySelector('.comparison-diff').open = false; window.scrollTo(0, 0); document.querySelector('.thread-rail').scrollTop = 0`);
  await screenshot(`${evidencePrefix}-workbench.png`);
  // A real unknown status has a question and an explicit uncertainty statement,
  // not fabricated live activity or a successful answer.
  projectedAlternative.status = 'unknown';
  projectedAlternative.artifact = null;
  projectedAlternative.attempt.status = 'unknown';
  projectedAlternative.attempt.error = 'Synthetic browser fixture: completion was not recorded; delivery remains unknown.';
  await wait(`document.querySelector('[data-aperture="right"] .state-label')?.textContent === 'unknown'`);
  assert(await evaluate(`document.querySelector('[data-aperture="right"] .pending-question').textContent.includes('Could the inner prepared checkpoint')`));
  assert(await evaluate(`document.querySelector('[data-aperture="right"]').textContent.includes('Missing output does not establish that nothing ran.')`));
  assert.equal(await evaluate(`document.querySelector('[data-aperture="right"] .work-content')`), null, 'unknown outcome must not render a completed artifact');
  await rpc('Fetch.disable');
  requestFixture = null;
  assert.equal(JSON.stringify([await getWork(identifier), await getWork(alternative.id)]), unchangedWorks, 'presentation fixture must not mutate authoritative objects');

  // Integrated local review: retain an exact native baseline while the outer
  // work waits, disclose evidence, then compare its separately named receipt.
  await clickText('Edit arrangement');
  await select('#compare-left', alternative.id);
  await select('#compare-right', alternative.id);
  await select('#compare-left-artifact', completedAlternative.artifact.id);
  await select('#compare-right-artifact', completedAlternative.artifact.id);
  await clickText('Review arrangement');
  await clickText('Apply arrangement');
  const nativeBaseline = await compositionIdentity();
  await clickText('Investigation', '.aperture-switch button');
  await select('#saved-investigation', alternative.id);
  await wait(`document.querySelector('#investigation-title')?.value === ${JSON.stringify(alternative.title)}`);
  await evaluate(`document.querySelector('.context-provenance').open = true`);
  await wait(`document.querySelector('.request-pin')?.textContent.includes(${JSON.stringify(completedAlternative.attempt.manifestId)})`);
  assert(await evaluate(`document.querySelector('.context-provenance').textContent.includes('PROJECTED / app_server')`));
  assert(await evaluate(`document.querySelector('.context-provenance').textContent.includes('Unknown at provider')`));
  await evaluate(`[...document.querySelectorAll('.manifest-slot')].find(e => e.querySelector('summary').textContent.includes('native/unknown')).open = true; document.querySelector('.context-provenance').scrollIntoView({block:'start'})`);
  await screenshot(`${evidencePrefix}-context-provenance.png`);
  const pinBefore = await (await fetch(`http://127.0.0.1:8765/api/investigations/${alternative.id}/context-lineage`)).json();
  await evaluate(`document.querySelector('.start-review').open = true`);
  await fill('#review-question', 'Which evidence should we retain before adopting this recovery conclusion?');
  await clickText('Start local evidence review');
  await wait(`document.querySelector('.review-status')?.textContent.includes('Local continuation pending')`);
  const waiting = await getWork(alternative.id);
  assert.equal(waiting.nativeArtifact.id, completedAlternative.artifact.id);
  assert.equal(waiting.artifact, null);
  assert(await evaluate(`document.querySelector('.investigation-result').textContent.includes('Original specialist result')`));
  assert.equal(await evaluate(`document.querySelector('#adoption-note')`), null);
  await fill('#review-note', 'Keep the inquiry pending while I inspect the earlier experiment.');
  await clickText('Defer review');
  await clickText('Confirm defer');
  await wait(`document.querySelector('.response-history')?.textContent.includes('Deferred')`);
  await reload();
  await wait(`document.querySelector('.response-history')?.textContent.includes('Deferred')`);
  const deferred = await getWork(alternative.id);
  assert.equal(deferred.continuation.id, waiting.continuation.id);
  assert.equal(deferred.continuation.checkpointId, waiting.continuation.checkpointId);
  await evaluate(`document.querySelector('.evidence-review').scrollIntoView({block:'center'})`);
  await screenshot(`${evidencePrefix}-local-review.png`);
  await clickText('Compare', '.aperture-switch button');
  await wait(`document.querySelector('[data-aperture="left"]')?.textContent.includes('Owner-started local evidence review')`);
  assert.equal(await compositionIdentity(), nativeBaseline, 'pending review must not replace pinned native baseline');
  assert(await evaluate(`document.querySelector('[data-aperture="left"] .work-content').textContent.includes('Synthetic specialist result')`));
  await clickText('Investigation', '.aperture-switch button');
  await fill('#review-note', 'Retain the reviewed two-thread evidence; native input remains unchanged.');
  await clickText('Review offer from current tray');
  await wait(`document.querySelector('.disclosure-preview')?.textContent.includes('Offer these exact ranges')`);
  await clickText('Confirm offer');
  await wait(`document.querySelector('.review-status')?.textContent.includes('Local continuation completed')`);
  const reviewed = await getWork(alternative.id);
  const offered = reviewed.continuation.inquiry.responses.find((r) => r.decision === 'offer').evidenceContext;
  assert(offered.manifestId);
  assert.equal(reviewed.nativeArtifact.id, completedAlternative.artifact.id);
  assert.notEqual(reviewed.artifact.id, reviewed.nativeArtifact.id);
  const pinAfter = await (await fetch(`http://127.0.0.1:8765/api/investigations/${alternative.id}/context-lineage`)).json();
  assert.deepEqual(pinAfter.attempt, pinBefore.attempt, 'local disclosure must not repin or synthesize native observations');
  await clickText('Compare', '.aperture-switch button');
  await wait(`document.querySelector('[data-aperture="left"]')?.textContent.includes('Owner-started local evidence review · completed')`);
  assert.equal(await compositionIdentity(), nativeBaseline, 'reintegration must preserve baseline artifact version');
  await clickText('Edit arrangement');
  await select('#compare-right-artifact', reviewed.artifact.id);
  await clickText('Review arrangement');
  await clickText('Apply arrangement');
  await wait(`document.querySelector('[data-aperture="right"] .work-content')?.textContent.includes('not a new native analysis')`);
  assert.equal(await evaluate(`document.querySelector('[data-aperture="left"]').dataset.artifactId`), reviewed.nativeArtifact.id);
  assert(await evaluate(`[...document.querySelectorAll('.comparison-aperture')].every(e => e.scrollWidth <= e.clientWidth + 1)`), 'receipt comparison must not overflow either aperture');
  await evaluate(`document.querySelector('.comparison-diff').open = true; window.scrollTo(0,0)`);
  await screenshot(`${evidencePrefix}-review-comparison.png`);
  await clickText('Investigation', '.aperture-switch button');
  await fill('#adoption-note', 'Adopt the reviewed conclusion; retain the original answer and disclosure provenance.');
  await clickText('Adopt conclusion');
  await wait(`document.querySelector('.adoption-receipt')?.textContent.includes('Conclusion adopted')`);
  assert.equal((await getWork(alternative.id)).adoption.artifactId, reviewed.artifact.id);

  // The same attention intent resolves real recorded local-review objects.
  // Presentation operations must never become disclosure/adoption requests.
  const savedWorkBeforeAttention = JSON.stringify([await getWork(identifier), await getWork(alternative.id)]);
  const mutationCount = () => apiRequests.filter((request) => !['GET', 'HEAD'].includes(request.method)).length;
  const mutationsBeforeAttention = mutationCount();
  await clickText('Compare', '.aperture-switch button');
  await wait(`document.querySelector('#arrange-evidence-chain')?.disabled === false`);
  assert(await evaluate(`document.querySelector('#arrange-alternative').disabled`), 'a missing experiment must not be actionable');
  await clickText('Original evidence → request → result', '#arrange-evidence-chain');
  await wait(`document.querySelector('.arrangement-review') !== null`);
  await clickText('Apply arrangement');
  await wait(`document.querySelector('[data-inquiry-role="result"]')?.dataset.artifactId === ${JSON.stringify(reviewed.artifact.id)}`);
  assert.equal(await evaluate(`document.querySelector('[data-inquiry-role="original"]').dataset.artifactId`), reviewed.nativeArtifact.id);
  assert.equal(await evaluate(`document.querySelector('[data-inquiry-role="requested"]').dataset.contextId`), offered.id);
  assert.equal(await evaluate(`document.querySelector('[data-inquiry-role="result"]').dataset.contextId`), reviewed.artifact.contextId);
  assert(await evaluate(`document.querySelector('[data-inquiry-role="result"]').textContent.includes('Local Eidos decision receipt')`));
  const recordedChain = await inquiryIdentity();
  await evaluate(`document.querySelector('[data-inquiry-role="requested"] .record-index button').focus()`);
  await keypress('Enter', 'Enter', 13);
  await wait(`document.querySelector('.focus-evidence')?.dataset.contextId === ${JSON.stringify(offered.id)}`);
  await reload();
  await wait(`document.querySelector('[data-inquiry-role="requested"]')?.dataset.contextId === ${JSON.stringify(offered.id)}`);
  assert.equal(await inquiryIdentity(), recordedChain);
  assert.equal(await evaluate(`document.querySelector('.focus-evidence').dataset.contextId`), offered.id);
  await evaluate(`document.querySelector('.inquiry-chain').scrollIntoView({block:'start'})`);
  await screenshot(`${evidencePrefix}-recorded-evidence-chain.png`);

  // An explicit authored scenario supplies the not-yet-supported specialist
  // inquiry and experiment. Opening it only stages an arrangement change.
  await clickText('Open synthetic inquiry & experiment');
  await wait(`document.querySelector('.arrangement-review') !== null`);
  assert.equal(await inquiryIdentity(), recordedChain, 'opening a fixture must not apply its arrangement');
  await clickText('Apply arrangement');
  await wait(`document.querySelector('[data-inquiry-role="original"]')?.dataset.artifactId === 'fixture:recovery-original-artifact-v1'`);
  assert.equal(await evaluate(`document.querySelector('[data-inquiry-role="original"]').dataset.contextId`), 'fixture:recovery-original-context-v1');
  assert.equal(await evaluate(`document.querySelector('[data-inquiry-role="requested"]').dataset.contextId`), '');
  assert.equal(await evaluate(`document.querySelector('[data-inquiry-role="result"]').dataset.artifactId`), '');
  assert(await evaluate(`document.querySelector('.inquiry-status').textContent.includes('Pending evidence')`));
  assert(await evaluate(`document.querySelector('.inquiry-lead').textContent.includes('No model was called')`));
  const pendingFixtureChain = await inquiryIdentity();
  await evaluate(`document.querySelector('.inquiry-chain').scrollIntoView({block:'start'})`);
  await screenshot(`${evidencePrefix}-pending-inquiry.png`);

  await clickText('Preview supplied-evidence outcome');
  await wait(`document.querySelector('.arrangement-review')?.textContent.includes('fixture:recovery-offered-context-v1')`);
  assert.equal(await inquiryIdentity(), pendingFixtureChain, 'a newly available outcome must not silently replace the pending result binding');
  await clickText('Apply arrangement');
  await wait(`document.querySelector('[data-inquiry-role="requested"]')?.dataset.contextId === 'fixture:recovery-offered-context-v1'`);
  assert.equal(await evaluate(`document.querySelector('[data-inquiry-role="result"]').dataset.artifactId`), 'fixture:recovery-receipt-artifact-v1');
  assert.equal(await evaluate(`document.querySelector('[data-inquiry-role="original"]').dataset.artifactId`), 'fixture:recovery-original-artifact-v1');
  assert(await evaluate(`document.querySelector('[data-inquiry-role="result"]').textContent.includes('not a new model conclusion')`));
  const suppliedFixtureChain = await inquiryIdentity();
  await evaluate(`document.querySelector('[data-inquiry-role="requested"] .record-index button').focus()`);
  await keypress('Enter', 'Enter', 13);
  await wait(`document.querySelector('.focus-evidence .frozen-record')?.dataset.evidenceSeq === '72'`);
  assert.equal(await evaluate(`document.querySelector('.focus-evidence').dataset.contextId`), 'fixture:recovery-offered-context-v1');
  await reload();
  await wait(`document.querySelector('[data-inquiry-role="requested"]')?.dataset.contextId === 'fixture:recovery-offered-context-v1'`);
  assert.equal(await inquiryIdentity(), suppliedFixtureChain);
  await wait(`document.querySelector('.focus-evidence .frozen-record')?.dataset.evidenceSeq === '72'`);
  assert.equal(await evaluate(`document.querySelector('.focus-evidence').dataset.contextId`), 'fixture:recovery-offered-context-v1');
  await clickText('Edit arrangement');
  await select('#compare-layout', 'stacked');
  await clickText('Review arrangement');
  await clickText('Apply arrangement');
  await wait(`document.querySelector('.inquiry-columns')?.classList.contains('stacked')`);
  const stackedRects = await evaluate(`[...document.querySelectorAll('.inquiry-columns > article')].map(e => { const r = e.getBoundingClientRect(); return { x:r.x, y:r.y, height:r.height }; })`);
  assert.equal(stackedRects.length, 3);
  for (let index = 1; index < stackedRects.length; index++) {
    assert(Math.abs(stackedRects[index].x - stackedRects[0].x) <= 1, 'stacked inquiry cards must share their horizontal origin');
    assert(stackedRects[index].y >= stackedRects[index - 1].y + stackedRects[index - 1].height - 1, 'stacked inquiry cards must appear one below another');
  }
  assert.equal(await inquiryIdentity(), suppliedFixtureChain, 'stacking must not change inquiry bindings');
  await clickText('Undo arrangement');
  await wait(`document.querySelector('.comparison-surface')?.dataset.layout === 'beside'`);
  assert.equal(await inquiryIdentity(), suppliedFixtureChain);
  await evaluate(`document.querySelector('.inquiry-chain').scrollIntoView({block:'start'})`);
  await screenshot(`${evidencePrefix}-supplied-evidence-chain.png`);

  // Structured input is data: an unsupported intent cannot dispatch anything.
  await evaluate(`document.querySelector('.structured-attention').open = true`);
  await fill('#arrangement-request', JSON.stringify({ version: 1, intent: 'dispatch', investigationId: identifier }));
  await clickText('Preview attention request');
  await wait(`document.querySelector('.attention-intents [role="alert"]')?.textContent.includes('Unsupported attention intent')`);
  assert.equal(await inquiryIdentity(), suppliedFixtureChain);
  await evaluate(`document.querySelector('.structured-attention').open = false`);

  await clickText('Compare the named alternative', '#arrange-alternative');
  await wait(`document.querySelector('.arrangement-review') !== null`);
  assert.equal(await inquiryIdentity(), suppliedFixtureChain);
  await clickText('Cancel changes');
  assert.equal(await inquiryIdentity(), suppliedFixtureChain);
  await clickText('Compare the named alternative', '#arrange-alternative');
  await clickText('Apply arrangement');
  await wait(`document.querySelector('.experiment-heading')?.dataset.experimentId === 'fixture:recovery-experiment-v1'`);
  assert.equal(await evaluate(`document.querySelector('[data-aperture="left"]').dataset.artifactId`), 'fixture:recovery-original-artifact-v1');
  assert.equal(await evaluate(`document.querySelector('[data-aperture="right"]').dataset.artifactId`), 'fixture:recovery-alternative-artifact-v1');
  assert.equal(await evaluate(`document.querySelector('[data-aperture="right"]').dataset.contextId`), 'fixture:recovery-alternative-context-v1');
  assert(await evaluate(`[...document.querySelectorAll('.comparison-diff .diff-row.added')].some(e => e.textContent.includes('72'))`), 'the named alternative must show the added evidence in a native context diff');
  assert(await evaluate(`document.querySelector('.experiment-evaluation').textContent.includes('not a blind prospective evaluation')`));
  const alternativeFixtureArrangement = await compositionIdentity();
  await clickText('Edit arrangement');
  await select('#compare-right', 'fixture:recovery-investigation-v1');
  await clickText('Review arrangement');
  await clickText('Apply arrangement');
  await wait(`document.querySelector('.attention-intents [role="alert"]')?.textContent.includes('requires its exact baseline and alternative')`);
  assert.equal(await compositionIdentity(), alternativeFixtureArrangement, 'editing a named experiment target must not misattribute its evaluation');
  await clickText('Cancel changes');
  await evaluate(`document.querySelector('.experiment-heading').scrollIntoView({block:'start'})`);
  await screenshot(`${evidencePrefix}-named-alternative.png`);

  await clickText('Review improvement', '#review-improvement');
  await wait(`document.querySelector('#improvement-detail') !== null`);
  assert(await evaluate(`document.querySelector('#adopt-improvement').disabled`), 'unsupported durable adoption must remain disabled');
  assert(await evaluate(`document.querySelector('.improvement-review .native-patch .added') !== null`));
  assert(await evaluate(`document.querySelector('.improvement-review').textContent.includes('Expected benefit · hypothesis')`));
  assert(await evaluate(`document.querySelector('.improvement-review').textContent.includes('No real user timing')`));
  await clickText('Review presentation preview', '#preview-adoption');
  await wait(`document.querySelector('#presentation-preview-review') !== null`);
  assert.equal(await evaluate(`document.querySelector('.improvement-review').dataset.previewActive`), 'false');
  assert.equal(await evaluate(`document.querySelector('[data-presentation-preview="evidence-first"]')`), null);
  await clickText('Cancel preview');
  await clickText('Review presentation preview', '#preview-adoption');
  await clickText('Apply presentation preview', '#apply-improvement-preview');
  await wait(`document.querySelector('.improvement-review')?.dataset.previewActive === 'true'`);
  await wait(`document.querySelector('[data-presentation-preview="evidence-first"] .inquiry-chain') !== null`);
  assert.equal(await compositionIdentity(), alternativeFixtureArrangement, 'presentation emphasis must retain the compared artifacts');
  assert(await evaluate(`!!(document.querySelector('[data-presentation-preview="evidence-first"]').compareDocumentPosition(document.querySelector('.comparison-apertures')) & Node.DOCUMENT_POSITION_FOLLOWING)`), 'the adopted browser preview must visibly place evidence before comparison');
  const previewIdentity = await inquiryIdentity();
  assert.equal(previewIdentity, suppliedFixtureChain, 'the presentation preview must use the same exact evidence chain');
  inspectStored(JSON.parse(await evaluate(`localStorage.getItem('nema.composition.v1')`)));
  inspectStored(JSON.parse(await evaluate(`localStorage.getItem('nema.improvement-presentation-preview.v1')`)));
  await reload();
  await wait(`document.querySelector('[data-presentation-preview="evidence-first"] .inquiry-chain') !== null`);
  assert.equal(await compositionIdentity(), alternativeFixtureArrangement);
  assert.equal(await inquiryIdentity(), previewIdentity);
  await clickText('Review improvement', '#review-improvement');
  await evaluate(`document.querySelector('#improvement-evaluation-title').scrollIntoView({block:'start'})`);
  await screenshot(`${evidencePrefix}-improvement-review.png`);
  await clickText('Undo presentation preview', '#undo-improvement-preview');
  await wait(`document.querySelector('.improvement-review')?.dataset.previewActive === 'false'`);
  assert.equal(await evaluate(`document.querySelector('[data-presentation-preview="evidence-first"]')`), null);
  assert.equal(await compositionIdentity(), alternativeFixtureArrangement);
  for (const width of [900, 390]) {
    await rpc('Emulation.setDeviceMetricsOverride', { width, height: 1000, deviceScaleFactor: 1, mobile: false });
    assert(await evaluate(`document.documentElement.scrollWidth <= ${width} + 1`), `reflective workflow must wrap at ${width}px`);
  }
  await rpc('Emulation.setDeviceMetricsOverride', { width: 1600, height: 1000, deviceScaleFactor: 1, mobile: false });
  assert.equal(mutationCount(), mutationsBeforeAttention, 'attention, fixture, and improvement-preview workflows must not issue API mutations');
  assert.equal(JSON.stringify([await getWork(identifier), await getWork(alternative.id)]), savedWorkBeforeAttention, 'attention arrangements and fixture decisions must not alter real synthetic API work');
  // Round 3 integration: real durable API objects, synthetic worker only.
  const capability = await (await fetch('http://127.0.0.1:8765/api/investigations/capabilities')).json();
  assert.equal(capability.nativeExecution.mode, 'synthetic');
  assert.equal(capability.specialistInquiry.interactive, false);
  await clickText('Investigation', '.aperture-switch button');
  await clickText('New alternative from selection');
  await fill('#investigation-title', 'Round 3 specialist inquiry and controlled alternative');
  await fill('#investigation-question', '[synthetic-needs-evidence] Compare the two-thread recovery evidence and ask for missing acknowledgement evidence.');
  await clickText('Save and preview context');
  await wait(`document.querySelector('.exact-input') !== null`);
  const round3Id = await evaluate(`document.querySelector('#saved-investigation').value`);
  await clickText('Start specialist with this context');
  await wait(`document.querySelector('.evidence-review')?.textContent.includes('Specialist evidence inquiry')`);
  await wait(`document.querySelector('.review-question')?.textContent.includes('acknowledgement')`);
  const inquiryStart = await getWork(round3Id);
  assert.equal(inquiryStart.continuation.origin, 'native-specialist');
  assert.equal(inquiryStart.nativeArtifact.executionEvidence, 'synthetic');
  assert.equal(inquiryStart.attempt.status, 'completed');
  assert.equal(await evaluate(`document.querySelector('#adoption-note')`), null, 'an evidence request is not an adoptable conclusion');
  await evaluate(`document.querySelector('.evidence-review').scrollIntoView({block:'start'})`);
  await screenshot(`${evidencePrefix}-specialist-inquiry.png`);
  await fill('#review-note', 'Keep the specialist question pending while locating the missing source.');
  await clickText('Defer review');
  await clickText('Confirm defer');
  await reload();
  await wait(`document.querySelector('.response-history')?.textContent.includes('Deferred')`);
  assert.equal((await getWork(round3Id)).continuation.id, inquiryStart.continuation.id);
  if (await evaluate(`[...document.querySelectorAll('.evidence-review button')].some(e => e.textContent.trim() === 'Retry recorded review action')`)) await clickText('Retry recorded review action');
  await wait(`document.querySelector('#review-note') !== null`);
  assert.equal((await getWork(round3Id)).continuation.inquiry.responses.length, 1, 'recovery retries preserve the source response identity');
  await evaluate(`[...document.querySelectorAll('.thread-button')].find(e => e.textContent.includes('Synthetic design:')).click()`);
  await wait(`document.querySelector('[data-item-id="fixture-design-turn-6-answer"] .source-select') !== null`);
  await evaluate(`document.querySelector('[data-item-id="fixture-design-turn-6-answer"] .source-select').click()`);
  await fill('#review-note', 'Offer the requested separately frozen evidence for this inquiry.');
  await clickText('Review offer from current tray');
  await clickText('Confirm offer');
  await wait(`document.querySelector('.followup-admission')?.textContent.includes('has not been sent')`);
  const incorporated = await getWork(round3Id);
  assert.equal(incorporated.continuation.inquiry.status, 'answered');
  assert.equal(incorporated.attempt.id, inquiryStart.attempt.id, 'local incorporation launches no native attempt');
  assert.equal(incorporated.currentContextId, inquiryStart.currentContextId);
  assert.notEqual(incorporated.continuation.nativeNext.contextId, inquiryStart.currentContextId);
  assert.equal(await evaluate(`document.querySelector('#adoption-note')`), null, 'local incorporation receipt is not a native conclusion');
  await evaluate(`document.querySelector('.followup-admission details').open = true; document.querySelector('.followup-admission').scrollIntoView({block:'start'})`);
  await screenshot(`${evidencePrefix}-followup-admission.png`);
  await evaluate(`document.querySelector('.followup-admission input[type="checkbox"]').click()`);
  await clickText('Run synthetic follow-up');
  await wait(`document.querySelector('.investigation-result h3')?.textContent === 'Follow-up specialist result'`);
  const continued = await getWork(round3Id);
  assert.notEqual(continued.attempt.id, inquiryStart.attempt.id);
  assert.equal(continued.attemptHistory[0].id, inquiryStart.attempt.id);
  assert.equal(continued.nativeArtifact.id, inquiryStart.nativeArtifact.id);
  assert(continued.artifactHistory.some((item) => item.id === incorporated.artifact.id));
  assert.equal(continued.artifact.executionEvidence, 'synthetic');
  assert.equal(continued.artifact.continuedFrom.responseId, incorporated.continuation.inquiry.responses.find((item) => item.decision === 'offer').id);
  await select('#experiment-baseline', continued.nativeArtifact.id);
  await select('#experiment-alternative', continued.currentContextId);
  await fill('#experiment-rationale', 'Retain the original evidence while making the requested observation available to a future input recipe.');
  await clickText('Review controlled alternative');
  await wait(`document.querySelector('.experiment-preview')?.textContent.includes('Frozen inputs for comparison')`);
  await clickText('Evaluate saved inputs');
  await wait(`document.querySelector('.recorded-experiment')?.dataset.experimentStatus === 'evaluated'`);
  assert(await evaluate(`document.querySelector('.recorded-experiment').textContent.includes('Better reasoning or user benefit is unmeasured')`));
  await evaluate(`document.querySelector('.recorded-experiments').scrollIntoView({block:'start'})`);
  await screenshot(`${evidencePrefix}-evaluated-alternative.png`);
  await fill('.recorded-experiment textarea', 'Structural retention is established; accept this proposal as a recorded candidate, with no configuration activation.');
  await clickText('Adopt recorded proposal');
  await wait(`document.querySelector('.recorded-experiment')?.dataset.experimentStatus === 'adopted'`);
  await reload();
  await wait(`document.querySelector('.recorded-experiment')?.dataset.experimentStatus === 'adopted'`);
  await fill('.recorded-experiment textarea', 'Restore the previous recorded version pending real usefulness evaluation.');
  await clickText('Record rollback');
  await wait(`document.querySelector('.recorded-experiment')?.dataset.experimentStatus === 'rolled-back'`);
  await select('#experiment-baseline', continued.nativeArtifact.id);
  await select('#experiment-alternative', continued.currentContextId);
  await fill('#experiment-rationale', 'Retain a rejected selection proposal alongside the accepted and rolled-back experiment.');
  await clickText('Review controlled alternative');
  await clickText('Evaluate saved inputs');
  await wait(`document.querySelectorAll('.recorded-experiment').length === 2`);
  await fill('.recorded-experiment[data-experiment-status="evaluated"] textarea', 'Selection measurements alone do not establish useful reasoning improvement.');
  await clickText('Reject recorded proposal');
  await wait(`[...document.querySelectorAll('.recorded-experiment')].some(e => e.dataset.experimentStatus === 'rejected')`);
  const round3Experiments = await (await fetch(`http://127.0.0.1:8765/api/investigations/${round3Id}/experiments`)).json();
  assert.deepEqual(round3Experiments.experiments.map((item) => item.status).sort(), ['rejected', 'rolled-back']);
  assert(round3Experiments.experiments.every((item) => item.evaluation.modelCalls === 0 && item.evaluation.measuredModelReasoningImprovement === false));
  await evaluate(`document.querySelector('.recorded-experiments').scrollIntoView({block:'start'})`);
  await screenshot(`${evidencePrefix}-preserved-decisions.png`);
  await clickText('Follow evidence & response');
  await wait(`document.querySelector('.arrangement-review') !== null`);
  await clickText('Apply arrangement');
  await wait(`document.querySelector('[data-inquiry-role="result"]')?.dataset.artifactId === ${JSON.stringify(continued.artifact.id)}`);
  assert.equal(await evaluate(`document.querySelector('[data-inquiry-role="original"]').dataset.contextId`), inquiryStart.currentContextId);
  assert.equal(await evaluate(`document.querySelector('[data-inquiry-role="result"]').dataset.contextId`), continued.currentContextId);
  assert.equal(await evaluate(`document.querySelector('.inquiry-chain .work-error')`), null);
  await evaluate(`document.querySelector('.inquiry-chain').scrollIntoView({block:'start'})`);
  await screenshot(`${evidencePrefix}-integrated-evidence-chain.png`);
  await reload();
  await wait(`document.querySelector('[data-inquiry-role="result"]')?.dataset.artifactId === ${JSON.stringify(continued.artifact.id)}`);
  for (const width of [900, 390]) {
    await rpc('Emulation.setDeviceMetricsOverride', { width, height: 1000, deviceScaleFactor: 1, mobile: false });
    assert(await evaluate(`document.documentElement.scrollWidth <= ${width} + 1`), `integrated evidence chain wraps at ${width}px`);
  }
  await rpc('Emulation.setDeviceMetricsOverride', { width: 1600, height: 1000, deviceScaleFactor: 1, mobile: false });
  console.log(JSON.stringify({
    passed: true, investigationId: identifier, alternativeId: alternative.id, round3Id, round3ExperimentStatuses: round3Experiments.experiments.map((item) => item.status),
    records: 3, sourceThreads: 2, revisions: 2, status: final.status,
    adoption: final.adoption.decision, compared: ['saved investigations', 'context revisions', 'returned artifacts'],
    verified: ['review/cancel/apply/undo', 'keyboard support navigation', 'cross-aperture focus', 'reload', 'presentation does not mutate server work', 'context manifest and immutable request pin', 'defer/reload/offer/adopt', 'native artifact version survives local review', 'recorded original/offered/result attention arrangement', 'explicit pending/supplied inquiry fixture', 'named counterfactual and exact context diff', 'unsupported intent rejected without dispatch', 'inspectable improvement and reversible evidence-first browser preview', 'unsupported durable adoption disabled', 'all attention workflows issue zero API mutations', 'durable specialist inquiry with deferral and separately offered evidence', 'separately admitted synthetic A2 preserves A1 and receipt', 'controlled saved-input evaluation with adoption, rollback and rejection', 'A2 exact context/artifact chain survives reload'],
    history: { source: 'browser-only synthetic projection', turns: longHistory.turns.length, renderedTurnLimit: 40, retrieval: historyRetrieval },
    retrievalEvidence: `${evidencePrefix}-retrieval.json`,
    supplementary: 'Browser-only competing artifact with outputSeqs cleared; native diff, unavailable citation, unknown question and 900/390px overflow verified; no API mutation',
    screenshots: ['workbench', 'server-comparison', 'context-diff', 'context-provenance', 'local-review', 'review-comparison', 'recorded-evidence-chain', 'pending-inquiry', 'supplied-evidence-chain', 'named-alternative', 'improvement-review', 'specialist-inquiry', 'followup-admission', 'evaluated-alternative', 'preserved-decisions', 'integrated-evidence-chain'].map((name) => `${evidencePrefix}-${name}.png`)
  }, null, 2));
} catch (error) {
  await screenshot('/tmp/nema-reflective-acceptance-failure.png').catch(() => {});
  console.error('Failure screenshot: /tmp/nema-reflective-acceptance-failure.png');
  console.error(await evaluate(`document.body.innerText.slice(-10000)`).catch(() => 'DOM unavailable'));
  throw error;
} finally {
  await fetch(`http://127.0.0.1:9222/json/close/${target.id}`).catch(() => {});
  socket.close();
}
