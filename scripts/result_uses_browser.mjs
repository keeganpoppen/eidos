// Actual local UI/API acceptance over authored public excerpts. No native calls.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {browserAcceptance} from './browser_acceptance_support.mjs';
const origin=process.env.NEMA_UI_ORIGIN??'http://127.0.0.1:5173';
const debug=process.env.NEMA_UI_DEBUG??'http://127.0.0.1:9233';
const prefix=process.env.NEMA_UI_EVIDENCE_PREFIX??'/tmp/nema-result-uses-browser-20261013';
const mode=process.env.NEMA_RESULT_USES_MODE??'baseline';
const marker=JSON.parse(await fs.readFile(process.env.NEMA_RESULT_USES_MARKER,'utf8'));
assert.equal(marker.schemaVersion,'authored-public-repository-result-uses/v1');
assert.equal(marker.nativeOrModelCalls,0);
assert(['baseline','flow','reopened','source-deleted'].includes(mode));
assert.equal(marker.sourceDeleted,mode==='source-deleted','Wait for fixture preparation to finish before starting this browser mode.');
for(const address of [origin,debug]){const u=new URL(address);assert(u.protocol==='http:'&&['127.0.0.1','localhost','[::1]'].includes(u.hostname));}
const b=await browserAcceptance({origin,debug});
const report={classification:marker.classification,mode,nativeOrModelCalls:0,checks:[],observations:{},screenshots:[]};
const draftKey='nema.investigation-draft.v1',findingKey='nema.authored-finding.v1';
const dialog="document.querySelector('.artifact-lineage[open]')";
const source=marker.source;
const usesPath=`/api/investigations/${source.investigationId}/artifacts/${source.artifactId}/uses`;
const storage=key=>b.evaluate(`localStorage.getItem(${JSON.stringify(key)})`);
async function shot(name,selector='.artifact-lineage[open]'){
 await b.evaluate(`document.querySelector(${JSON.stringify(selector)}).scrollIntoView({block:'start'})`);
 const path=prefix+'-'+mode+'-'+name+'.png';await b.screenshot(path);report.screenshots.push(path);
 const size=await b.evaluate(`({width:innerWidth,document:document.documentElement.scrollWidth,component:document.querySelector(${JSON.stringify(selector)}).scrollWidth-document.querySelector(${JSON.stringify(selector)}).clientWidth})`);
 assert(size.document<=size.width+1,JSON.stringify(size));assert(size.component<=1,JSON.stringify(size));
 (report.measurements??=[]).push({name,...size});
}
async function seedEditor(){
 const ownerId=marker.sourceDeleted?marker.e:source.investigationId;
 await b.select('#saved-investigation',ownerId);
 const editorContext=marker.originalOwners.find(w=>w.id===ownerId).currentContextId;
 await b.wait(`document.querySelector('.context-preview')?.textContent.includes(${JSON.stringify(editorContext)})`);
 await b.fill('#investigation-question','Independent unfinished merge question; preserve this pending save.');
 await b.fill('[aria-label="Why include source 1"]','Independent unsaved source rationale.');await b.settle();
 const pending={id:'result-uses-independent-editor-save',body:'{"id":"result-uses-independent-save","question":"Preserve unresolved save identity"}'};
 const finding={version:1,source:{investigationId:source.investigationId,contextId:source.contextId,title:marker.originalOwners.find(w=>w.id===source.investigationId).title,question:marker.originalContext.question},
  text:null,request:JSON.stringify({requestId:'result-uses-independent-finding-save',contextId:source.contextId,text:'Independent unfinished hypothesis.'}),savedId:null};
 await b.evaluate(`(()=>{const value=JSON.parse(localStorage.getItem(${JSON.stringify(draftKey)}));value.pendingRequest=${JSON.stringify(pending)};localStorage.setItem(${JSON.stringify(draftKey)},JSON.stringify(value));localStorage.setItem(${JSON.stringify(findingKey)},${JSON.stringify(JSON.stringify(finding))});})()`);
 await b.reload();await b.settle();
 return {draft:await storage(draftKey),finding:await storage(findingKey),sourceFocus:await storage('nema.source-focus.v1')};
}
async function unchanged(saved){
 assert.equal(await storage(draftKey),saved.draft);assert.equal(await storage(findingKey),saved.finding);
 assert.equal(await storage('nema.source-focus.v1'),saved.sourceFocus);
 assert.equal(b.requests.filter(r=>r.method!=='GET').length,0);
}
async function openOriginal(artifactId=source.artifactId){
 await b.clickText('Inspect finding provenance',`document.querySelector('[data-result-artifact-id="${artifactId}"]')`);
 await b.wait(`${dialog}?.querySelector('[data-lineage-context-id]')?.dataset.lineageContextId===${JSON.stringify(source.contextId)}`);await b.settle();
}
const rows=".artifact-lineage[open] [data-result-use-owner][data-result-use-context]";
const preview=".artifact-lineage[open] [data-result-use-preview]";
const row=(owner,context)=>`${rows}[data-result-use-owner="${owner}"][data-result-use-context="${context}"]`;
const detailPath=(owner,context)=>`${usesPath}/${owner}/contexts/${context}`;
async function settleReads(){
 if(b.page.held){await Promise.all(b.page.reads);await new Promise(r=>setTimeout(r,150));}
 else await b.settle();
}
async function waitHeld(){
 for(let n=0;n<100&&!b.page.held;n++)await new Promise(r=>setTimeout(r,50));assert(b.page.held);
}
async function openUses(expected=2){
 await b.clickText('Questions supplied this result',dialog);
 await b.wait(`document.querySelectorAll(${JSON.stringify(rows)}).length===${expected}`);await settleReads();
}
async function checkUses(){
 const actual=await b.evaluate(`[...document.querySelectorAll(${JSON.stringify(rows)})].map(e=>({investigationId:e.dataset.resultUseOwner,contextId:e.dataset.resultUseContext,text:e.textContent}))`);
 assert.deepEqual(actual.map(v=>[v.investigationId,v.contextId]).sort(),marker.expectedUses.map(v=>[v.investigationId,v.contextId]).sort());
 for(const expected of marker.expectedUses)assert(actual.find(v=>v.investigationId===expected.investigationId).text.includes(expected.isCurrent?'Current saved context':'Historical saved context'));
 const responses=b.requests.filter(r=>r.path===usesPath&&r.status===200&&r.response?.uses);
 assert(responses.length);const value=responses.at(-1);
 assert.equal(value.response.scope,'direct-frozen-artifact-inputs/v1');
 assert.deepEqual(value.response.source,{investigationId:source.investigationId,artifactId:source.artifactId});
 assert.equal(value.response.uses.length,2);assert(value.bodyBytes<=128*1024);
 report.observations.usesResponse=value.response;report.observations.usesResponseBytes=value.bodyBytes;
}
async function inspect(owner,context){
 await b.clickText('Inspect saved context',`document.querySelector(${JSON.stringify(row(owner,context.id))})`);
 await b.wait(`document.querySelector(${JSON.stringify(preview)})?.dataset.consumerContext===${JSON.stringify(context.id)}`);await settleReads();
 await b.wait(`document.activeElement?.closest('[data-result-use-preview]')?.dataset.consumerContext===${JSON.stringify(context.id)}`);
 const visible=await b.evaluate(`(()=>{const r=document.activeElement.getBoundingClientRect();return {top:r.top,bottom:r.bottom,height:innerHeight}})()`);
 assert(visible.top>=0&&visible.bottom<=visible.height,JSON.stringify(visible));
 assert.equal(await b.evaluate(`document.querySelector(${JSON.stringify(preview)}).dataset.consumerOwner`),owner);
 const text=await b.evaluate(`document.querySelector(${JSON.stringify(preview)}).textContent`);
 assert(text.includes(context.question));assert(text.includes(context.artifactInputs[0].rationale));
 assert(text.includes(marker.f0.text.split('\n\n')[0]));
 const response=b.requests.filter(r=>r.path===detailPath(owner,context.id)&&r.status===200).at(-1)?.response;
 assert(response);assert.deepEqual(response.context,context);assert.deepEqual(response.matchingInputIndexes,[0]);
 assert.deepEqual(response.context.artifactInputs[0].artifact,marker.f0);
 assert(!text.includes(marker.f1.text));return response;
}
async function deletedEntry(){
 // B's saved finding still references F0; inspect the frozen upstream input from there.
 // The independent editor remains E, so use the result catalog's read-only inspector.
 await b.fill('#context-artifact-picker-search',marker.bf.text.slice(0,40));
 await b.clickText('Search',"document.querySelector('#context-artifact-picker').closest('.catalog-picker')");
 await b.select('#context-artifact-picker',JSON.stringify([marker.b,marker.bf.id]));
 await b.clickText('Inspect selected result');
 await b.wait(`${dialog}?.querySelector('[data-lineage-context-id]')?.dataset.lineageContextId===${JSON.stringify(marker.b0.id)}`);
 await b.click(`.artifact-lineage[open] .lineage-input[data-artifact-id="${source.artifactId}"]`);
 await b.wait(`${dialog}?.querySelector('[data-lineage-artifact-id]')?.dataset.lineageArtifactId===${JSON.stringify(source.artifactId)}`);await b.settle();
 assert(b.requests.some(r=>r.path===usesPath.replace(/\/uses$/,'/source')&&r.status===404));
 assert(await b.evaluate(`${dialog}.textContent.includes('investigation not found')`));
}
async function flow(){
 const saved=await seedEditor();
 if(marker.sourceDeleted)await deletedEntry();else await openOriginal();
 await openUses();await checkUses();await unchanged(saved);await shot('direct-uses','.artifact-lineage[open] .result-uses');
 await inspect(marker.b,marker.b0);await shot('historical-context',preview);await unchanged(saved);
 await b.page.rpc('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:false});await shot('mobile-historical-context',preview);
 await b.page.rpc('Emulation.setDeviceMetricsOverride',{width:1600,height:1100,deviceScaleFactor:1,mobile:false});
 const copied=await inspect(marker.d,marker.d0);assert.deepEqual(copied.context.inputOrigin,marker.d0.inputOrigin);
 await shot('copied-context',preview);await unchanged(saved);
 await closeOriginal();
 if(mode==='flow'){
  // Hold an actual completed detail response, close its subject, then release it.
  await openOriginal();await openUses();b.page.holdPath=detailPath(marker.b,marker.b0.id);
  await b.clickText('Inspect saved context',`document.querySelector(${JSON.stringify(row(marker.b,marker.b0.id))})`);
  await waitHeld();
  await closeOriginal();await openOriginal(marker.f1.id);
  try{
   await b.page.rpc('Fetch.continueRequest',{requestId:b.page.held});
   report.observations.closedDetailDelivery='released after close';
  }catch(error){
   // AbortController may retire Chromium's interception before the harness releases it.
   // This observes cancellation, not delivery of a stale response to the component.
   assert(String(error).includes('Invalid InterceptionId.'),String(error));
   report.observations.closedDetailDelivery='browser aborted before release';
  }
  b.page.held=null;await b.settle();
  assert.equal(await b.evaluate(`document.querySelector(${JSON.stringify(preview)})!==null`),false);
 await openUses(0);
  assert(await b.evaluate(`${dialog}.textContent.includes('No saved contexts directly supplied this exact result.')`));
  assert.equal(await b.evaluate(`${dialog}.querySelector('[data-lineage-artifact-id]').dataset.lineageArtifactId`),marker.f1.id);
  await shot('new-finding-no-inferred-uses','.artifact-lineage[open] .result-uses');await unchanged(saved);await closeOriginal();
  // A failed list read is displayed as failure; explicit refresh recovers the real uses.
  await openOriginal();b.page.failPath=usesPath;await b.clickText('Questions supplied this result',dialog);await b.settle();
  assert(await b.evaluate(`${dialog}.querySelector('.result-uses').textContent.includes('Synthetic one-shot read failure')`));
  assert.equal(await b.evaluate(`document.querySelectorAll(${JSON.stringify(rows)}).length`),0);
  await b.clickText('Refresh saved uses',dialog);await b.wait(`document.querySelectorAll(${JSON.stringify(rows)}).length===2`);await b.settle();
  await checkUses();await closeOriginal();await unchanged(saved);
  // Original source loading must not displace a consumer inspected in the meantime.
  b.page.holdPath=usesPath.replace(/\/uses$/,'/source');
  await b.clickText('Inspect finding provenance',`document.querySelector('[data-result-artifact-id="${source.artifactId}"]')`);
  await waitHeld();await openUses();await inspect(marker.b,marker.b0);
  const scrollBefore=await b.evaluate(`${dialog}.scrollTop`);
  await b.page.rpc('Fetch.continueRequest',{requestId:b.page.held});b.page.held=null;await b.settle();
  assert.equal(await b.evaluate("document.activeElement?.closest('[data-result-use-preview]')?.dataset.consumerContext"),marker.b0.id);
  assert(Math.abs(await b.evaluate(`${dialog}.scrollTop`)-scrollBefore)<=1);
  await shot('late-source-keeps-inspection',preview);await closeOriginal();await unchanged(saved);
 }
 report.observations.saved=saved;
 report.checks.push('Direct saved uses are exactly historical B0 and current copied-input D; B1, transitive C, raw-sharing E and prose-only F are excluded.',
  'Inline inspection returns the exact historical/copy context and frozen F0 with its original inclusion rationale.',
  'Independent dirty/pending editor and finding-recovery storage remain byte-identical; all browser API actions are GETs.');
 if(mode==='flow')report.checks.push('Closing held B0 detail and navigating to F1 cannot reopen or misplace the preview; F1 receives no inferred uses. The report distinguishes browser abort from delivery.',
  'Synthetic list-read failure remains an error; explicit refresh recovers the relation.');
 if(mode==='flow')report.checks.push('Original source reply held until after B0 inspection cannot reset the explicit preview focus or scroll.');
 if(marker.sourceDeleted)report.checks.push('After explicit fixture source/raw deletion and API restart, original-source read is404 while B0/D membership and exact frozen snapshots remain inspectable.');
}
async function closeOriginal(){
 await b.clickText('Close result provenance',dialog);
 await b.wait("document.querySelectorAll('.artifact-lineage[open]').length===0");
}
async function baseline(){
 const saved=await seedEditor();await openOriginal();
 assert.equal(await b.evaluate(`${dialog}.textContent.includes('Questions supplied this result')`),false);
 const all=await b.evaluate("fetch('/api/investigations').then(r=>r.text())");
 const owners=JSON.parse(all).investigations;
 const uses=owners.flatMap(w=>w.contexts.filter(c=>c.artifactInputs?.some(i=>i.investigationId===source.investigationId&&i.artifactId===source.artifactId)).map(c=>({investigationId:w.id,contextId:c.id,isCurrent:c.id===w.currentContextId})));
 const sorted=v=>v.sort((a,z)=>a.investigationId.localeCompare(z.investigationId));
 assert.deepEqual(sorted(uses),sorted(structuredClone(marker.expectedUses)));
 const search=await b.evaluate(`fetch('/api/investigations/artifacts?q='+encodeURIComponent(${JSON.stringify(source.artifactId)})).then(r=>r.json())`);
 assert(search.artifacts.some(a=>a.investigationId===marker.f));assert(!search.artifacts.some(a=>a.investigationId===marker.d));
 await shot('original-provenance');
 await b.page.rpc('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:false});await shot('mobile-provenance');
 await closeOriginal();await unchanged(saved);
 report.observations={saved,uses,wholeOwnerResponseBytes:Buffer.byteLength(all),search};
 report.checks.push('Existing provenance shows original inputs but has no direct-use view.',
  'Manual full-owner scan finds historical B0 and copied-input D; result text search misses D and returns prose-only F.',
  'Read-only baseline preserves independent pending editor/finding storage.');
}
try{
 await b.fresh('result-uses-'+mode);await b.settle();
 if(mode==='baseline')await baseline();
 else await flow();
 await b.settle();assert.equal(b.exceptions.length,0,JSON.stringify(b.exceptions));
 report.requests=b.requests;report.runtimeExceptions=b.exceptions;
 await fs.writeFile(prefix+'-'+mode+'.json',JSON.stringify(report,null,2)+'\n');
 console.log(JSON.stringify({mode,checks:report.checks,requests:b.requests.length,posts:b.requests.filter(r=>r.method==='POST').length,report:prefix+'-'+mode+'.json'}));
}catch(error){
 report.error=String(error);report.requests=b.requests;report.runtimeExceptions=b.exceptions;
 await fs.writeFile(prefix+'-'+mode+'-failure.json',JSON.stringify(report,null,2)+'\n');
 await b.screenshot(prefix+'-'+mode+'-failure.png').catch(()=>{});throw error;
}finally{await b.close();}
