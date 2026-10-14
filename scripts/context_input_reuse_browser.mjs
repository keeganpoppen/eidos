// Actual local UI/API acceptance using context_input_reuse_demo.py. Never dispatch.
// Set NEMA_CONTEXT_REUSE_MARKER, NEMA_UI_ORIGIN, NEMA_UI_DEBUG and
// NEMA_UI_EVIDENCE_PREFIX; optional NEMA_CONTEXT_REUSE_MODE=baseline|reopened|appearance.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import { browserAcceptance } from './browser_acceptance_support.mjs';

const markerPath=process.env.NEMA_CONTEXT_REUSE_MARKER;
assert(markerPath,'Set NEMA_CONTEXT_REUSE_MARKER to the authored fixture marker.');
const marker=JSON.parse(await fs.readFile(markerPath,'utf8'));
assert.equal(marker.schemaVersion,'synthetic-context-input-reuse/v1');
assert.equal(marker.classification,'authored-host-history');
assert.equal(marker.nativeOrModelCalls,0);
const origin=process.env.NEMA_UI_ORIGIN??'http://127.0.0.1:5173';
const debug=process.env.NEMA_UI_DEBUG??'http://127.0.0.1:9233';
const prefix=process.env.NEMA_UI_EVIDENCE_PREFIX??'/tmp/nema-context-input-reuse-browser';
const mode=process.env.NEMA_CONTEXT_REUSE_MODE??'flow';
assert(['baseline','flow','reopened','appearance'].includes(mode),'Unknown context reuse acceptance mode.');
for(const address of [origin,debug]) {
 const url=new URL(address);assert(url.protocol==='http:'&&['localhost','127.0.0.1','[::1]'].includes(url.hostname));
}
const b=await browserAcceptance({origin,debug});
const draftKey='nema.investigation-draft.v1', stagedKey='nema.context-input-draft.v1';
const form="document.querySelector('.context-input-draft')";
const checks=[],screenshots=[],measurements=[];let observations={};
const posts=()=>b.requests.filter(r=>r.method==='POST');
const raw=key=>b.evaluate(`localStorage.getItem(${JSON.stringify(key)})`);
const draft=()=>raw(draftKey);
const staged=()=>b.local(stagedKey);
const hasButton=text=>`[...${form}?.querySelectorAll('button')??[]].some(e=>e.textContent.trim()===${JSON.stringify(text)})`;
const buttonDisabled=text=>`[...${form}.querySelectorAll('button')].find(e=>e.textContent.trim()===${JSON.stringify(text)})?.disabled===true`;
async function shot(name,selector='.context-input-draft') {
 await b.evaluate(`document.querySelector(${JSON.stringify(selector)}).scrollIntoView({block:'start'})`);
 const file=`${prefix}-${mode}-${name}.png`;await b.screenshot(file);screenshots.push(file);
 const size=await b.evaluate(`({width:innerWidth,document:document.documentElement.scrollWidth,panes:[...document.querySelectorAll('.context-input-draft')].map(e=>e.scrollWidth-e.clientWidth)})`);
 assert(size.document<=size.width+1,JSON.stringify(size));assert(size.panes.every(x=>x<=1),JSON.stringify(size));measurements.push({name,...size});
}
async function readOwner(id) {
 return b.evaluate(`fetch('/api/investigations/'+${JSON.stringify(id)}).then(r=>{if(!r.ok)throw Error('Owner read failed');return r.json()})`);
}
function checkCreated(work,contextId) {
 const context=work.contexts.find(c=>c.id===contextId);assert(context);
 assert.deepEqual(context.selections,marker.historicalContext.selections);
 assert.deepEqual(context.records,marker.historicalContext.records);
 assert.deepEqual(context.artifactInputs,marker.historicalContext.artifactInputs);
 assert.equal(context.question,marker.newQuestion);
 assert.equal(context.parentContextId,null);
 assert.deepEqual(context.inputOrigin,{version:1,kind:'historical-context-inputs',investigationId:marker.owner,
  contextId:marker.historicalContextId,manifestId:marker.historicalContext.manifestId});
 assert(context.projectedPrompt.includes(marker.newQuestion));assert(!context.projectedPrompt.includes(marker.oldQuestion));
 assert(!context.projectedPrompt.includes('NEW_SOURCE_REVIEW'));assert(!context.projectedPrompt.includes('NEW_SOURCE_RESULT'));
 assert(context.projectedPrompt.includes('OLD_FROZEN_REVIEW'));
 assert.equal(context.inquiryLineage,undefined);assert.equal(work.attempt,null);assert.equal(work.artifact,null);assert.equal(work.adoption,null);
 assert.notEqual(context.id,marker.historicalContextId);
 return context;
}
async function seedEditor() {
 await b.select('#saved-investigation',marker.owner);
 await b.wait(`document.querySelector('.context-preview')?.textContent.includes(${JSON.stringify(marker.currentContextId)})`);await b.settle();
 await b.fill('#investigation-question','Independent unsaved question: preserve my working draft.');
 await b.fill('[aria-label="Why include source 1"]','Independent unsaved inclusion rationale.');
 await b.select('#context-revision',marker.historicalContextId);
 await b.wait(`JSON.parse(localStorage.getItem(${JSON.stringify(draftKey)}))?.previewId===${JSON.stringify(marker.historicalContextId)}`);
 const pending={id:'authored-context-reuse-original-save',body:'{"id":"authored-original-save","question":"Do not replace this recovery identity"}'};
 await b.evaluate(`(()=>{const value=JSON.parse(localStorage.getItem(${JSON.stringify(draftKey)}));value.pendingRequest=${JSON.stringify(pending)};localStorage.setItem(${JSON.stringify(draftKey)},JSON.stringify(value));})()`);
 await b.reload();await b.settle();
 const value=await draft();assert.deepEqual(JSON.parse(value).pendingRequest,pending);return value;
}
try {
 await b.fresh('historical-input-reuse-'+mode);await b.settle();
 assert.equal(b.requests.find(r=>r.path==='/api/investigations/capabilities')?.response.nativeExecution.available,false);
 if(mode==='reopened'||mode==='appearance') {
  const prior=JSON.parse(await fs.readFile(`${prefix}-flow.json`,'utf8'));
  await b.evaluate(`localStorage.setItem(${JSON.stringify(draftKey)},${JSON.stringify(prior.observations.originalDraft)});localStorage.setItem(${JSON.stringify(stagedKey)},${JSON.stringify(JSON.stringify(prior.observations.savedStage))})`);
  await b.reload();await b.settle();
  assert.equal(await draft(),prior.observations.originalDraft);assert.deepEqual(await staged(),prior.observations.savedStage);
  assert(await b.evaluate(buttonDisabled('Open saved draft')));
  const target=prior.observations.savedStage.saved;const work=await readOwner(target.investigationId);checkCreated(work,target.contextId);
  assert.deepEqual(await readOwner(marker.owner),marker.originalOwner);assert.deepEqual(await readOwner(marker.sourceOwner),marker.originalSource);
  assert.equal(posts().length,0);await shot('same-saved-draft');
  checks.push('after actual API restart, restored staged/result and editor recovery snapshots resolve exact frozen result without POST or dispatch');
  observations={restoration:'Explicit authored restoration of the previously captured local browser entries into an isolated browser context.',savedStage:await staged(),savedInvestigation:work};
  if(mode==='appearance') {
   await b.clickText('Inspect saved input',form);
   await b.wait(`document.querySelector('[data-inspected-context]')?.dataset.inspectedContext===${JSON.stringify(target.contextId)}`);
   await b.evaluate("document.querySelector('.created-input-preview details').open=true");
   await shot('exact-saved-packet','.created-input-preview');
   await b.page.rpc('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:false});
   await shot('mobile-exact-saved-packet','.created-input-preview');
   // Restore an explicitly authored unsent stage only in this isolated visual
   // inspection context. It sends nothing and does not replace a real retry.
   const unsent={...prior.observations.savedStage,request:null,saved:null,refusal:null};
   await b.evaluate(`localStorage.setItem(${JSON.stringify(stagedKey)},${JSON.stringify(JSON.stringify(unsent))})`);
   await b.reload();await b.settle();await shot('mobile-unsent-controls','#context-input-question');
   await b.page.rpc('Emulation.setDeviceMetricsOverride',{width:1600,height:1100,deviceScaleFactor:1,mobile:false});
   await shot('desktop-unsent-controls');
   assert.equal(posts().length,0);assert.equal(await draft(),prior.observations.originalDraft);
   checks.push('post-style visual inspection restores only authored snapshots in an isolated context; exact packet and form controls stay readable with zero writes');
  }
 } else {
  const originalDraft=await seedEditor();
  assert.deepEqual(JSON.parse(originalDraft).selections,marker.originalOwner.contexts.at(-1).selections.map((s,i)=>({...s,rationale:i===0?'Independent unsaved inclusion rationale.':s.rationale})));
  assert.equal(JSON.parse(originalDraft).previewId,marker.historicalContextId);
  if(mode==='baseline') {
   assert.equal(await b.evaluate("!!document.querySelector('#context-input-start')"),false);
   await shot('historical-preview','.context-preview');assert.equal(await draft(),originalDraft);assert.equal(posts().length,0);
   observations={originalDraft};checks.push('baseline historical preview shows C0 while editable inputs remain C1; no historical-input reuse action exists');
  } else {
   await b.click('#context-input-start');await b.wait(`${form}&&document.querySelector('#context-input-question')`);
   assert.equal(await b.evaluate("document.querySelector('#context-input-question').value"),'');
   assert.equal(await draft(),originalDraft);assert.equal(posts().length,0);
   await b.fill('#context-input-title','New question from the retained historical inputs');
   await b.fill('#context-input-question',marker.newQuestion);
   assert.equal((await staged()).source.contextId,marker.historicalContextId);
   await shot('staged-exact-inputs');
   await b.page.rpc('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:false});
   await shot('mobile-staged');
   b.page.losePost='/api/investigations';await b.clickText('Save new draft',form);
   await b.wait(hasButton('Retry creating this draft'));await b.settle();
   assert.equal(b.page.lost.length,1);assert.equal(b.page.lost[0].committedStatus,201);assert.equal(posts().length,1);
   const pendingStage=await staged();assert(pendingStage.request);assert.equal(pendingStage.saved,null);
   const request=JSON.parse(pendingStage.request);
   assert.deepEqual(request.inputSource,{investigationId:marker.owner,contextId:marker.historicalContextId});
   assert.equal(request.question,marker.newQuestion);assert.equal(request.selections,undefined);assert.equal(request.artifactInputs,undefined);
   assert(await b.evaluate("document.querySelector('#context-input-question').disabled"));assert.equal(await draft(),originalDraft);
   await shot('lost-committed-reply');await b.reload();await b.settle();
   assert.equal(posts().length,1);assert.deepEqual(await staged(),pendingStage);assert.equal(await draft(),originalDraft);
   await b.clickText('Retry creating this draft',form);await b.wait(`(${form}?.textContent??'').includes('Open saved draft')`);await b.settle();
   const savedStage=await staged();assert(savedStage.saved);assert.equal(posts().length,2);
   assert.equal(posts()[0].body,posts()[1].body);assert.equal(posts()[1].status,201);
   const saved=posts()[1].response,context=checkCreated(saved,savedStage.saved.contextId);
   assert.equal(saved.id,savedStage.saved.investigationId);assert.equal(await draft(),originalDraft);
   assert(await b.evaluate(buttonDisabled('Open saved draft')));
   await b.clickText('Inspect saved input',form);
   await b.wait(`document.querySelector('[data-inspected-context]')?.dataset.inspectedContext===${JSON.stringify(context.id)}`);
   await b.evaluate("document.querySelector('.created-input-preview details').open=true");
   assert.equal(await b.evaluate("document.querySelector('.created-input-preview pre').textContent"),context.projectedPrompt);
   assert.equal(await draft(),originalDraft);assert.equal(posts().length,2);
   await shot('saved-with-editor-pending');
   await b.reload();await b.settle();assert.equal(posts().length,2);assert.equal(await draft(),originalDraft);assert.deepEqual(await staged(),savedStage);
   assert.deepEqual(await readOwner(marker.owner),marker.originalOwner);assert.deepEqual(await readOwner(marker.sourceOwner),marker.originalSource);
   checks.push('new blank question uses C0 snapshots and old source review; lost committed response retries identical body once, creating one draft while preserving original dirty/pending editor bytes');
   checks.push('reloading saved creation sends nothing; original pending save blocks Open and historical source/current owners remain unchanged');

   // Independent browser context tests deliberate replacement, retaining the first
   // context's pending editor untouched rather than clearing it to enable Open.
   await b.page.rpc('Page.setWebLifecycleState',{state:'frozen'});
   await b.fresh('explicit-open-created-context');await b.settle();
   await b.select('#saved-investigation',marker.owner);await b.wait("!!document.querySelector('.context-preview')");await b.settle();
   await b.fill('#investigation-question','Separate unsaved draft for the replacement choice.');
   await b.wait(`JSON.parse(localStorage.getItem(${JSON.stringify(draftKey)}))?.question==='Separate unsaved draft for the replacement choice.'`);
   await b.evaluate(`localStorage.setItem(${JSON.stringify(stagedKey)},${JSON.stringify(JSON.stringify(savedStage))})`);
   await b.reload();await b.settle();const beforeOpen=await draft();
   await b.clickText('Open saved draft',form);await b.wait(hasButton('Keep editing current draft'));
   await b.clickText('Keep editing current draft',form);assert.equal(await draft(),beforeOpen);
   b.page.holdPath=`/api/investigations/${saved.id}/view`;
   await b.clickText('Open saved draft',form);await b.wait(hasButton('Replace unsaved draft and open'));await b.clickText('Replace unsaved draft and open',form);
   for(let n=0;n<100&&!b.page.held;n++)await new Promise(resolve=>setTimeout(resolve,50));
   assert(b.page.held,'Expected to hold the saved-owner Open response.');
   await b.clickText('Compare');await b.wait("document.querySelector('.shell').classList.contains('comparison-mode')");
   const held=b.page.held;b.page.held=null;await b.page.rpc('Fetch.continueRequest',{requestId:held});await b.settle();
   assert.equal(await draft(),beforeOpen);
   await b.clickText('Investigation');await b.settle();assert.equal(await draft(),beforeOpen);
   checks.push('late Open response after switching to Compare cannot replace the hidden or returning working draft');
   await b.clickText('Open saved draft',form);await b.wait(hasButton('Replace unsaved draft and open'));await b.clickText('Replace unsaved draft and open',form);
   await b.wait(`document.querySelector('#saved-investigation')?.value===${JSON.stringify(saved.id)}`);
   await b.wait(`document.querySelector('#context-revision')?.value===${JSON.stringify(context.id)}`);await b.settle();
   assert.equal(posts().length,2);assert.equal(await b.evaluate("document.querySelector('#investigation-question').value"),marker.newQuestion);
   await shot('opened-exact-created-context','.context-preview');
   await b.page.rpc('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:false});await shot('mobile-opened-origin','.context-preview');
   checks.push('opening over a different dirty editor requires an explicit replacement choice; Keep leaves it untouched and confirmed Open selects the exact created context without dispatch');
   observations={originalDraft,pendingStage,savedStage,savedInvestigation:saved,createdContext:context,originalContext:marker.historicalContext};
  }
 }
 assert.deepEqual(b.exceptions,[]);assert(!b.requests.some(r=>/\/(dispatch|adoption|cancel)$/.test(r.path)));
 await b.settle();
 const result={classification:'real-local-api-authored-history',nativeOrModelCalls:0,mode,marker,checks,observations,screenshots,measurements,apiRequests:b.requests,exceptions:b.exceptions};
 await fs.writeFile(`${prefix}-${mode}.json`,JSON.stringify(result,null,2)+'\n');
 console.log(JSON.stringify({mode,checks,apiRequests:b.requests.length,postRequests:posts().length,screenshots,measurements}));
} catch(error) {
 await b.settle().catch(()=>{});
 await fs.writeFile(`${prefix}-${mode}-failure.json`,JSON.stringify({mode,marker,checks,observations,screenshots,measurements,apiRequests:b.requests,exceptions:b.exceptions,failure:{message:error.message,stack:error.stack}},null,2)+'\n');throw error;
} finally {await b.close();}
