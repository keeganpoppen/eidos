// Actual local UI/API acceptance using pinned public source and captured local checks.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {browserAcceptance} from './browser_acceptance_support.mjs';
const origin=process.env.NEMA_UI_ORIGIN??'http://127.0.0.1:5173';
const debug=process.env.NEMA_UI_DEBUG??'http://127.0.0.1:9233';
const prefix=process.env.NEMA_UI_EVIDENCE_PREFIX??'/tmp/nema-supplied-text-browser-20261014';
const mode=process.env.NEMA_SUPPLIED_TEXT_MODE??'baseline';
const marker=JSON.parse(await fs.readFile(process.env.NEMA_SUPPLIED_TEXT_MARKER,'utf8'));
assert.equal(marker.schemaVersion,'public-code-supplied-text-episode/v1');
assert.equal(marker.nativeOrModelCalls,0);
if(mode==='source-deleted')assert.equal(marker.sourceDeleted,true,'Prepare marked source-loss fixture before this mode');
for(const address of [origin,debug]){const u=new URL(address);assert(u.protocol==='http:'&&['127.0.0.1','localhost','[::1]'].includes(u.hostname));}
const b=await browserAcceptance({origin,debug});
const report={classification:marker.classification,mode,nativeOrModelCalls:0,checks:[],observations:{},screenshots:[]};
const posts=()=>b.requests.filter(r=>r.method==='POST');
const storage=key=>b.evaluate(`localStorage.getItem(${JSON.stringify(key)})`);
const dialog="document.querySelector('.supplied-text-evidence')";
const guards=['nema.investigation-draft.v1','nema.authored-finding.v1','nema.history-import.v1','nema.source-focus.v1'];
const external=[];
async function fresh(name){
 await b.fresh(name);await b.settle();
 const prior=b.page.event;b.page.event=message=>{
  if(message.method==='Network.requestWillBeSent'){
   const url=new URL(message.params.request.url);
   if(['http:','https:'].includes(url.protocol)&&!['127.0.0.1','localhost','[::1]'].includes(url.hostname))external.push(url.href);
  }prior(message);
 };
}
async function snapshot(){const pairs=await Promise.all(guards.map(async key=>[key,await storage(key)]));return Object.fromEntries(pairs);}
async function guard(expected){assert.deepEqual(await snapshot(),expected);}
async function open(){await b.click('[data-open-supplied-text="rail"]');await b.wait("!!document.querySelector('.supplied-text-evidence')?.closest('dialog').open");}
async function choose(entry){await file('#supplied-text-file',entry.path);}
async function seedIndependent(){
 await b.fill('#investigation-title','Independent unfinished review');
 await b.fill('#investigation-question','Preserve this pending question while files are admitted.');await b.settle();
 await b.evaluate(`(()=>{
  const key='nema.investigation-draft.v1',draft=JSON.parse(localStorage.getItem(key));
  draft.pendingRequest={id:'independent-text-editor-save',body:JSON.stringify({requestId:'independent-text-editor-save',question:'Preserve this exact request'})};localStorage.setItem(key,JSON.stringify(draft));
  localStorage.setItem('nema.authored-finding.v1',JSON.stringify({version:1,source:{investigationId:'investigation_independent',contextId:'context_independent',title:'Independent finding',question:'Retain my unanswered review'},text:null,request:JSON.stringify({requestId:'independent-finding-save',contextId:'context_independent',text:'Do not replace this pending finding.'}),savedId:null}));
  localStorage.setItem('nema.history-import.v1',JSON.stringify({requestId:'independent-history-import',format:'appserver-jsonl/v1',source:'authored-independent',direction:'appserver_to_client',fileName:'independent.jsonl',fileSha256:'1'.repeat(64),byteLength:17,previewFingerprint:'2'.repeat(64),operationFingerprint:'3'.repeat(64)}));
 })()`);
 await b.reload();await b.settle();return snapshot();
}
async function confirmFile(entry){
 await choose(entry);await b.clickText('Preview text evidence',dialog);await b.settle();
 const p=posts().filter(r=>r.path==='/api/evidence/files/preview').at(-1);assert.equal(p?.status,200);
 assert.equal(p.response.preview.fileSha256,entry.fileSha256);
 await b.clickText('Add reviewed text',dialog);await b.settle();
 const admission=posts().filter(r=>r.path==='/api/evidence/files').at(-1);assert.equal(admission?.status,201);
 const receipt=admission.response.receipt;assert.equal(receipt.fileSha256,entry.fileSha256);assert.equal(receipt.byteLength,entry.byteLength);
 await b.wait(`document.querySelector('[data-supplied-text-receipt]')?.dataset.suppliedTextReceipt===${JSON.stringify(receipt.id)}`);
 return receipt;
}
const ownerRead=id=>b.evaluate(`fetch('/api/investigations/'+${JSON.stringify(id)}).then(r=>{if(!r.ok)throw Error('Owner read failed');return r.json()})`);
async function file(selector,path){
 const {root}=await b.page.rpc('DOM.getDocument');
 const {nodeId}=await b.page.rpc('DOM.querySelector',{nodeId:root.nodeId,selector});
 assert(nodeId,selector);await b.page.rpc('DOM.setFileInputFiles',{nodeId,files:[path]});
}
async function shot(name,selector){
 if(selector)await b.evaluate(`document.querySelector(${JSON.stringify(selector)}).scrollIntoView({block:'start'})`);
 const path=prefix+'-'+mode+'-'+name+'.png';await b.screenshot(path);report.screenshots.push(path);
 const size=await b.evaluate(`({width:innerWidth,document:document.documentElement.scrollWidth,component:${selector?`document.querySelector(${JSON.stringify(selector)}).scrollWidth-document.querySelector(${JSON.stringify(selector)}).clientWidth`:'0'}})`);
 assert(size.document<=size.width+1,JSON.stringify(size));assert(size.component<=1,JSON.stringify(size));
 (report.measurements??=[]).push({name,...size});
}
async function baseline(){
 await b.fill('#investigation-title','Independent unfinished review');
 await b.fill('#investigation-question','Preserve this local question while I inspect file intake.');await b.settle();
 const draft=await storage('nema.investigation-draft.v1');assert(draft);
 assert.equal(await b.evaluate("!!document.querySelector('[data-open-supplied-text]')"),false);
 await b.clickText('Import history',"document.querySelector('.thread-rail')");
 await file('#history-import-file',marker.files.find(f=>f.fileName==='observed-checks.txt').path);
 await b.wait("document.querySelector('.chosen-file')?.textContent.includes('observed-checks.txt')");
 await b.clickText('Preview import',"document.querySelector('.history-import')");await b.settle();
 const preview=posts().find(r=>r.path==='/api/history/imports/preview');
 assert.equal(preview?.status,400);assert.match(preview.response.error,/invalid or unrepresentable JSON object/);
 await shot('text-is-not-history','.history-import');
 await b.page.rpc('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:false});
 await shot('narrow-refusal','.history-import');
 assert.equal(await storage('nema.investigation-draft.v1'),draft);
 const missing=await b.evaluate("fetch('/api/evidence/files/requests/baseline-missing').then(async r=>({status:r.status,body:await r.json()}))");
 assert.equal(missing.status,404);assert.equal(posts().length,1);
 report.observations={draft,preview:preview.response,missing};
 report.checks.push('Actual captured text cannot enter the current JSONL history preview; no text-admission action/route exists.',
 'Refused preview preserves independent question draft; zero admission/native POSTs.');
}
async function flow(){
 // Establish a real explicit source focus before challenging preservation on
 // admission/reload; an empty first-run workbench has no existing source pin.
 await open();const focusReceipt=await confirmFile(marker.files.find(f=>f.fileName==='before-import-method.py'));
 await b.clickText('Open supplied text',dialog);await b.settle();
 const independent=await seedIndependent();await open();
 if(!await b.evaluate("!!document.querySelector('[data-supplied-text-receipt]')")){await b.clickText('Check text receipt',dialog);await b.settle();}
 if(await b.evaluate("!!document.querySelector('[data-supplied-text-receipt]')"))await b.clickText('Add another text file',dialog);
 const entry=marker.files.find(f=>f.fileName==='observed-checks.txt');
 await choose(entry);await b.clickText('Preview text evidence',dialog);await b.settle();
 const preview=posts().filter(r=>r.path==='/api/evidence/files/preview').at(-1);assert.equal(preview?.status,200);
 assert.equal(preview.response.preview.fileSha256,entry.fileSha256);await guard(independent);
 await shot('actual-check-preview','.supplied-text-evidence');
 b.page.phase='lost-admission-reply';b.page.losePost='/api/evidence/files';
 await b.clickText('Add reviewed text',dialog);await b.settle();
 assert.equal(b.page.lost.length,1);assert.equal(b.page.lost[0].committedStatus,201);
 const pending=await storage('nema.supplied-text.v1');assert(pending);assert(Buffer.byteLength(pending)<=4096);
 assert.equal(pending.includes('Public-code malformed-tail'),false);
 const body=JSON.parse(b.page.lost[0].body);assert.equal(body.fileName,entry.fileName);
 const count=posts().length;await b.reload();await b.settle();
 assert.equal(posts().length,count);assert.equal(await storage('nema.supplied-text.v1'),pending);await guard(independent);
 await open();await shot('pending-after-reload','.supplied-text-evidence');
 await b.page.rpc('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:false});
 await shot('narrow-pending','.supplied-text-evidence');
 report.observations={pending,independent,body,focusReceipt};
 report.checks.push('Actual local-check stdout previews as supplied text; admission reply is lost after201.',
 'Metadata-only recovery survives reload without automatic POST; independent pending editor/finding/history-import and source focus remain byte-exact.');
}
async function restore(prior){
 await b.evaluate(`(()=>{const guards=${JSON.stringify(prior.independent)};for(const [key,value]of Object.entries(guards)){if(value===null)localStorage.removeItem(key);else localStorage.setItem(key,value);}localStorage.setItem('nema.supplied-text.v1',${JSON.stringify(prior.pending)});})()`);
 await b.reload();await b.settle();
}
async function recovery(){
 const prior=JSON.parse(await fs.readFile(prefix+'-flow.json','utf8')).observations;
 await restore(prior);await open();assert.equal(posts().length,0);
 b.page.phase='receipt-after-api-restart';await b.clickText('Check text receipt',dialog);await b.settle();
 const request=b.requests.find(r=>r.path==='/api/evidence/files/requests/'+prior.body.requestId);assert.equal(request?.status,200);
 const original=request.response.receipt;assert.equal(original.fileSha256,marker.files.find(f=>f.fileName==='observed-checks.txt').fileSha256);
 await guard(prior.independent);assert.equal(posts().length,0);await shot('receipt-after-restart','.supplied-text-evidence');
 await fresh('supplied-text-exact-retry');await restore(prior);await open();
 await choose(marker.files.find(f=>f.fileName==='literal-content.txt'));await b.settle();
 await b.wait("document.querySelector('.supplied-text-evidence [role=alert]')?.textContent.length>0");
 assert.equal(await storage('nema.supplied-text.v1'),prior.pending);assert.equal(posts().length,0);
 await choose(marker.files.find(f=>f.fileName==='observed-checks.txt'));
 b.page.phase='exact-retry';await b.clickText('Retry adding this file',dialog);await b.settle();
 const replay=posts().find(r=>r.phase==='exact-retry');assert.equal(replay?.status,200);
 assert.deepEqual(JSON.parse(replay.body),prior.body);assert.deepEqual(replay.response.receipt,original);await guard(prior.independent);
 await b.clickText('Open supplied text',dialog);await b.settle();
 await b.wait(`!!document.querySelector('[data-supplied-text-id="${original.id}"]')`);
 assert.equal(await b.evaluate("!!document.querySelector('.composer textarea')"),false);
 await shot('local-source-history','[data-supplied-text-id]');
 const receipts=[prior.focusReceipt,original];
 await fresh('supplied-text-other-files');
 for(const entry of marker.files.filter(f=>!receipts.some(r=>r.fileName===f.fileName))){
  await open();
  if(await b.evaluate("!!document.querySelector('[data-supplied-text-receipt]')"))await b.clickText('Add another text file',dialog);
  const receipt=await confirmFile(entry);receipts.push(receipt);
  const originalBytes=await b.evaluate(`fetch('/api/evidence/files/'+${JSON.stringify(receipt.id)}).then(async r=>({status:r.status,body:await r.json()}))`);
  assert.equal(originalBytes.status,200);assert.deepEqual(originalBytes.body.receipt,receipt);
  assert.deepEqual(Buffer.from(originalBytes.body.contentBase64,'base64'),await fs.readFile(entry.path));
  await b.clickText('Open supplied text',dialog);await b.settle();
  await b.wait(`!!document.querySelector('[data-supplied-text-id="${receipt.id}"]')`);
  if(entry.fileName==='literal-content.txt'){
   await shot('literal-nonfetching-source',`[data-supplied-text-id="${receipt.id}"]`);
   assert.equal(await b.evaluate(`document.querySelector('[data-supplied-text-id="${receipt.id}"]').querySelectorAll('img,iframe,script,a').length`),0);
   await b.page.rpc('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:false});
   await shot('narrow-literal-source',`[data-supplied-text-id="${receipt.id}"]`);
  }
 }
 assert.deepEqual(external,[]);report.observations={receipts};
 report.checks.push('After actual API restart receipt GET recovers exact admission; wrong-file reselection refuses and exact retry returns200 with the same receipt.',
 'Five explicit files are admitted; local source display has no native composer. Markdown/HTML/RPC-looking text remains plain and causes zero external requests.');
}
async function saveFinding(text){
 await b.clickText('Write finding',"document.querySelector('.context-preview')");await b.fill('#authored-finding-text',text);
 const before=posts().length;await b.clickText('Save finding',"document.querySelector('.authored-finding-draft')");await b.settle();
 const save=posts().slice(before).find(r=>r.path.endsWith('/findings'));assert.equal(save?.status,201);return save.response.finding;
}
async function episode(){
 const receipts=JSON.parse(await fs.readFile(prefix+'-recovery.json','utf8')).observations.receipts;
 const inputReceipts=receipts.filter(r=>r.fileName!=='literal-content.txt');
 for(const receipt of inputReceipts){
  await b.select('#evidence-search-thread',receipt.threadId);
  const q=receipt.fileName==='observed-checks.txt'?'malformed-tail regression':receipt.fileName==='after-history-imports.py'?'def import_legacy_lines':'def import_jsonl';
  await b.fill('#evidence-search-query',q);await b.clickText('Search history',"document.querySelector('.evidence-discovery')");await b.settle();
  assert.equal(await b.evaluate("document.querySelectorAll('[data-evidence-hit-id]').length"),1);
  assert.equal(await b.evaluate("document.querySelector('[data-evidence-hit-id]').dataset.evidenceField"),'suppliedText.text');
  await b.clickText('Inspect source',"document.querySelector('.evidence-discovery')");await b.settle();
  const inspect=b.requests.filter(r=>r.path.startsWith('/api/evidence/hits/')).at(-1);assert.equal(inspect?.status,200);
  assert.equal(inspect.response.records[0].localEvidence.id,receipt.id);
  const fileEntry=marker.files.find(f=>f.fileName===receipt.fileName);
  assert.equal(JSON.parse(inspect.response.records[0].rawText).params.item.text,await fs.readFile(fileEntry.path,'utf8'));
  await b.clickText('Add these source records',"document.querySelector('.evidence-discovery')");
 }
 await b.fill('#investigation-title','Atomic imports: observed regression and repair');
 await b.fill('#investigation-question','Does the pinned atomic importer prevent malformed-tail retry inflation while preserving intentional repeated lines, and what can these method-level checks establish?');
 for(let n=1;n<=inputReceipts.length;n++)await b.fill(`[aria-label="Why include source ${n}"]`,'Exact supplied public source or captured local check; intake does not authenticate execution or authorship.');
 b.page.phase='save-observation-context';await b.clickText('Save and preview context',"document.querySelector('.context-builder')");await b.settle();
 const create=posts().find(r=>r.phase==='save-observation-context');assert.equal(create?.status,201);
 const owner=create.response,context=owner.contexts[0];assert.equal(context.records.length,4);
 for(const record of context.records){assert.equal(record.localEvidence.classification,'local-owner-supplied');assert.equal(record.localEvidence.hostRecordSha256,record.sha256);}
 assert(!context.coverage.startsWith('Selected app-server evidence only.'));assert.equal(owner.attempt,null);
 const seq=name=>receipts.find(r=>r.fileName===name).seq;
 const finding=await saveFinding(`Observed local counterexample: the historical import method appends each parsed line immediately [evidence:${seq('before-import-method.py')}]. The repaired entry delegates to an adapter that parses the whole iterable before transactionally appending it [evidence:${seq('after-import-method.py')}] [evidence:${seq('after-history-imports.py')}].\n\nThe captured local check retained 1 then 2 records after malformed-tail retries under the old method, versus 0 then 0 under the pinned repaired adapter; two intentional duplicate valid lines remained two [evidence:${seq('observed-checks.txt')}].\n\nScope: public2386b29 method versus publicd2b5fdb adapter, both on today's TraceStore. This is a retrospective method/adapter check, not an entire old-release run, native/model result, human benefit measurement, arbitrary-file safety proof or broad release qualification. File admission preserves supplied bytes; it does not certify who ran the check. Inference: atomic admission addresses retry-prefix inflation without content deduplication in these stated cases.`);
 await shot('frozen-observation-finding','.authored-finding-draft');
 await b.clickText('Dismiss saved finding',"document.querySelector('.authored-finding-draft')");
 await b.clickText('New investigation',"document.querySelector('.work-picker')");await b.settle();
 await b.fill('#context-artifact-picker-search','Atomic imports: observed regression');
 await b.clickText('Search',"document.querySelector('#context-artifact-picker').closest('.catalog-picker')");await b.settle();
 await b.select('#context-artifact-picker',JSON.stringify([owner.id,finding.id]));await b.settle();
 await b.clickText('Add selected result to context',"document.querySelector('.artifact-picker')");
 await b.fill('#investigation-title','Review: retain atomic import, preserve repeated events');
 await b.fill('#investigation-question','What adoption judgment and rollback constraints follow from the exact observed import finding?');
 await b.fill('[aria-label="Why include result 1"]','Review the frozen method comparison and its explicit limits, following original support when needed.');
 b.page.phase='save-review-context';await b.clickText('Save and preview context',"document.querySelector('.context-builder')");await b.settle();
 const reviewCreate=posts().find(r=>r.phase==='save-review-context');assert.equal(reviewCreate?.status,201);const review=reviewCreate.response;
 const reviewFinding=await saveFinding(`Review decision: retain the atomic import behavior demonstrated by [artifact:${finding.id}], including intentional repeated events. The accepted code path is pinned at d2b5fdb; the repair originally integrated in2aae982. The baseline for comparison is the2386b29 import method.\n\nThis is an attributed retrospective review, not code installation, blanket release approval or an execution grant. The finding supports the malformed-tail/retry and intentional-repeat cases only. Remaining obligations include full-suite compatibility, bounded memory and latency on representative inputs, and human usefulness. The check uses local CPU/SQLite with zero native/model calls; performance cost was not measured.\n\nRollback basis: retain the pinned before/after sources and these exact cases. Blindly restoring2386b29 would reintroduce prefix retention; reject that rollback. If a later importer change regresses valid inputs, make a scoped correction against the reviewed parent while keeping atomic malformed-tail refusal and intentional-repeat preservation. No automatic code or instruction activation is requested.`);
 await b.clickText('Compare saved work',"document.querySelector('.work-picker')");await b.settle();
 await b.clickText('Edit arrangement',"document.querySelector('.comparison-surface')");
 for(const [side,value,artifact]of[['left',owner,finding],['right',review,reviewFinding]]){
  await b.fill('#compare-'+side+'-search',value.title);await b.clickText('Search',`document.querySelector('#compare-${side}').closest('.catalog-picker')`);await b.settle();
  await b.select('#compare-'+side,value.id);await b.select('#compare-'+side+'-context',value.currentContextId);await b.select('#compare-'+side+'-artifact',artifact.id);
 }
 await b.clickText('Review arrangement',"document.querySelector('.arrangement-editor')");await b.clickText('Apply arrangement',"document.querySelector('.arrangement-editor')");await b.settle();
 await b.fill('#composition-title','Atomic import: observed case and review');b.page.phase='save-comparison';await b.click('#save-comparison');await b.settle();
 const save=posts().find(r=>r.phase==='save-comparison');assert.equal(save?.status,201);const composition=save.response.composition;
 await shot('saved-reflective-episode','.comparison-apertures');
 await b.page.rpc('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:false});await shot('narrow-reflective-episode','.comparison-apertures');
 report.observations={receipts,owner:await ownerRead(owner.id),finding,review:await ownerRead(review.id),reviewFinding,composition};
 report.checks.push('Actual UI searches and inspects four supplied files, freezes exact local-source context, saves a cited observation and a separate artifact-grounded review.',
 'Existing plain saved comparison carries review decision, scope limits and rollback basis with zero native attempts and no new experiment ontology.');
}
async function boundary(){
 const prior=JSON.parse(await fs.readFile(prefix+'-episode.json','utf8')).observations;
 const receipt=prior.receipts.find(r=>r.fileName==='literal-content.txt');
 const body={requestId:'supplied-text-literal-rendering-fixture',title:'Literal supplied text rendering check',question:'Inspect these literal contents as evidence. No execution or external actions are requested.',selections:[{threadId:receipt.threadId,startSeq:receipt.seq,endSeq:receipt.seq,rationale:'Authored rendering adversary: text only, not an observed command or conversation.'}]};
 const saved=await b.evaluate(`fetch('/api/investigations',{method:'POST',headers:{'content-type':'application/json'},body:${JSON.stringify(JSON.stringify(body))}}).then(async r=>({status:r.status,body:await r.json()}))`);assert([200,201].includes(saved.status));
 await b.fill('#saved-investigation-search',body.title);await b.clickText('Search',"document.querySelector('#saved-investigation').closest('.catalog-picker')");await b.settle();
 await b.select('#saved-investigation',saved.body.id);await b.settle();
 const record=saved.body.contexts[0].records[0],selector=`.context-preview .frozen-record[data-evidence-seq="${receipt.seq}"]`;
 await b.evaluate(`(()=>{for(let e=document.querySelector(${JSON.stringify(selector)});e;e=e.parentElement)if(e.tagName==='DETAILS')e.open=true;})()`);
 const plain=selector+' [data-supplied-text-id]';await b.wait(`!!document.querySelector(${JSON.stringify(plain)})`);
 assert.equal(await b.evaluate(`document.querySelector(${JSON.stringify(plain+' pre')}).textContent`),JSON.parse(record.rawText).params.item.text);
 assert.equal(await b.evaluate(`document.querySelector(${JSON.stringify(plain)}).querySelectorAll('img,iframe,script,a').length`),0);
 await shot('frozen-literal-contents',selector);
 const independent=await seedIndependent();await open();await choose(marker.files.find(f=>f.fileName==='literal-content.txt'));
 b.page.holdPath='/api/evidence/files/preview';await b.clickText('Preview text evidence',dialog);
 for(let n=0;n<100&&!b.page.held;n++)await new Promise(r=>setTimeout(r,50));assert(b.page.held);
 await b.clickText('Close text evidence',dialog);
 const held=b.page.held;b.page.held=null;let delivery;
 try{await b.page.rpc('Fetch.continueRequest',{requestId:held});delivery='released-after-close';}
 catch(error){if(!String(error).includes('Invalid InterceptionId'))throw error;delivery='browser-aborted-before-release';}
 await b.settle();await guard(independent);
 assert.equal(await b.evaluate("document.querySelector('.supplied-text-evidence').closest('dialog').open"),false);
 assert.equal(await storage('nema.supplied-text.v1'),null);assert.deepEqual(external,[]);
 report.observations={owner:saved.body,fixtureSaveStatus:saved.status,sourceDeleted:!!marker.sourceDeleted,delivery,independent};
 report.checks.push('Frozen adversarial supplied text remains exact escaped text with no fetchable elements or external requests.',
 'Held preview is closed before delivery; browser cancellation/release outcome is recorded without claiming that aborted bytes were delivered. Independent pending slots/focus stay exact.');
}
async function reopened(){
 const prior=JSON.parse(await fs.readFile(prefix+'-episode.json','utf8')).observations;
 assert.deepEqual(await ownerRead(prior.owner.id),prior.owner);assert.deepEqual(await ownerRead(prior.review.id),prior.review);
 await b.clickText('Compare',"document.querySelector('.thread-rail')");await b.settle();
 await b.evaluate("document.querySelector('#saved-comparisons-browser').open=true");await b.settle();await b.select('#saved-composition',prior.composition.id);
 await b.click('#preview-comparison');await b.settle();await b.click('#open-comparison');await b.settle();
 await b.wait(`document.querySelector('[data-aperture="left"]')?.dataset.artifactId===${JSON.stringify(prior.finding.id)}`);
 await shot('recovered-saved-episode','.comparison-apertures');
 await b.clickText('Inspect result provenance',"document.querySelector('[data-aperture=\"left\"]')");
 await b.wait(`document.querySelector('.artifact-lineage[open] [data-lineage-context-id]')?.dataset.lineageContextId===${JSON.stringify(prior.owner.currentContextId)}`);
 for(const record of prior.owner.contexts[0].records){
  const selector=`.artifact-lineage[open] .frozen-record[data-evidence-seq="${record.seq}"]`;
  await b.evaluate(`document.querySelector(${JSON.stringify(selector)}).closest('.lineage-record').open=true`);
  await b.wait(`!!document.querySelector(${JSON.stringify(selector)})?.querySelector('[data-supplied-text-id]')`);
  const plain=selector+' [data-supplied-text-id]';
  if(JSON.parse(record.rawText).params.item.text.length>12000)await b.clickText('Read complete supplied text',`document.querySelector(${JSON.stringify(plain)})`);
  assert.equal(await b.evaluate(`document.querySelector(${JSON.stringify(plain+' pre')}).textContent`),JSON.parse(record.rawText).params.item.text);
  assert.equal(await b.evaluate(`document.querySelector(${JSON.stringify(selector)}).querySelectorAll('img,iframe,script,a').length`),0);
  await shot('frozen-source-'+record.seq,selector);
 }
 assert.equal(posts().length,0);assert.deepEqual(external,[]);report.observations=prior;
 if(mode==='source-deleted'){
  for(const receipt of prior.receipts){const read=await b.evaluate(`fetch('/api/evidence/files/'+${JSON.stringify(receipt.id)}).then(r=>r.status)`);assert.equal(read,404);}
  report.checks.push('Marked disposable-fixture source ledger/raw deletion leaves both exact canonical owners and their frozen text support unchanged; originals are404.');
  const boundary=JSON.parse(await fs.readFile(prefix+'-boundary.json','utf8')).observations;
  assert.deepEqual(await ownerRead(boundary.owner.id),boundary.owner);
 }
 report.checks.push('After actual API restart a fresh browser opens the exact saved observation/review comparison and frozen supplied-text support with zero POSTs.');
}
try{
 await fresh('supplied-text-'+mode);
 assert.equal(b.requests.find(r=>r.path==='/api/investigations/capabilities')?.response.nativeExecution.available,false);
 if(mode==='baseline')await baseline();else if(mode==='flow')await flow();else if(mode==='recovery')await recovery();else if(mode==='episode')await episode();else if(mode==='boundary')await boundary();else if(['reopened','source-deleted'].includes(mode))await reopened();else throw Error('Unsupported acceptance mode: '+mode);
 assert.deepEqual(b.exceptions,[]);
 report.requests=b.requests;report.exceptions=b.exceptions;report.externalRequests=external;
 await fs.writeFile(prefix+'-'+mode+'.json',JSON.stringify(report,null,2)+'\n');
 console.log(JSON.stringify({mode,checks:report.checks,requests:b.requests.length,posts:posts().length,screenshots:report.screenshots}));
}catch(error){
 report.error=String(error?.stack??error);report.requests=b.requests;report.exceptions=b.exceptions;
 await b.screenshot(prefix+'-'+mode+'-failure.png').catch(()=>{});
 await fs.writeFile(prefix+'-'+mode+'-failure.json',JSON.stringify(report,null,2)+'\n');throw error;
}finally{await b.close();}
