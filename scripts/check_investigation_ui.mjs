// Synthetic rendered acceptance. Requires demo API :8765, Vite :5173, and
// isolated Chromium --remote-debugging-port=9222. No npm dependencies/model calls.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';

const target = await (await fetch('http://127.0.0.1:9222/json/new?http://127.0.0.1:5173', { method: 'PUT' })).json();
const socket = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve) => socket.addEventListener('open', resolve, { once: true }));
let sequence = 0;
const pending = new Map();
socket.addEventListener('message', (event) => {
  const message = JSON.parse(event.data);
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
const clickText = async (text, selector = 'button') => evaluate(`(() => {
  const element = [...document.querySelectorAll(${JSON.stringify(selector)})].find(e => e.textContent.trim() === ${JSON.stringify(text)});
  if (!element || element.disabled) throw Error('Action unavailable: ' + ${JSON.stringify(text)});
  element.click();
})()`);
const fill = async (selector, value) => evaluate(`(() => {
  const e = document.querySelector(${JSON.stringify(selector)});
  e.value = ${JSON.stringify(value)}; e.dispatchEvent(new Event('input', {bubbles:true}));
})()`);

try {
  await rpc('Emulation.setDeviceMetricsOverride', { width: 1600, height: 1000, deviceScaleFactor: 1, mobile: false });
  await wait(`document.querySelector('#investigation-title') !== null`);
  await evaluate(`localStorage.clear()`);
  await rpc('Page.reload');
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
  await clickText('Start specialist with this context');
  await wait(`document.querySelector('.work-status')?.textContent.includes('completed')`);
  await wait(`document.querySelector('.investigation-result')?.textContent.includes('Synthetic specialist result')`);
  await rpc('Page.reload');
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
  await rpc('Page.reload');
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
  await fs.mkdir('docs/evidence', { recursive: true });
  await fs.writeFile('docs/evidence/investigation-workbench.png', Buffer.from((await rpc('Page.captureScreenshot', { format: 'png' })).data, 'base64'));
  console.log(JSON.stringify({ passed: true, investigationId: identifier, records: 3, sourceThreads: 2, revisions: 2, status: final.status, adoption: final.adoption.decision, screenshot: 'docs/evidence/investigation-workbench.png' }, null, 2));
} finally {
  socket.close();
}
