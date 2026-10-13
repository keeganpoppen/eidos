// Supplementary rendered history checks. Run after check_investigation_ui.mjs
// against the same synthetic demo, Vite :5173 and isolated Chromium :9222.
// Delay real HTTP requests to challenge navigation races; never alter bodies.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import { persistedHistory } from './fixtures/reflective_history.mjs';

const prefix = process.env.NEMA_UI_EVIDENCE_PREFIX ?? '/tmp/nema-history-navigation';
const source = await (await fetch(`http://127.0.0.1:8765/api/threads/${persistedHistory.threadId}`)).json();
const node = source.outline.nodes.find((candidate) => candidate.node_id === persistedHistory.semanticNodeId);
const [rejectionSeq, decisionSeq] = node.support.map((span) => span.start);
const decisionPage = await (await fetch(`http://127.0.0.1:8765/api/threads/${persistedHistory.threadId}?aroundSeq=${decisionSeq}`)).json();
const neighbor = await (await fetch(`http://127.0.0.1:8765/api/threads/${persistedHistory.neighborThreadId}`)).json();
const neighborSeq = neighbor.turns[0].items.find((item) => item.id === persistedHistory.neighborItemId).startSeq;
const target = await (await fetch('http://127.0.0.1:9222/json/new?http://127.0.0.1:5173', { method: 'PUT' })).json();
const socket = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve) => socket.addEventListener('open', resolve, { once: true }));
let sequence = 0;
let documentLoads = 0;
const pending = new Map();
let delayedSeq = null;
let heldRequest = null;
let delayedStatus = null;
socket.addEventListener('message', (event) => {
  const message = JSON.parse(event.data);
  if (message.method === 'Page.loadEventFired') documentLoads++;
  if (message.id) {
    const request = pending.get(message.id);
    pending.delete(message.id);
    message.error ? request.reject(Error(JSON.stringify(message.error))) : request.resolve(message.result);
  }
  if (message.method === 'Fetch.requestPaused') {
    const seq = new URL(message.params.request.url).searchParams.get('aroundSeq');
    if (seq === delayedSeq) heldRequest = message.params.requestId;
    else void rpc('Fetch.continueRequest', { requestId: message.params.requestId });
  }
  if (message.method === 'Network.responseReceived') {
    const response = message.params.response;
    if (new URL(response.url).searchParams.get('aroundSeq') === delayedSeq) delayedStatus = response.status;
  }
});
const rpc = (method, params = {}) => new Promise((resolve, reject) => {
  pending.set(++sequence, { resolve, reject });
  socket.send(JSON.stringify({ id: sequence, method, params }));
});
const evaluate = async (expression) => {
  const result = await rpc('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
  if (result.exceptionDetails) throw Error(JSON.stringify(result.exceptionDetails));
  return result.result.value;
};
const wait = async (condition, description) => {
  for (let attempt = 0; attempt < 100; attempt++) {
    try { if (await condition()) return; } catch { /* Reload may replace the execution context. */ }
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw Error(`UI condition did not arrive: ${description}`);
};
const visibleSource = (itemId) => wait(() => evaluate(`document.querySelector('.workspace [data-item-id="${itemId}"]')?.classList.contains('highlighted')`), itemId);
const reload = async () => {
  const previous = documentLoads;
  await rpc('Page.reload');
  await wait(() => documentLoads > previous, 'new document loaded');
};
const goToRecord = (seq) => evaluate(`(() => {
  const input = document.querySelector('input[aria-label="Find source record"]');
  input.value = '${seq}'; input.dispatchEvent(new Event('input', { bubbles: true }));
  document.querySelector('.history-navigation form').requestSubmit();
})()`);
const screenshot = async (suffix) => {
  await evaluate(`document.querySelector('.workspace').scrollTop = 0; window.scrollTo(0, 0)`);
  await evaluate(`new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))`);
  await fs.writeFile(`${prefix}-${suffix}.png`, Buffer.from((await rpc('Page.captureScreenshot', { format: 'png' })).data, 'base64'));
};
try {
  await rpc('Page.enable');
  await rpc('Network.enable');
  await rpc('Emulation.setDeviceMetricsOverride', { width: 1600, height: 1000, deviceScaleFactor: 1, mobile: false });
  await wait(() => evaluate(`document.querySelector('.aperture-switch') !== null`), 'initial page');
  await evaluate(`localStorage.clear(); localStorage.setItem('nema.source-focus.v1', ${JSON.stringify(JSON.stringify({
    threadId: persistedHistory.threadId, revision: '', anchorSeq: decisionPage.window.anchorSeq,
    selectedNodeId: node.node_id, spans: node.support, workMode: false
  }))})`);
  await reload();
  await visibleSource(persistedHistory.decisionItemId);
  await rpc('Fetch.enable', { patterns: [{ urlPattern: `*/api/threads/${persistedHistory.threadId}*`, requestStage: 'Request' }] });
  delayedSeq = String(neighborSeq);
  await goToRecord(neighborSeq);
  await wait(() => heldRequest !== null, 'held wrong-thread request');
  await goToRecord(decisionSeq);
  await wait(() => evaluate(`document.querySelector('.history-navigation p[role="status"]')?.textContent.includes('${decisionSeq}')`), 'newer source notice');
  await rpc('Fetch.continueRequest', { requestId: heldRequest });
  await wait(() => delayedStatus === 404, 'real wrong-thread rejection');
  await new Promise((resolve) => setTimeout(resolve, 200));
  assert(await evaluate(`document.querySelector('.history-navigation p[role="status"]').textContent.includes('${decisionSeq}')`));
  await visibleSource(persistedHistory.decisionItemId);

  delayedSeq = String(rejectionSeq); heldRequest = null; delayedStatus = null;
  await evaluate(`document.querySelector('.semantic-node').click()`);
  await wait(() => heldRequest !== null, 'held semantic source request');
  await evaluate(`document.querySelector('.source-focus-notice .inline-control:not(.source-range)').click()`);
  await rpc('Fetch.continueRequest', { requestId: heldRequest });
  await wait(() => delayedStatus === 200, 'real semantic source response');
  await new Promise((resolve) => setTimeout(resolve, 200));
  assert.equal(await evaluate(`document.querySelector('.source-focus-notice')`), null);
  assert.equal(await evaluate(`document.querySelectorAll('.workspace .highlighted').length`), 0);
  assert.equal(await evaluate(`document.querySelector('[data-testid="history-window"]').dataset.anchorSeq`), String(decisionPage.window.anchorSeq));
  await rpc('Fetch.disable');

  await evaluate(`document.querySelector('.semantic-node').click()`);
  await visibleSource(persistedHistory.rejectionItemId);
  for (const [width, seq, itemId] of [
    [900, decisionSeq, persistedHistory.decisionItemId],
    [390, rejectionSeq, persistedHistory.rejectionItemId]
  ]) {
    await rpc('Emulation.setDeviceMetricsOverride', { width, height: 1000, deviceScaleFactor: 1, mobile: false });
    await reload();
    await wait(() => evaluate(`document.querySelectorAll('.source-focus-notice [data-support-start]').length === 2`), 'restored disjoint sources');
    await evaluate(`document.querySelector('.source-focus-notice [data-support-start="${seq}"]').click()`);
    await visibleSource(itemId);
    assert.equal(await evaluate(`document.querySelector('.source-focus-notice [data-support-start="${seq}"]').getAttribute('aria-current')`), 'location');
    assert(await evaluate(`document.documentElement.scrollWidth <= ${width} + 1`), `overflow at ${width}px`);
    await screenshot(`navigation-${width}`);
  }
  await rpc('Emulation.setDeviceMetricsOverride', { width: 1600, height: 1000, deviceScaleFactor: 1, mobile: false });
  await evaluate(`document.querySelector('.source-focus-notice [data-support-start="${decisionSeq}"]').click()`);
  await visibleSource(persistedHistory.decisionItemId);
  await screenshot('navigation-1600');
  await evaluate(`document.querySelector('.workspace [data-item-id="${persistedHistory.decisionItemId}"]').scrollIntoView({ block: 'center' })`);
  await fs.writeFile(`${prefix}-decision.png`, Buffer.from((await rpc('Page.captureScreenshot', { format: 'png' })).data, 'base64'));
  const report = { passed: true, source: 'Persisted synthetic history in actual Chromium; real HTTP bodies unmodified',
    delayedWrongThreadRejectionCannotReplaceNewerFocus: true, clearFocusCancelsDelayedSourceReveal: true,
    restoredDisjointSourcesNavigableAtWidths: [900, 390], horizontalDocumentOverflow: false,
    limitation: 'Supplementary race requests are intentionally delayed; these are separate from the unintercepted retrieval byte measurements.' };
  await fs.writeFile(`${prefix}-navigation.json`, `${JSON.stringify(report, null, 2)}\n`);
  console.log(JSON.stringify(report, null, 2));
} finally {
  await rpc('Fetch.disable').catch(() => {});
  await fetch(`http://127.0.0.1:9222/json/close/${target.id}`).catch(() => {});
  socket.close();
}
