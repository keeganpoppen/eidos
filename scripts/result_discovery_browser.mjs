// Real API/browser acceptance for scripts/result_discovery_demo.py. Seed/serve its
// authored database, point Vite at that API and start isolated Chromium CDP.
// NEMA_RESULT_DISCOVERY_MARKER=/tmp/result-demo.json NEMA_UI_ORIGIN=http://127.0.0.1:5181 \
// NEMA_UI_DEBUG=http://127.0.0.1:9231 NEMA_UI_EVIDENCE_PREFIX=/tmp/result-ui \
// bun scripts/result_discovery_browser.mjs
// This reads historical fixtures and saves one draft. It never dispatches work.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import { browserAcceptance } from './browser_acceptance_support.mjs';

const markerPath=process.env.NEMA_RESULT_DISCOVERY_MARKER;
assert(markerPath,'Set NEMA_RESULT_DISCOVERY_MARKER to the authored fixture marker.');
const marker=JSON.parse(await fs.readFile(markerPath,'utf8'));
assert.equal(marker.schemaVersion,'synthetic-result-discovery/v1');
assert.equal(marker.classification,'authored-host-history');
assert.equal(marker.nativeOrModelCalls,0);
const origin=process.env.NEMA_UI_ORIGIN??'http://127.0.0.1:5181';
const debug=process.env.NEMA_UI_DEBUG??'http://127.0.0.1:9231';
const prefix=process.env.NEMA_UI_EVIDENCE_PREFIX??'/tmp/nema-result-discovery-browser';
for(const address of [origin,debug]) {
 const url=new URL(address);
 assert(url.protocol==='http:'&&['localhost','127.0.0.1','[::1]'].includes(url.hostname));
}
const b=await browserAcceptance({origin,debug});
const checks=[],screenshots=[],measurements=[],injections=[],navigationRetirements=[];
function trackDocumentReads() {
 const client=b.page,previous=client.event,reads=new Map();
 client.event=event=>{
   const p=event.params;
   if(event.method==='Page.frameNavigated'&&!p.frame.parentId) {
     for(const [id,read] of reads) {
       if(read.loader&&read.loader!==p.frame.loaderId&&read.entry.method==='GET'&&client.inflight.has(id)) {
         navigationRetirements.push({context:client.name,path:read.entry.path,query:read.entry.query,
           status:read.entry.status??null,reason:'Prior-document GET had no terminal network event before main-frame navigation; its body is not acceptance evidence.'});
         client.inflight.delete(id);reads.delete(id);
       }
     }
   }
   previous(event);
   if(event.method==='Network.requestWillBeSent'&&new URL(p.request.url).pathname.startsWith('/api/')) {
     reads.set(p.requestId,{loader:p.loaderId,entry:b.requests.at(-1)});
   }
   if(['Network.loadingFinished','Network.loadingFailed'].includes(event.method))reads.delete(p.requestId);
 };
}
const picker="document.querySelector('#context-artifact-picker').closest('.catalog-picker')";
const dialog="document.querySelector('.artifact-lineage[open]')";
const key=(owner,artifact)=>JSON.stringify([owner,artifact]);
const targetKey=key(marker.owner,marker.artifactId);
const sourcePath=`/api/investigations/${marker.owner}/artifacts/${marker.artifactId}/source`;
const draft=()=>b.local('nema.investigation-draft.v1');
const posts=()=>b.requests.filter(request=>request.method==='POST');
const latestCatalog=query=>b.requests.findLast(request=>request.path==='/api/investigations/artifacts'&&new URLSearchParams(request.query).get('q')===query&&request.response?.artifacts)?.response.artifacts;
async function search(query,wait=true) {
 await b.fill('#context-artifact-picker-search',query);
 await b.clickText('Search',picker);
 if(wait){await b.wait("document.querySelector('#context-artifact-picker').getAttribute('aria-busy')==='false'");await b.settle();}
}
async function selectedTarget() { await b.select('#context-artifact-picker',targetKey); }
async function inspectTarget() {
 await b.clickText('Inspect selected result');
 await b.wait(`${dialog}?.querySelector('.original-question')?.textContent.includes(${JSON.stringify(marker.question)})`);
 await b.settle();
 assert.equal(await b.evaluate(`${dialog}.querySelector('[data-lineage-artifact-id]').dataset.lineageArtifactId`),marker.artifactId);
 assert.equal(await b.evaluate(`${dialog}.querySelector('[data-lineage-context-id]').dataset.lineageContextId`),marker.contextId);
 assert((await b.evaluate(`${dialog}.textContent`)).includes(marker.text));
 const request=b.requests.findLast(request=>request.path===sourcePath&&request.response?.artifact);
 assert.equal(new URLSearchParams(request.query).get('contextId'),marker.contextId);
 assert.equal(request.response.attempt.id,marker.attemptId);
 assert.equal(request.response.context.id,marker.contextId);
}
async function closeDialog(){await b.clickText('Close result provenance',dialog);await b.wait(`!${dialog}`);}
async function heldResponse(){for(let n=0;n<100&&!b.page.held;n++)await new Promise(resolve=>setTimeout(resolve,50));assert(b.page.held,'Response interception did not occur.');}
async function releaseResponse(){const requestId=b.page.held;b.page.held=null;await b.page.rpc('Fetch.continueRequest',{requestId});await b.settle();}
async function shot(name,selector='.artifact-picker') {
 await b.evaluate(`document.querySelector(${JSON.stringify(selector)}).scrollIntoView({block:'start'})`);
 const file=`${prefix}-${name}.png`;await b.screenshot(file);screenshots.push(file);
 const sizes=await b.evaluate(`({width:innerWidth,document:document.documentElement.scrollWidth,dialogs:[...document.querySelectorAll('.artifact-lineage[open]')].map(e=>e.scrollWidth-e.clientWidth),pickers:[...document.querySelectorAll('.catalog-picker')].map(e=>e.scrollWidth-e.clientWidth)})`);
 assert(sizes.document<=sizes.width+1,JSON.stringify(sizes));assert(sizes.dialogs.every(n=>n<=1));assert(sizes.pickers.every(n=>n<=1));measurements.push({name,...sizes});
}
let observations={};
try {
 await b.fresh('dirty-owner-discovery');await b.settle();trackDocumentReads();
 assert.equal(b.requests.find(request=>request.path==='/api/investigations/capabilities')?.response.nativeExecution.available,false);
 await b.select('#saved-investigation',marker.owner);
 await b.wait(`document.querySelector('.investigation-state')?.textContent.includes(${JSON.stringify(marker.owner)})`);await b.settle();
 await b.fill('#investigation-question','Authored unsent question: retain this independent working draft.');
 await b.fill('[aria-label="Why include source 1"]','Authored unsent rationale.');
 await b.wait("JSON.parse(localStorage.getItem('nema.investigation-draft.v1')).question.startsWith('Authored unsent')");
 const pendingSave={id:'authored-discovery-pending-save',body:'{"id":"authored-unsent-save","question":"Preserve original retry"}'};
 await b.evaluate(`(()=>{const value=JSON.parse(localStorage.getItem('nema.investigation-draft.v1'));value.pendingRequest=${JSON.stringify(pendingSave)};localStorage.setItem('nema.investigation-draft.v1',JSON.stringify(value));})()`);
 const before=await draft();await b.reload();await b.settle();assert.deepEqual(await draft(),before);

 await search(marker.questionQuery);
 const questionHits=latestCatalog(marker.questionQuery);
 assert.deepEqual(questionHits.map(item=>item.artifactId).sort(),[marker.artifactId,marker.decoyArtifactId].sort());
 assert.equal(questionHits.find(item=>item.artifactId===marker.artifactId).match.field,'question');
 assert.equal(questionHits.find(item=>item.artifactId===marker.decoyArtifactId).match.field,'title');
 assert(!questionHits.some(item=>item.artifactId===marker.currentArtifactId));
 await selectedTarget();
 assert.equal(await b.evaluate(`${picker}.querySelector('.catalog-match').dataset.matchField`),'question');
 await shot('question-hit');await inspectTarget();
 await b.evaluate(`${dialog}.querySelector('.lineage-record').open=true`);
 await b.wait(`${dialog}?.textContent.includes(${JSON.stringify(marker.support)})`);
 await b.evaluate(`${dialog}.querySelector('.raw-evidence').open=true`);
 await b.wait(`${dialog}?.querySelector('.raw-evidence pre')?.textContent.includes(${JSON.stringify(marker.excludedCanary)})`);
 assert((await b.evaluate(`${dialog}.textContent`)).includes(marker.excludedCanary),'Excluded search fields remain inspectable as original evidence.');
 await shot('original-question-support','.artifact-lineage[open]');await closeDialog();
 assert.deepEqual(await draft(),before);assert.equal(posts().length,0);
 checks.push('question phrase finds old A1/C0 beside title-only decoy; pre-Add inspection shows its original question and support without changing dirty draft or pending save');

 await search(marker.excludedCanary);assert.deepEqual(latestCatalog(marker.excludedCanary),[]);
 await b.wait(`${picker}.querySelector('.catalog-retained')?.textContent.includes('Retained selection')`);
 assert.equal(await b.evaluate(`!!${picker}.querySelector('.catalog-match')`),false);
 assert.equal(await b.evaluate("document.querySelector('#context-artifact-picker').value"),targetKey);
 await inspectTarget();await closeDialog();assert.deepEqual(await draft(),before);
 checks.push('raw-only field does not produce search hits; retained selection stays exact and its old excerpt is not represented as a new-query match');

 b.page.holdPath='/api/investigations/artifacts';
 await search(marker.questionQuery,false);await heldResponse();
 await search(marker.resultQuery,false);
 await b.wait(`${picker}.querySelector('.catalog-match')?.dataset.matchField==='result'`);
 await releaseResponse();
 assert.deepEqual(latestCatalog(marker.resultQuery).map(item=>item.artifactId),[marker.artifactId]);
 assert.equal(await b.evaluate(`${picker}.querySelector('.catalog-match').dataset.matchField`),'result');
 assert.equal(await b.evaluate(`[...document.querySelector('#context-artifact-picker').options].some(e=>e.value===${JSON.stringify(key(marker.decoyOwner,marker.decoyArtifactId))})`),false);
 checks.push('late response from the earlier question search cannot replace the newer result-only page');

 b.page.holdPath=sourcePath;await b.clickText('Inspect selected result');await heldResponse();await closeDialog();
 await search(marker.questionQuery,false);
 await b.wait("document.querySelector('#context-artifact-picker').getAttribute('aria-busy')==='false'");
 await b.select('#context-artifact-picker',key(marker.decoyOwner,marker.decoyArtifactId));
 await b.clickText('Inspect selected result');
 await b.wait(`${dialog}?.querySelector('[data-lineage-artifact-id]')?.dataset.lineageArtifactId===${JSON.stringify(marker.decoyArtifactId)} && !!${dialog}?.querySelector('.original-question')`);
 await releaseResponse();
 assert.equal(await b.evaluate(`${dialog}.querySelector('[data-lineage-artifact-id]').dataset.lineageArtifactId`),marker.decoyArtifactId);
 assert(!(await b.evaluate(`${dialog}.querySelector('.original-question').textContent`)).includes(marker.question));
 await closeDialog();assert.deepEqual(await draft(),before);
 checks.push('late source detail cannot replace the subsequently selected decoy; exact source pins remain separate');

 await search(marker.resultQuery);await selectedTarget();
 const previousEvent=b.page.event;let missing=true;
 b.page.event=event=>{
   const p=event.params;
   if(missing&&event.method==='Fetch.requestPaused'&&!p.responseStatusCode&&new URL(p.request.url).pathname===sourcePath){
     missing=false;injections.push({kind:'authored-one-shot-missing-source',path:sourcePath,status:404});
     void b.page.rpc('Fetch.fulfillRequest',{requestId:p.requestId,responseCode:404,responseHeaders:[{name:'Content-Type',value:'application/json'}],body:Buffer.from('{"error":"Authored exact source is unavailable"}').toString('base64')});
   }else previousEvent(event);
 };
 await b.clickText('Inspect selected result');await b.wait(`${dialog}?.querySelector('.work-error')?.textContent.includes('exact source is unavailable')`);
 assert.equal(await b.evaluate(`!!${dialog}.querySelector('.original-question')`),false);
 assert.equal(await b.evaluate(`!!${dialog}.querySelector('.artifact-content')`),false);
 assert((await b.evaluate(`${dialog}.textContent`)).includes(marker.contextId));
 await closeDialog();b.page.event=previousEvent;assert.deepEqual(await draft(),before);
 await b.page.rpc('Fetch.disable'); // All intentional failure/delay challenges are finished.
 await b.reload();await b.settle();assert.deepEqual(await draft(),before);assert.equal(posts().length,0);
 checks.push('authored missing-source response keeps exact references without a newer result; reload preserves the original working draft and retry identity');

 await b.page.rpc('Page.setWebLifecycleState',{state:'frozen'});
 await b.fresh('explicit-result-reuse');await b.settle();trackDocumentReads();
 await b.page.rpc('Fetch.disable'); // Observe ordinary save/reload without interception.
 await b.fill('#investigation-title','Browser · exact historical result reuse');
 await b.fill('#investigation-question','Which retained result explains the stopped attempt claim?');
 const emptyDraft=await draft();
 await search(marker.resultQuery);await selectedTarget();
 await inspectTarget();await closeDialog();assert.deepEqual(await draft(),emptyDraft);
 await b.page.rpc('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:false});
 await shot('mobile-match');await inspectTarget();await shot('mobile-original-question','.artifact-lineage[open]');await closeDialog();
 assert.equal(posts().length,0);
 await b.clickText('Add selected result to context');
 await b.wait(`document.querySelector('[data-selected-artifact-id=${JSON.stringify(marker.artifactId)}]')`);
 assert.deepEqual((await draft()).artifactInputs,[{investigationId:marker.owner,artifactId:marker.artifactId,rationale:''}]);
 assert.equal(posts().length,0);
 await b.clickText('Save and preview context');
 await b.wait(`!!document.querySelector('[data-frozen-artifact-id=${JSON.stringify(marker.artifactId)}]')`);await b.settle();
 assert.equal(posts().length,1);assert.equal(posts()[0].path,'/api/investigations');assert.equal(posts()[0].status,201);
 const saved=posts()[0].response,context=saved.contexts.find(item=>item.id===saved.currentContextId),input=context.artifactInputs[0];
 assert.equal(context.artifactInputs.length,1);assert.equal(context.records.length,0);
 assert.equal(input.artifactId,marker.artifactId);assert.equal(input.sourceContextId,marker.contextId);
 assert.equal(input.artifact.attemptId,marker.attemptId);assert.equal(input.artifact.text,marker.text);
 assert.equal(saved.attempt,null);assert.notEqual(input.artifactId,marker.currentArtifactId);
 await b.reload();await b.wait(`!!document.querySelector('[data-frozen-artifact-id=${JSON.stringify(marker.artifactId)}]')`);await b.settle();
 assert.equal(await b.evaluate("document.querySelector('#saved-investigation').value"),saved.id);
 assert.equal(posts().length,1);await shot('mobile-frozen-input','.frozen-artifact-input');
 checks.push('only explicit Add changes inputs; ordinary Save freezes old A1/C0 without underlying raw source or A2, and reload retains the saved packet');

 assert.deepEqual(b.exceptions,[]);
 for(const request of b.requests.filter(item=>item.path==='/api/investigations/artifacts'&&item.response?.artifacts)) {
   assert(!JSON.stringify(request.response).includes(marker.excludedCanary));
   const q=new URLSearchParams(request.query).get('q')?.trim();
   for(const hit of request.response.artifacts) {
     if(q){assert(['title','question','result'].includes(hit.match.field));assert([...hit.match.excerpt].length<=240);}
     else assert.equal(hit.match,undefined);
   }
 }
 assert(!b.requests.some(request=>request.path.endsWith('/dispatch')));
 observations={dirtyDraftBefore:before,pendingSave,savedInvestigation:saved,questionHits,resultHits:latestCatalog(marker.resultQuery),injections,navigationRetirements};
 const result={classification:'real-local-api-authored-history',nativeOrModelCalls:0,marker,checks,observations,screenshots,measurements,apiRequests:b.requests,exceptions:b.exceptions};
 await fs.writeFile(`${prefix}.json`,JSON.stringify(result,null,2)+'\n');
 console.log(JSON.stringify({checks,apiRequests:b.requests.length,postRequests:posts().length,screenshots,measurements}));
} catch(error) {
 await b.settle().catch(()=>{});
 await fs.writeFile(`${prefix}-failure.json`,JSON.stringify({marker,checks,observations,injections,navigationRetirements,screenshots,measurements,apiRequests:b.requests,exceptions:b.exceptions,failure:{message:error.message,stack:error.stack}},null,2)+'\n');
 throw error;
} finally {await b.close();}
