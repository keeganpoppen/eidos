// Read-only browser acceptance for scripts/private_native_evidence_demo.py.
// Seed that demo with --db /tmp/private-demo.db --output /tmp/private-demo.json;
// serve it with --resume --serve --port 8767 and point Vite's /api proxy at it.
// Start an isolated Chromium with CDP on :9231, then run:
// NEMA_PRIVATE_EVIDENCE_MARKER=/tmp/private-demo.json NEMA_UI_ORIGIN=http://127.0.0.1:5181 \
// NEMA_UI_DEBUG=http://127.0.0.1:9231 NEMA_UI_EVIDENCE_PREFIX=/tmp/private-ui \
// bun scripts/private_native_evidence_browser.mjs
// Creates only browser-owned presentation state and screenshots. No API writes,
// auth, native launches or model calls; source publication projection is required.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {browserAcceptance} from './browser_acceptance_support.mjs';
const markerPath=process.env.NEMA_PRIVATE_EVIDENCE_MARKER;
assert(markerPath, 'Set NEMA_PRIVATE_EVIDENCE_MARKER to the authored demo marker JSON.');
const marker=JSON.parse(await fs.readFile(markerPath,'utf8'));
assert.equal(marker.schemaVersion,'synthetic-private-native-evidence/v1');
assert.equal(marker.classification,'authored-subprocess-fixture');
assert.equal(marker.realNativeOrModelCalls,0);
const prefix=process.env.NEMA_UI_EVIDENCE_PREFIX ?? '/tmp/nema-private-evidence-browser';
const origin=process.env.NEMA_UI_ORIGIN ?? 'http://127.0.0.1:5181';
const debug=process.env.NEMA_UI_DEBUG ?? 'http://127.0.0.1:9231';
for(const address of [origin,debug]) {
 const url=new URL(address);
 assert(url.protocol==='http:' && ['127.0.0.1','localhost','[::1]'].includes(url.hostname), 'Use the local authored fixture and isolated Chromium only.');
}
for(const mode of ['conclusion','inquiry']) {
 const result=marker.results[mode];
 assert.equal(result.outputSeqs.length,1);
 assert(Number.isSafeInteger(result.outputSeqs[0]) && result.outputSeqs[0]>0);
 assert(typeof result.threadId==='string' && result.threadId.length>0);
}
const aSeq=marker.results.conclusion.outputSeqs[0],qSeq=marker.results.inquiry.outputSeqs[0];
const sourcePath=mode=>'/api/threads/'+encodeURIComponent(marker.results[mode].threadId);
const requestedSequence=(request,mode,seq)=>request.path===sourcePath(mode) && new URLSearchParams(request.query).get('aroundSeq')===String(seq);
const notice='Derived publication; original native evidence was recorded privately.';
const b=await browserAcceptance({origin,debug});
const checks=[],screenshots=[],measurements=[];
const root="document.querySelector('.investigation-result')";
async function choose(mode){await b.select('#saved-investigation',marker.investigations[mode]);await b.wait(`document.querySelector('.investigation-state')?.textContent.includes(${JSON.stringify(marker.investigations[mode])})`);}
async function shot(name,selector){await b.evaluate(`document.querySelector(${JSON.stringify(selector)}).scrollIntoView({block:'start'})`);const path=prefix+'-'+name+'.png';await b.screenshot(path);screenshots.push(path);}
async function overflow(name){const v=await b.evaluate(`({width:innerWidth,document:document.documentElement.scrollWidth,body:document.body.scrollWidth})`);measurements.push({name,...v});assert(v.document<=v.width+1,JSON.stringify({name,...v}));}
try{
 await b.fresh('real-private-publication');
 await choose('conclusion');const a=marker.results.conclusion;
 await b.wait(`${root}?.dataset.resultArtifactId===${JSON.stringify(a.artifactId)}`);
 assert((await b.evaluate(`${root}.textContent`)).includes(notice));
 assert((await b.evaluate(`${root}.textContent`)).includes('Synthetic output'));
 assert(!(await b.evaluate(`${root}.textContent`)).includes('Inspect recorded native output'));
 await b.clickText('Inspect published result',root);
 await b.wait(`!!document.querySelector('.item-card[data-start="${aSeq}"]')`);
 await b.settle();
 assert(b.requests.some(r=>requestedSequence(r,'conclusion',aSeq)));
 const publicThread=b.requests.findLast(r=>r.path===sourcePath('conclusion')&&r.response?.turns)?.response;
 assert(publicThread);
 const pub=publicThread.turns.flatMap(t=>t.items).find(i=>i.recordSeqs?.includes(aSeq));
 assert(pub);assert.equal(pub.id,`publication@${aSeq}`);assert.equal(pub.type,'privateResultPublication');assert.equal(pub.complete,true);assert.equal(pub.raw.provenance.kind,'private-capsule');
 assert(!JSON.stringify(publicThread).includes('PRIVATE_'));
 const sourceItem=`document.querySelector('.item-card[data-start="${aSeq}"]')`;
 const text=await b.evaluate(`${sourceItem}.textContent`);
 assert(text.includes('Published result'));assert(text.includes(notice));assert(text.includes('Synthetic output'));assert(!text.includes('LIVE'));
 await b.evaluate(`${sourceItem}.querySelector('details').open=true`);
 await b.wait(`${sourceItem}.textContent.includes('private-capsule')`);
 checks.push(`conclusion publication label, separate synthetic class, public source sequence ${aSeq} and inspectable derived item`);
 await shot('desktop-conclusion','.investigation-result');await overflow('desktop-conclusion');
 await b.clickText('Inspect result provenance',root);
 await b.wait(`!!document.querySelector('dialog[open] [data-lineage-artifact-id="${a.artifactId}"][data-lineage-context-id="${a.contextId}"]')`);
 await b.clickText('Close result provenance',"document.querySelector('dialog[open]')");
 await b.reload();await b.wait(`${root}?.dataset.resultArtifactId===${JSON.stringify(a.artifactId)}`);
 assert.equal((await b.local('nema.investigation-draft.v1')).selectedId,marker.investigations.conclusion);
 assert.equal((await b.local('nema.investigation-draft.v1')).previewId,a.contextId);
 await b.settle();const reopened=b.requests.findLast(r=>r.path.endsWith('/'+marker.investigations.conclusion+'/view')&&r.response?.investigation)?.response.investigation;
 assert.deepEqual([reopened.artifact.id,reopened.artifact.contextId,reopened.artifact.attemptId,reopened.artifact.outputSeqs],[a.artifactId,a.contextId,a.attemptId,[aSeq]]);
 checks.push('reload preserves owner, context, attempt, artifact and public sequence');
 await choose('inquiry');const q=marker.results.inquiry;
 await b.wait(`${root}?.dataset.resultArtifactId===${JSON.stringify(q.artifactId)}`);
 await b.wait("document.querySelector('.evidence-review')?.textContent.includes('Which retained record supports the choice?')");
 assert((await b.evaluate(`${root}.textContent`)).includes(notice));
 await b.clickText('Inspect published result',root);await b.settle();
 assert(b.requests.some(r=>requestedSequence(r,'inquiry',qSeq)));
 await b.wait(`!!document.querySelector('.source-range[data-support-start="${qSeq}"]')`);
 const inquiry=b.requests.findLast(r=>r.path.endsWith('/'+marker.investigations.inquiry+'/view')&&r.response?.investigation)?.response.investigation;
 assert.equal(inquiry.continuation.inquiry.status,'pending');assert.equal(inquiry.continuation.cause.schemaVersion,2);assert.equal(inquiry.continuation.cause.nativeEvent.evidence.kind,'private-capsule-record');assert(!Object.hasOwn(inquiry.continuation.cause,'requestSeq'));
 await b.wait(`!!document.querySelector('.item-card[data-start="${qSeq}"]')`);
 checks.push(`inquiry public sequence ${qSeq} and pending question; cause uses typed private reference`);
 await shot('desktop-inquiry','.investigation-result');
 await b.reload();await b.wait(`${root}?.dataset.resultArtifactId===${JSON.stringify(q.artifactId)}`);await b.wait("document.querySelector('.evidence-review')?.textContent.includes('Which retained record supports the choice?')");
 assert.equal((await b.local('nema.investigation-draft.v1')).selectedId,marker.investigations.inquiry);
 checks.push('inquiry reload keeps exact artifact and pending question');
 await b.page.rpc('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:false});
 await shot('mobile-inquiry','.evidence-review');await overflow('mobile-inquiry');
 await choose('conclusion');await b.wait(`${root}?.dataset.resultArtifactId===${JSON.stringify(a.artifactId)}`);await shot('mobile-conclusion','.investigation-result');await overflow('mobile-conclusion');
 for(const mode of ['error','malformed']){await choose(mode);await b.wait("document.querySelector('.investigation-state')?.textContent.includes('unknown')");assert.equal(await b.evaluate("!!document.querySelector('.investigation-result')"),false);assert(!(await b.evaluate('document.body.textContent')).includes('PRIVATE_'));await overflow('mobile-'+mode);}
 checks.push('error and malformed cases retain unknown outcome, no artifact or public canaries');
 await b.page.rpc('Emulation.setDeviceMetricsOverride',{width:1600,height:1100,deviceScaleFactor:1,mobile:false});
 const target=mode=>({investigationId:marker.investigations[mode],contextId:marker.results[mode].contextId,artifactId:marker.results[mode].artifactId});
 const arrangement={left:target('conclusion'),right:target('inquiry'),lens:'result',layout:'beside'};
 await b.evaluate(`localStorage.setItem('nema.composition.v1',${JSON.stringify(JSON.stringify({version:1,open:true,arrangement,undo:[],focus:null}))})`);
 await b.reload();await b.wait(`document.querySelector('[data-aperture=left]')?.textContent.includes('Published result records: ${aSeq}')`);
 assert((await b.evaluate("document.querySelector('[data-aperture=right]').textContent")).includes(`Published result records: ${qSeq}`));
 assert((await b.evaluate("document.querySelector('[data-aperture=left]').textContent")).includes(notice));
 await shot('desktop-comparison','.comparison-apertures');
 await b.clickText('Inspect published result',"document.querySelector('[data-aperture=left]')");
 await b.wait(`!!document.querySelector('dialog[open] [data-lineage-artifact-id="${a.artifactId}"][data-lineage-context-id="${a.contextId}"]')`);
 await b.clickText('Close result provenance',"document.querySelector('dialog[open]')");
 await b.page.rpc('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:false});
 await shot('mobile-comparison','.comparison-apertures');await overflow('mobile-comparison');
 checks.push('real publication comparison retains main sequences and exact artifact inspector at desktop and 390px');
 await b.settle();
 assert.deepEqual(b.exceptions,[]);assert(b.requests.every(r=>r.method==='GET'));assert(b.requests.every(r=>r.status===200 && Object.hasOwn(r,'response')));assert(b.requests.every(r=>!JSON.stringify(r.response).includes('PRIVATE_')));
 assert(!b.requests.some(r=>r.path.includes('capsule_')));
 const summary={classification:'real-local-api-authored-subprocess-fixture',nativeOrModelCalls:0,marker,checks,measurements,screenshots,requests:b.requests,exceptions:b.exceptions};
 await fs.writeFile(prefix+'-browser.json',JSON.stringify(summary,null,2)+'\n');console.log(JSON.stringify({checks,measurements,requestCount:b.requests.length,screenshots,exceptions:b.exceptions}));
}finally{await b.close();}
