// Authored local empty-workbench/import acceptance; no native or model calls.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {browserAcceptance} from './browser_acceptance_support.mjs';
const origin=process.env.NEMA_UI_ORIGIN??'http://127.0.0.1:5173';
const debug=process.env.NEMA_UI_DEBUG??'http://127.0.0.1:9233';
const prefix=process.env.NEMA_UI_EVIDENCE_PREFIX??'/tmp/nema-history-import-browser-20261013';
const mode=process.env.NEMA_HISTORY_IMPORT_MODE??'baseline';
for(const address of [origin,debug]) {const u=new URL(address);assert(u.protocol==='http:'&&['127.0.0.1','localhost','[::1]'].includes(u.hostname));}
assert(['baseline','flow','recovery','reopened'].includes(mode));
const marker=mode==='baseline'?null:JSON.parse(await fs.readFile(process.env.NEMA_HISTORY_IMPORT_MARKER,'utf8'));
if(marker)assert.equal(marker.schemaVersion,'synthetic-history-import/v1');
const draftKey='nema.investigation-draft.v1',importKey='nema.history-import.v1';
const b=await browserAcceptance({origin,debug});
const report={classification:'authored-empty-workbench',mode,nativeOrModelCalls:0,checks:[],observations:{},screenshots:[]};
try {
 await b.fresh('history-import-'+mode);await b.settle();
 if(mode==='baseline') {
 assert.deepEqual(b.requests.find(r=>r.path==='/api/threads')?.response.threads,[]);
 assert.equal(b.requests.find(r=>r.path==='/api/investigations/capabilities')?.response.nativeExecution.available,false);
 assert.equal(await b.evaluate("document.querySelector('.new-thread button').disabled"),true);
 assert.equal(await b.evaluate("document.querySelectorAll('input[type=file]').length"),0);
 assert.equal(await b.evaluate("!!document.querySelector('.history-import')"),false);
 assert.equal(await b.evaluate("document.querySelector('.thread-header').textContent.includes('import existing Codex history')"),true);
 await b.fill('#investigation-title','Unfinished question before bringing history');
 await b.fill('#investigation-question','Which evidence supports the decision?');await b.settle();
 report.observations.draft=await b.evaluate("localStorage.getItem('nema.investigation-draft.v1')");
 report.observations.buttons=await b.evaluate("[...document.querySelectorAll('button')].map(e=>({text:e.textContent.trim(),disabled:e.disabled})).filter(e=>e.text)");
 for(const [name,width,height] of [['desktop',1600,1100],['mobile',390,844]]) {
  await b.page.rpc('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false});
  const path=prefix+'-baseline-'+name+'.png';await b.screenshot(path);report.screenshots.push(path);
 }
 assert.deepEqual(b.exceptions,[]);assert.equal(b.requests.filter(r=>r.method==='POST').length,0);
 report.checks.push('Fresh empty workbench suggests import but has no file input or import component; native new-thread is disabled.',
 'Authored unfinished question remains editable; baseline performs only reads.');
 } else if(mode==='flow') {await flow();}
 else if(mode==='recovery') {await recovery();}
 else {await reopened();}
 assert.deepEqual(b.exceptions,[]);
 const allowed=new Set(['/api/history/imports/preview','/api/history/imports','/api/investigations']);
 assert(b.requests.filter(r=>r.method==='POST').every(r=>allowed.has(r.path)));
 report.apiRequests=b.requests;report.exceptions=b.exceptions;
 await fs.writeFile(prefix+'-'+mode+'.json',JSON.stringify(report,null,2)+'\n');
 console.log(JSON.stringify({checks:report.checks,requests:b.requests.length,posts:b.requests.filter(r=>r.method==='POST').length},null,2));
} catch(error) {
 await b.settle().catch(()=>{});await b.screenshot(prefix+'-'+mode+'-failure.png').catch(()=>{});
 await fs.writeFile(prefix+'-'+mode+'-failure.json',JSON.stringify({...report,error:String(error),apiRequests:b.requests,exceptions:b.exceptions},null,2)+'\n');throw error;
} finally {await b.close();}


async function storage(key) {return b.evaluate(`localStorage.getItem(${JSON.stringify(key)})`);}
async function openImport() {
 if(!await b.evaluate("document.querySelector('.history-import')?.closest('dialog')?.open===true"))await b.clickText('Import history',"document.querySelector('.thread-rail')");
 await b.wait("document.querySelector('.history-import')?.closest('dialog')?.open===true");
}
async function upload(name) {
 const {root}=await b.page.rpc('DOM.getDocument');
 const {nodeId}=await b.page.rpc('DOM.querySelector',{nodeId:root.nodeId,selector:'#history-import-file'});
 assert(nodeId);await b.page.rpc('DOM.setFileInputFiles',{nodeId,files:[marker.files[name].path]});
}
async function preview(name) {
 await upload(name);const before=b.requests.length;
 await b.clickText('Preview import',"document.querySelector('.history-import')");await b.settle();
 const request=b.requests.slice(before).find(r=>r.path==='/api/history/imports/preview');
 assert(request);return request;
}
async function shot(name,selector='.history-import') {
 if(selector)await b.evaluate(`document.querySelector(${JSON.stringify(selector)}).scrollIntoView({block:'start'})`);
 const path=prefix+'-'+mode+'-'+name+'.png';await b.screenshot(path);report.screenshots.push(path);
 const dimensions=await b.evaluate(`({width:innerWidth,document:document.documentElement.scrollWidth,component:${selector?`document.querySelector(${JSON.stringify(selector)}).scrollWidth-document.querySelector(${JSON.stringify(selector)}).clientWidth`:'0'}})`);
 assert(dimensions.document<=dimensions.width+1,JSON.stringify(dimensions));assert(dimensions.component<=1,JSON.stringify(dimensions));
 (report.measurements??=[]).push({name,...dimensions});
}
async function restore(draft,pending) {
 await b.evaluate(`localStorage.setItem(${JSON.stringify(draftKey)},${JSON.stringify(draft)});localStorage.setItem(${JSON.stringify(importKey)},${JSON.stringify(pending)});`);
 await b.reload();await b.settle();
}
async function flow() {
 assert.deepEqual(b.requests.find(r=>r.path==='/api/threads')?.response.threads,[]);
 await b.fill('#investigation-title','Independent unfinished question while importing');
 await b.fill('#investigation-question','Preserve this question and its unresolved save.');await b.settle();
 const pending={id:'authored-independent-import-editor-save',body:'{"id":null,"title":"Unfinished question","question":"Preserve my unresolved save","selections":[]}'};
 await b.evaluate(`(()=>{const value=JSON.parse(localStorage.getItem(${JSON.stringify(draftKey)}));value.pendingRequest=${JSON.stringify(pending)};localStorage.setItem(${JSON.stringify(draftKey)},JSON.stringify(value));})()`);
 await b.reload();await b.settle();const originalDraft=await storage(draftKey);
 await openImport();await b.fill('#history-import-source',marker.source);
 await b.select('#history-import-direction',marker.direction);
 b.page.phase='refused-previews';
 const malformed=await preview('malformed');assert.equal(malformed.status,400);assert(malformed.response.error);
 assert.equal(await b.evaluate("!!document.querySelector('[data-import-preview]')"),false);
 const unsupported=await preview('unsupported');assert.equal(unsupported.status,200);
 assert.equal(unsupported.response.preview.committable,false);assert.equal(unsupported.response.preview.summary.discoverableFieldCount,0);
 assert.equal(await b.evaluate("[...document.querySelector('.history-import').querySelectorAll('button')].find(e=>e.textContent.trim()==='Import reviewed file')?.disabled??true"),true);
 assert.equal(await storage(draftKey),originalDraft);
 const empty=await b.evaluate("fetch('/api/threads').then(r=>r.json())");assert.deepEqual(empty.threads,[]);
 await shot('unsupported-preview');
 b.page.phase='stale-preview';
 await upload('valid');b.page.holdPath='/api/history/imports/preview';
 await b.clickText('Preview import',"document.querySelector('.history-import')");
 for(let n=0;n<100&&!b.page.held;n++)await new Promise(r=>setTimeout(r,50));assert(b.page.held);
 await upload('different');await b.page.rpc('Fetch.continueRequest',{requestId:b.page.held});b.page.held=null;await b.settle();
 assert.equal(await b.evaluate("!!document.querySelector('[data-import-preview]')"),false);
 b.page.phase='review-and-lost-commit';
 const checked=await preview('valid');assert.equal(checked.status,200);
 const inspected=checked.response.preview;assert.equal(inspected.fileSha256,marker.files.valid.sha256);
 assert.equal(inspected.byteLength,marker.files.valid.byteLength);assert.equal(inspected.recordCount,marker.recordCount);assert.equal(inspected.summary.threadCount,2);assert.equal(inspected.committable,true);
 await shot('reviewed-file');
 b.page.losePost='/api/history/imports';
 await b.clickText('Import reviewed file',"document.querySelector('.history-import')");await b.settle();
 assert.equal(b.page.lost.length,1);assert.equal(b.page.lost[0].committedStatus,201);
 const pendingImport=await storage(importKey);assert(pendingImport);assert(pendingImport.length<4096);assert(!pendingImport.includes('contentBase64'));
 assert.equal(await storage(draftKey),originalDraft);assert.equal(await b.evaluate("!!document.querySelector('[data-import-receipt]')"),false);
 const importPosts=()=>b.requests.filter(r=>r.method==='POST'&&r.path==='/api/history/imports');
 assert.equal(importPosts().length,1);const body=JSON.parse(importPosts()[0].body);assert.equal(body.previewFingerprint,inspected.previewFingerprint);
 assert.equal(Buffer.from(body.contentBase64,'base64').toString('hex'),(await fs.readFile(marker.files.valid.path)).toString('hex'));
 await b.reload();await b.settle();assert.equal(importPosts().length,1);assert.equal(await storage(importKey),pendingImport);assert.equal(await storage(draftKey),originalDraft);
 await openImport();await shot('pending-after-reload');
 report.observations={originalDraft,pendingImport,preview:inspected,commitBody:body};
 report.checks.push('Malformed tail and unsupported-only file cannot import; preview leaves empty target unchanged.',
 'A late preview cannot attach to a different selected file; exact original bytes reviewed and sent.',
 'Successful import reply deliberately lost; metadata-only recovery survives reload with no automatic POST and independent pending editor unchanged.');
}
async function recoverReceipt(prior) {
 await openImport();const before=b.requests.length;
 await b.clickText('Check import receipt',"document.querySelector('.history-import')");await b.settle();
 const read=b.requests.slice(before).find(r=>r.path.startsWith('/api/history/imports/requests/'));assert.equal(read?.status,200);
 const receipt=read.response.receipt;assert.equal(receipt.requestId,prior.observations.commitBody.requestId);
 assert.equal(receipt.fileSha256,marker.files.valid.sha256);assert.equal(receipt.recordCount,marker.recordCount);
 await b.wait(`document.querySelector('[data-import-receipt]')?.dataset.importReceipt===${JSON.stringify(receipt.id)}`);
 return receipt;
}
async function recovery() {
 const prior=JSON.parse(await fs.readFile(prefix+'-flow.json','utf8'));
 await restore(prior.observations.originalDraft,prior.observations.pendingImport);
 b.page.phase='receipt-after-api-restart';const receipt=await recoverReceipt(prior);
 assert.equal(await storage(draftKey),prior.observations.originalDraft);assert.equal(b.requests.filter(r=>r.method==='POST').length,0);
 await shot('recovered-receipt');
 await b.page.rpc('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:false});await shot('mobile-receipt');
 await b.page.rpc('Emulation.setDeviceMetricsOverride',{width:1600,height:1100,deviceScaleFactor:1,mobile:false});
 // A separate explicitly restored snapshot exercises deliberate same-request retry.
 await b.fresh('history-import-exact-retry');await b.settle();await restore(prior.observations.originalDraft,prior.observations.pendingImport);await openImport();
 b.page.phase='wrong-file-then-exact-retry';await upload('different');
 await b.wait("!!document.querySelector('.history-import [role=alert]') || document.querySelector('.history-import').textContent.includes('match')");
 assert.equal(await b.evaluate("[...document.querySelector('.history-import').querySelectorAll('button')].find(e=>e.textContent.trim()==='Retry this import')?.disabled??true"),true);
 assert.equal(b.requests.filter(r=>r.method==='POST').length,0);
 await upload('valid');await b.clickText('Retry this import',"document.querySelector('.history-import')");await b.settle();
 const replay=b.requests.filter(r=>r.method==='POST'&&r.path==='/api/history/imports').at(-1);assert.equal(replay?.status,200);assert.deepEqual(replay.response.receipt,receipt);
 assert.deepEqual(JSON.parse(replay.body),prior.observations.commitBody);assert.equal(await storage(draftKey),prior.observations.originalDraft);
 report.observations.receipt=receipt;
 // A separate fresh question preserves the independent pending editor exactly.
 await b.fresh('history-import-canonical-question');await b.settle();
 b.page.phase='discover-and-save';
 await b.fill('#investigation-title','What makes an import recoverable?');
 await b.fill('#investigation-question','Which decision and counterexample explain preserving an exact receipt without duplicate history?');
 const inspected=[];
 for(const q of [marker.queries.decision,marker.queries.counterexample,marker.queries.split]) {
  const detail=await discover(q);inspected.push(...detail.records);
  await b.clickText('Add these source records',"document.querySelector('.evidence-discovery')");await b.settle();
 }
 const repeat=await discover(marker.queries.repeated);assert.equal(repeat.records.length,2);assert.equal(repeat.records[0].rawText,repeat.records[1].rawText);
 const expected=[...new Map(inspected.map(r=>[r.seq,r])).values()].sort((a,b)=>a.seq-b.seq);assert.equal(expected.length,4);assert.equal(new Set(expected.map(r=>r.threadId)).size,2);
 await b.clickText('Save and preview context');await b.wait("!!document.querySelector('.context-preview')");await b.settle();
 const created=b.requests.find(r=>r.path==='/api/investigations'&&r.method==='POST');assert(created?.response);
 const work=created.response,context=work.contexts.find(c=>c.id===work.currentContextId);assert(context);assert.deepEqual(context.records,expected);
 assert.equal(work.attempt,null);assert.equal(work.artifact,null);assert.equal(work.adoption,null);
 await b.evaluate("document.querySelector('.context-preview .exact-input').open=true");await shot('canonical-context','.context-preview');
 const savedDraft=await storage(draftKey);await b.reload();await b.settle();assert.equal(await storage(draftKey),savedDraft);
 report.observations.savedDraft=savedDraft;report.observations.savedInvestigation=work;report.observations.savedContext=context;
 report.checks.push('After actual API restart, explicit receipt GET recovers exact commit with zero POSTs and untouched pending editor.',
 'Independent restored pending import rejects a different file, then explicit exact retry returns200 and the same immutable receipt.',
 'Imported repeated identical lines remain distinct; discovery freezes four exact inspected records across two threads into a canonical question, with no native attempt.');
}
async function discover(q) {
 const before=b.requests.length;await b.fill('#evidence-search-query',q);await b.clickText('Search history',"document.querySelector('.evidence-discovery')");await b.settle();
 const result=b.requests.slice(before).find(r=>r.path==='/api/evidence/search'&&r.response?.hits);assert.equal(result?.status,200);assert.equal(result.response.hits.length,1);
 const hit=result.response.hits[0];const offset=b.requests.length;
 await b.clickText('Inspect source',`document.querySelector('[data-evidence-hit-id="${hit.id}"]')`);await b.settle();
 await b.wait(`document.querySelector('[data-inspected-evidence-hit]')?.dataset.inspectedEvidenceHit===${JSON.stringify(hit.id)}`);
 const detail=b.requests.slice(offset).find(r=>r.path==='/api/evidence/hits/'+hit.id)?.response;assert(detail);assert.deepEqual(detail.hit,hit);assert.deepEqual(detail.records.map(r=>r.seq),hit.recordSeqs);return detail;
}
async function reopened() {
 const first=JSON.parse(await fs.readFile(prefix+'-flow.json','utf8'));
 const prior=JSON.parse(await fs.readFile(prefix+'-recovery.json','utf8'));
 await restore(prior.observations.savedDraft,first.observations.pendingImport);
 b.page.phase='second-api-restart';
 await b.wait(`document.querySelector('.context-preview')?.textContent.includes(${JSON.stringify(prior.observations.savedContext.id)})`);
 const work=await b.evaluate(`fetch('/api/investigations/'+${JSON.stringify(prior.observations.savedInvestigation.id)}).then(r=>r.json())`);assert.deepEqual(work,prior.observations.savedInvestigation);
 const receipt=await recoverReceipt(first);assert.deepEqual(receipt,prior.observations.receipt);assert.equal(await storage(draftKey),prior.observations.savedDraft);
 assert.equal(b.requests.filter(r=>r.method==='POST').length,0);await shot('same-receipt');
 await b.clickText('Close import',"document.querySelector('.history-import')");await shot('same-canonical-context','.context-preview');
 report.checks.push('Second actual API restart recovers the same canonical question and immutable import receipt through reads only.');
}
