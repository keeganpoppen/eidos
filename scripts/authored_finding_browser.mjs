// Actual local UI/API acceptance over authored public repository excerpts. No native calls.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {browserAcceptance} from './browser_acceptance_support.mjs';
const origin=process.env.NEMA_UI_ORIGIN??'http://127.0.0.1:5173';
const debug=process.env.NEMA_UI_DEBUG??'http://127.0.0.1:9233';
const prefix=process.env.NEMA_UI_EVIDENCE_PREFIX??'/tmp/nema-authored-finding-browser-20261013';
const mode=process.env.NEMA_AUTHORED_FINDING_MODE??'baseline';
const marker=JSON.parse(await fs.readFile(process.env.NEMA_AUTHORED_FINDING_MARKER,'utf8'));
assert.equal(marker.schemaVersion,'authored-public-repository-finding/v1');
assert.equal(marker.classification,'authored-public-repository-excerpts');
assert.equal(marker.nativeOrModelCalls,0);
assert(['baseline','flow','recovery','reopened'].includes(mode));
for(const address of [origin,debug]) {const u=new URL(address);assert(u.protocol==='http:'&&['127.0.0.1','localhost','[::1]'].includes(u.hostname));}
const draftKey='nema.investigation-draft.v1',findingKey='nema.authored-finding.v1';
const b=await browserAcceptance({origin,debug});
const report={classification:marker.classification,mode,nativeOrModelCalls:0,checks:[],observations:{},screenshots:[]};
const posts=()=>b.requests.filter(r=>r.method==='POST');
const storage=key=>b.evaluate(`localStorage.getItem(${JSON.stringify(key)})`);
async function shot(name,selector) {
 if(selector)await b.evaluate(`document.querySelector(${JSON.stringify(selector)}).scrollIntoView({block:'start'})`);
 const path=prefix+'-'+mode+'-'+name+'.png';await b.screenshot(path);report.screenshots.push(path);
 const size=await b.evaluate(`({width:innerWidth,document:document.documentElement.scrollWidth,component:${selector?`document.querySelector(${JSON.stringify(selector)}).scrollWidth-document.querySelector(${JSON.stringify(selector)}).clientWidth`:'0'}})`);
 assert(size.document<=size.width+1,JSON.stringify(size));assert(size.component<=1,JSON.stringify(size));
 (report.measurements??=[]).push({name,...size});
}
async function seedEditor() {
 await b.select('#saved-investigation',marker.ownerId);
 await b.wait(`document.querySelector('.context-preview')?.textContent.includes(${JSON.stringify(marker.contextId)})`);await b.settle();
 await b.fill('#investigation-question','Independent unfinished merge question; preserve this pending save.');
 await b.fill('[aria-label="Why include source 1"]','Independent unsaved source rationale.');await b.settle();
 const pending={id:'authored-finding-independent-editor-save',body:'{"id":"authored-independent-save","question":"Preserve my unresolved save identity"}'};
 await b.evaluate(`(()=>{const value=JSON.parse(localStorage.getItem(${JSON.stringify(draftKey)}));value.pendingRequest=${JSON.stringify(pending)};localStorage.setItem(${JSON.stringify(draftKey)},JSON.stringify(value));})()`);
 await b.reload();await b.settle();return storage(draftKey);
}
async function baseline() {
 const originalDraft=await seedEditor();
 assert.equal(await b.evaluate("[...document.querySelectorAll('button')].some(e=>e.textContent.trim()==='Write finding')"),false);
 assert.equal(await b.evaluate("!!document.querySelector('.authored-finding-draft')"),false);
 assert.equal(await b.evaluate("[...document.querySelectorAll('button')].find(e=>e.textContent.trim()==='Start specialist with this context').disabled"),true);
 const found=await b.evaluate(`fetch('/api/investigations/artifacts?q='+encodeURIComponent(${JSON.stringify(marker.search)})).then(r=>r.json())`);
 assert.deepEqual(found.artifacts,[]);
 await shot('saved-context','.context-preview');
 await b.page.rpc('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:false});await shot('mobile-context','.context-preview');
 assert.equal(await storage(draftKey),originalDraft);assert.equal(posts().length,0);
 report.observations={originalDraft,catalog:found};
 report.checks.push('Saved public-repository question retains its rationale; no authored-finding action exists and result search finds no conclusion.',
 'Default native start remains disabled; exact independent dirty/pending editor survives read-only inspection.');
}
const form="document.querySelector('.authored-finding-draft')";
const ownerRead=id=>b.evaluate(`fetch('/api/investigations/'+${JSON.stringify(id)}).then(r=>{if(!r.ok)throw Error('Owner read failed');return r.json()})`);
async function restore(originalDraft,pendingFinding) {
 await b.evaluate(`localStorage.setItem(${JSON.stringify(draftKey)},${JSON.stringify(originalDraft)});localStorage.setItem(${JSON.stringify(findingKey)},${JSON.stringify(pendingFinding)});`);
 await b.reload();await b.settle();
}
async function flow() {
 const originalDraft=await seedEditor();
 await b.clickText('Write finding',"document.querySelector('.context-preview')");
 await b.wait("!!document.querySelector('#authored-finding-text')");
 await b.fill('#authored-finding-text',marker.findingText);await b.settle();
 const stage=JSON.parse(await storage(findingKey));
 assert.equal(stage.source.investigationId,marker.ownerId);assert.equal(stage.source.contextId,marker.contextId);
 assert.equal(stage.source.question,marker.question);assert.equal(stage.text,marker.findingText);
 assert.equal(await storage(draftKey),originalDraft);assert.equal(posts().length,0);
 await shot('exact-context-draft','.authored-finding-draft');
 b.page.phase='lost-finding-reply';b.page.losePost='/api/investigations/'+marker.ownerId+'/findings';
 await b.clickText('Save finding',form);await b.settle();
 assert.equal(b.page.lost.length,1);assert.equal(b.page.lost[0].committedStatus,201);
 const pendingFinding=await storage(findingKey);const pending=JSON.parse(pendingFinding);
 const saveBody=JSON.parse(pending.request);assert.equal(saveBody.contextId,marker.contextId);assert.equal(saveBody.text,marker.findingText);
 assert.equal(pending.text,null);assert.equal(pending.savedId,null);
 assert.equal(await storage(draftKey),originalDraft);assert.equal(posts().length,1);
 await b.reload();await b.settle();
 assert.equal(await storage(findingKey),pendingFinding);assert.equal(await storage(draftKey),originalDraft);assert.equal(posts().length,1);
 await shot('pending-after-reload','.authored-finding-draft');
 const owner=await ownerRead(marker.ownerId);
 assert.equal(owner.findings.length,1);assert.equal(owner.findings[0].contextId,marker.contextId);
 assert.deepEqual({...owner,findings:undefined},{...marker.originalOwner,findings:undefined});
 report.observations={originalDraft,pendingFinding,saveBody,finding:owner.findings[0],owner};
 report.checks.push('Finding stages the exact saved C0/question despite an independent dirty/pending editor.',
 'A successful finding save reply is deliberately lost; reload keeps the exact pending request and makes no automatic POST.',
 'Canonical owner adds only one immutable finding; native/context state and independent editor stay unchanged.');
}
async function inspectFinding(finding) {
 await b.clickText('Inspect saved finding',form);
 await b.wait(`document.querySelector('[data-lineage-artifact-id]')?.dataset.lineageArtifactId===${JSON.stringify(finding.id)} && document.querySelector('[data-lineage-context-id]')?.dataset.lineageContextId===${JSON.stringify(marker.contextId)}`);
 assert.equal(await b.evaluate("document.querySelector('.artifact-lineage[open] .original-question').textContent.includes("+JSON.stringify(marker.question)+")"),true);
 assert.equal(await b.evaluate("document.querySelectorAll('.artifact-lineage[open] .lineage-record').length"),2);
 await shot('original-finding-support','.artifact-lineage[open]');
 await b.clickText('Close result provenance',"document.querySelector('.artifact-lineage[open]')");
 await b.wait("document.querySelectorAll('.artifact-lineage[open]').length===0");
}
async function recovery() {
 const prior=JSON.parse(await fs.readFile(prefix+'-flow.json','utf8'));
 assert.notEqual(marker.currentContextId,marker.contextId,'Advance the marked fixture and restart API before this mode');
 await restore(prior.observations.originalDraft,prior.observations.pendingFinding);
 assert.equal(posts().length,0);
 b.page.phase='receipt-after-api-restart';await b.clickText('Check finding receipt',form);await b.settle();
 const read=b.requests.find(r=>r.path==='/api/investigations/'+marker.ownerId+'/findings/requests/'+prior.observations.saveBody.requestId);
 assert.equal(read?.status,200);assert.deepEqual(read.response.finding,prior.observations.finding);
 await b.wait(`document.querySelector('[data-saved-finding-id]')?.dataset.savedFindingId===${JSON.stringify(prior.observations.finding.id)}`);
 assert.equal(await storage(draftKey),prior.observations.originalDraft);assert.equal(posts().length,0);
 await shot('recovered-receipt','.authored-finding-draft');
 await inspectFinding(prior.observations.finding);
 await b.page.rpc('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:false});await shot('mobile-receipt','.authored-finding-draft');
 await b.page.rpc('Emulation.setDeviceMetricsOverride',{width:1600,height:1100,deviceScaleFactor:1,mobile:false});
 // Restore the captured pending snapshot into a separate isolated context for exact retry.
 await b.fresh('finding-exact-retry');await b.settle();await restore(prior.observations.originalDraft,prior.observations.pendingFinding);
 b.page.phase='exact-retry';await b.clickText('Retry saving this finding',form);await b.settle();
 const replay=posts().find(r=>r.path==='/api/investigations/'+marker.ownerId+'/findings');
 assert.equal(replay?.status,200);assert.deepEqual(replay.response.finding,prior.observations.finding);assert.deepEqual(JSON.parse(replay.body),prior.observations.saveBody);
 assert.equal(await storage(draftKey),prior.observations.originalDraft);
 const owner=await ownerRead(marker.ownerId);assert.equal(owner.findings.length,1);assert.equal(owner.currentContextId,marker.currentContextId);
 assert.equal(owner.attempt,null);assert.equal(owner.artifact,null);assert.equal(owner.status,'draft');
 report.observations={finding:prior.observations.finding,owner,originalDraft:prior.observations.originalDraft,savedStage:await storage(findingKey)};
 report.checks.push('After actual API restart and C0→C1 advancement, explicit receipt GET recovers exact F0/C0 without POST.',
 'Separate restored pending snapshot retries the exact body and receives F0/C0; one finding remains and native state stays absent.');
 await discoverReuseCompare(prior.observations.finding);
}
async function discoverReuseCompare(finding) {
 await b.fresh('finding-discovery-reuse');await b.settle();
 b.page.phase='discover-and-inspect';
 await b.fill('#context-artifact-picker-search',marker.search);
 await b.clickText('Search',"document.querySelector('#context-artifact-picker').closest('.catalog-picker')");await b.settle();
 await b.select('#context-artifact-picker',JSON.stringify([marker.ownerId,finding.id]));await b.settle();
 assert.equal(await b.evaluate("document.querySelector('.catalog-selection')?.dataset.selectedResult"),finding.id);
 assert.equal(await b.evaluate("document.querySelector('.catalog-match')?.dataset.matchField"),'result');
 await b.clickText('Inspect selected result',"document.querySelector('.artifact-picker')");
 await b.wait(`document.querySelector('[data-lineage-context-id]')?.dataset.lineageContextId===${JSON.stringify(marker.contextId)}`);
 await shot('discovered-original-support','.artifact-lineage[open]');
 await b.clickText('Close result provenance',"document.querySelector('.artifact-lineage[open]')");
 await b.wait("document.querySelectorAll('.artifact-lineage[open]').length===0");
 await b.clickText('Add selected result to context',"document.querySelector('.artifact-picker')");
 await b.fill('#investigation-title','A test for incremental import identity');
 await b.fill('#investigation-question','Which comparison should distinguish a retransmitted record from two real identical events?');
 await b.fill('[aria-label="Why include result 1"]','Use the exact recorded finding and follow its original support.');
 b.page.phase='save-reused-question';await b.clickText('Save and preview context',"document.querySelector('.context-builder')");await b.settle();
 const creation=posts().find(r=>r.phase==='save-reused-question'&&r.path==='/api/investigations');
 assert.equal(creation?.status,201);const derived=creation.response;
 assert(derived.id);const context=derived.contexts[0];
 assert.deepEqual(context.records,[]);assert.equal(context.artifactInputs.length,1);
 const input=context.artifactInputs[0];assert.deepEqual(input.artifact,finding);assert.equal(input.sourceContextId,marker.contextId);
 assert.equal(input.sourceAttemptManifestId,null);assert.equal(input.sourceAdoption,null);
 assert.equal(input.sourceManifestId,marker.originalOwner.contexts[0].manifestId);
 assert.equal(derived.attempt,null);assert.equal(derived.artifact,null);
 await b.clickText('Write finding',"document.querySelector('.context-preview')");
 const nextText='Proposed test: compare one replayed delivery with two intentionally repeated events. This follows the earlier question [artifact:'+finding.id+']. The original raw record is not directly supplied here [evidence:1].';
 await b.fill('#authored-finding-text',nextText);b.page.phase='derived-finding';await b.clickText('Save finding',form);await b.settle();
 const derivedWrite=posts().find(r=>r.phase==='derived-finding');assert.equal(derivedWrite?.status,201);
 const nextFinding=derivedWrite.response.finding;assert.deepEqual(nextFinding.citations,[]);assert.deepEqual(nextFinding.unsupportedCitations,[1]);assert.deepEqual(nextFinding.artifactCitations,[finding.id]);
 await shot('derived-finding-no-inherited-records','.authored-finding-draft');
 await b.clickText('Dismiss saved finding',form);
 await b.select('#saved-investigation',marker.ownerId);await b.settle();
 await b.select('#context-revision',marker.currentContextId);
 await b.clickText('Write finding',"document.querySelector('.context-preview')");
 await b.fill('#authored-finding-text',marker.uncitedText);b.page.phase='uncited-hypothesis';await b.clickText('Save finding',form);await b.settle();
 const uncitedWrite=posts().find(r=>r.phase==='uncited-hypothesis');assert.equal(uncitedWrite?.status,201);
 const uncited=uncitedWrite.response.finding;assert.equal(uncited.contextId,marker.currentContextId);assert.deepEqual(uncited.citations,[]);assert.deepEqual(uncited.artifactCitations,[]);
 assert.equal(await b.evaluate(form+".textContent.includes('No cited support')"),true);
 await shot('uncited-hypothesis','.authored-finding-draft');
 await b.clickText('Compare saved work',"document.querySelector('.work-picker')");await b.settle();
 await compareFindings(finding,derived,nextFinding,uncited);
 report.checks.push('Remembered result text discovers F0 and its original C0 support before adding it.',
 'New B freezes exact F0 with no attempt/adoption pin. B finding cites F0 but marks inherited evidence:1 unsupported.',
 'A separate uncited C1 hypothesis saves with No cited support. Two exact findings form a saved plain comparison without native execution.');
}
async function compareFindings(finding,derived,nextFinding,uncited) {
 const context=derived.contexts[0];
 await b.clickText('Edit arrangement',"document.querySelector('.comparison-surface')");
 // Catalogs are bounded pages; explicitly search the named owner instead of
 // assuming a newly created owner is already in a mounted picker's cached page.
 for(const [side,id,title,contextId,artifactId] of [['left',marker.ownerId,marker.originalOwner.title,marker.contextId,finding.id],['right',derived.id,derived.title,context.id,nextFinding.id]]) {
  await b.fill('#compare-'+side+'-search',title);
  await b.clickText('Search',`document.querySelector('#compare-${side}').closest('.catalog-picker')`);await b.settle();
  await b.select('#compare-'+side,id);await b.select('#compare-'+side+'-context',contextId);await b.select('#compare-'+side+'-artifact',artifactId);
 }
 await b.clickText('Review arrangement',"document.querySelector('.arrangement-editor')");
 await b.clickText('Apply arrangement',"document.querySelector('.arrangement-editor')");await b.settle();
 await b.wait(`document.querySelector('[data-aperture="left"]')?.dataset.artifactId===${JSON.stringify(finding.id)} && document.querySelector('[data-aperture="right"]')?.dataset.artifactId===${JSON.stringify(nextFinding.id)}`);
 await b.fill('#composition-title','Import identity: finding and proposed test');
 b.page.phase='save-finding-comparison';await b.click('#save-comparison');await b.settle();
 const snapshotWrite=posts().find(r=>r.phase==='save-finding-comparison');assert.equal(snapshotWrite?.status,201);
 const snapshot=snapshotWrite.response.composition;assert.equal(snapshot.arrangement.left.artifactId,finding.id);assert.equal(snapshot.arrangement.right.artifactId,nextFinding.id);
 await shot('saved-comparison','.comparison-apertures');
 await b.page.rpc('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:false});await shot('mobile-comparison','.comparison-apertures');
 report.observations={...report.observations,derived:await ownerRead(derived.id),nextFinding,uncited,snapshot,
  canonicalOwner:await ownerRead(marker.ownerId),compositionStorage:await storage('nema.composition.v1')};
 report.checks.push('Explicit catalog searches bind both exact findings; the applied plain comparison saves without native execution.');
}
async function reopened() {
 const prior=JSON.parse(await fs.readFile(prefix+'-recovery.json','utf8'));
 assert.deepEqual(await ownerRead(marker.ownerId),prior.observations.canonicalOwner);
 assert.deepEqual(await ownerRead(prior.observations.derived.id),prior.observations.derived);
 await b.clickText('Compare',"document.querySelector('.thread-rail')");await b.settle();
 await b.evaluate("document.querySelector('#saved-comparisons-browser').open=true");await b.settle();
 await b.select('#saved-composition',prior.observations.snapshot.id);
 await b.click('#preview-comparison');await b.settle();
 await b.click('#open-comparison');await b.settle();
 await b.wait(`document.querySelector('[data-aperture="left"]')?.dataset.artifactId===${JSON.stringify(prior.observations.finding.id)} && document.querySelector('[data-aperture="right"]')?.dataset.artifactId===${JSON.stringify(prior.observations.nextFinding.id)}`);
 await shot('exact-comparison-after-restart','.comparison-apertures');
 await b.clickText('Inspect result provenance',"document.querySelector('[data-aperture=\"left\"]')");
 await b.wait(`document.querySelector('.artifact-lineage[open] [data-lineage-context-id]')?.dataset.lineageContextId===${JSON.stringify(marker.contextId)}`);
 for(const record of marker.originalOwner.contexts[0].records) {
  const selector=`.artifact-lineage[open] .frozen-record[data-evidence-seq="${record.seq}"]`;
  await b.evaluate(`(()=>{const record=document.querySelector(${JSON.stringify(selector)});record.closest('.lineage-record').open=true;record.querySelector('.raw-evidence').open=true;})()`);
  await b.wait(`!!document.querySelector(${JSON.stringify(selector+' .raw-evidence pre')})`);
  assert.equal(await b.evaluate(`document.querySelector(${JSON.stringify(selector+' .raw-evidence pre')}).textContent`),record.rawText);
  assert.equal(await b.evaluate(`document.querySelector(${JSON.stringify(selector+' .record-hash')}).textContent`),'SHA-256 '+record.sha256);
  await shot('exact-raw-record-'+record.seq,selector);
 }
 await b.clickText('Close result provenance',"document.querySelector('.artifact-lineage[open]')");
 await b.wait("document.querySelectorAll('.artifact-lineage[open]').length===0");
 await b.page.rpc('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:false});await shot('mobile-reopened-comparison','.comparison-apertures');
 assert.equal(posts().length,0);
 report.observations={snapshot:prior.observations.snapshot,canonicalOwner:prior.observations.canonicalOwner,derived:prior.observations.derived};
 report.checks.push('After a second actual API restart a fresh browser finds, previews and opens the exact saved comparison with zero POSTs; both owners/findings remain byte-equivalent.',
 'The visible source inspector opens both original frozen records; displayed raw bytes and SHA-256 match the original C0 exactly.');
}
try {
 await b.fresh('authored-finding-'+mode);await b.settle();
 assert.equal(b.requests.find(r=>r.path==='/api/investigations/capabilities')?.response.nativeExecution.available,false);
 if(mode==='baseline')await baseline();
 else if(mode==='flow')await flow();
 else if(mode==='recovery')await recovery();
 else await reopened();
 assert.deepEqual(b.exceptions,[]);
 assert(posts().every(r=>r.path==='/api/investigations'||r.path==='/api/compositions'||/^\/api\/investigations\/[^/]+\/findings$/.test(r.path)),'Only explicit question, finding and comparison saves are allowed');
 report.apiRequests=b.requests;report.exceptions=b.exceptions;
 await fs.writeFile(prefix+'-'+mode+'.json',JSON.stringify(report,null,2)+'\n');
 console.log(JSON.stringify({checks:report.checks,requests:b.requests.length,posts:posts().length},null,2));
} catch(error) {
 await b.settle().catch(()=>{});await b.screenshot(prefix+'-'+mode+'-failure.png').catch(()=>{});
 await fs.writeFile(prefix+'-'+mode+'-failure.json',JSON.stringify({...report,error:String(error),apiRequests:b.requests,exceptions:b.exceptions},null,2)+'\n');throw error;
} finally {await b.close();}
