// Authored local UI/API discovery acceptance. No native/model calls.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import { browserAcceptance } from './browser_acceptance_support.mjs';
const marker=JSON.parse(await fs.readFile(process.env.NEMA_EVIDENCE_DISCOVERY_MARKER,'utf8'));
assert.equal(marker.schemaVersion,'synthetic-evidence-discovery/v1');
const origin=process.env.NEMA_UI_ORIGIN??'http://127.0.0.1:5173';
const debug=process.env.NEMA_UI_DEBUG??'http://127.0.0.1:9233';
const prefix=process.env.NEMA_UI_EVIDENCE_PREFIX??'/tmp/nema-evidence-discovery-browser';
const mode=process.env.NEMA_EVIDENCE_DISCOVERY_MODE??'baseline';
assert(['baseline','flow','reopened'].includes(mode));
for(const address of [origin,debug]) {const url=new URL(address);assert(url.protocol==='http:'&&['127.0.0.1','localhost','[::1]'].includes(url.hostname));}
const b=await browserAcceptance({origin,debug});
const pane="document.querySelector('.evidence-discovery')";
const draftKey='nema.investigation-draft.v1';
const draft=()=>b.evaluate(`localStorage.getItem(${JSON.stringify(draftKey)})`);
const posts=()=>b.requests.filter(r=>r.method==='POST');
const report={classification:'authored-unmapped-history',nativeOrModelCalls:0,mode,checks:[],observations:{},screenshots:[]};
try {
 await b.fresh('unmapped-history-'+mode);await b.settle();
 assert.equal(b.requests.find(r=>r.path==='/api/investigations/capabilities')?.response.nativeExecution.available,false);
 assert(b.requests.find(r=>r.path==='/api/threads')?.response.threads.every(t=>!t.hasSemanticMap));
 if(mode==='baseline') {
 await b.evaluate(`[...document.querySelectorAll('.thread-button')].find(e=>e.textContent.includes('1,200 turns')).click()`);
 await b.wait(`document.querySelector('.thread-header .meta')?.textContent.includes(${JSON.stringify(marker.longThread)})`);
 await b.settle();
 const first=b.requests.filter(r=>r.path==='/api/threads/'+marker.longThread&&r.response?.turns).at(-1).response;
 assert.equal(first.outline,null);assert.equal(first.window.totalTurns,1200);
 assert.equal(first.window.startIndex,0);
 const hasDecision=()=>b.evaluate(`document.querySelector('[data-testid="history-window"]').textContent.includes(${JSON.stringify(marker.queries.decision)})`);
 assert.equal(await hasDecision(),false);
 const inputs=await b.evaluate(`[...document.querySelectorAll('input')].map(e=>({type:e.type,label:e.getAttribute('aria-label'),placeholder:e.placeholder}))`);
 assert.equal(await b.evaluate("!!document.querySelector('#evidence-search-query, .evidence-discovery')"),false);
 assert(inputs.some(e=>e.label==='Find source record'&&e.type==='number'));
 assert(!inputs.some(e=>/search.*(history|evidence)|(history|evidence).*search/i.test((e.label??'')+' '+e.placeholder)));
 await b.fill('#investigation-title','Independent unfinished discovery draft');
 await b.fill('#investigation-question','Keep this question while I look for source evidence.');
 await b.settle();
 const draft=await b.evaluate("localStorage.getItem('nema.investigation-draft.v1')");
 await b.screenshot(prefix+'-baseline-first-page.png');report.screenshots.push(prefix+'-baseline-first-page.png');
 let advances=0;
 while(!await hasDecision()) {
  assert(advances<30);
  const anchor=await b.evaluate("document.querySelector('[data-testid=\"history-window\"]').dataset.anchorSeq");
  await b.clickText('Later turns');
  await b.wait(`document.querySelector('[data-testid="history-window"]').dataset.anchorSeq!==${JSON.stringify(anchor)}`);
  advances++;
 }
 await b.settle();assert.equal(advances,27);
 assert.equal(await b.evaluate("localStorage.getItem('nema.investigation-draft.v1')"),draft);
 await b.evaluate(`document.querySelector('[data-item-id="fixture-long-history-turn-1100-answer"]').scrollIntoView({block:'center'})`);
 await b.screenshot(prefix+'-baseline-paged-decision.png');report.screenshots.push(prefix+'-baseline-paged-decision.png');
 report.observations={inputs,firstWindow:first.window,pageAdvancesToDecision:advances,draft,
  explanation:'Sequential rendered-page phrase detection supplied no record number. Scripted paging is not a human search-speed measurement.'};
 assert.equal(b.requests.filter(r=>r.method==='POST').length,0);assert.deepEqual(b.exceptions,[]);
 report.checks.push('Unmapped 1200-turn history has only paging and numeric source navigation; no text-search affordance.',
  'Decision outside first page is reachable after27 next-page actions; source bytes and unsaved editor are unchanged.');
 } else if(mode==='flow') {
  await flow();
 } else {
  await reopened();
 }
 assert.deepEqual(b.exceptions,[]);
 assert(posts().every(r=>r.path==='/api/investigations'),'Only explicit canonical draft creation is allowed.');
 report.apiRequests=b.requests;report.exceptions=b.exceptions;
 await fs.writeFile(prefix+'-'+mode+'.json',JSON.stringify(report,null,2)+'\n');
 console.log(JSON.stringify({mode,checks:report.checks,requests:b.requests.length,posts:posts().length},null,2));
} catch(error) {
 await b.settle().catch(()=>{});await b.screenshot(prefix+'-'+mode+'-failure.png').catch(()=>{});
 await fs.writeFile(prefix+'-'+mode+'-failure.json',JSON.stringify({...report,error:String(error),apiRequests:b.requests,exceptions:b.exceptions},null,2)+'\n');throw error;
} finally {await b.close();}

async function shot(name,selector='.evidence-discovery') {
 await b.evaluate(`document.querySelector(${JSON.stringify(selector)}).scrollIntoView({block:'start'})`);
 const path=prefix+'-'+mode+'-'+name+'.png';await b.screenshot(path);report.screenshots.push(path);
 const dimensions=await b.evaluate(`({width:innerWidth,document:document.documentElement.scrollWidth,component:document.querySelector('.evidence-discovery').scrollWidth-document.querySelector('.evidence-discovery').clientWidth})`);
 assert(dimensions.document<=dimensions.width+1,JSON.stringify(dimensions));assert(dimensions.component<=1,JSON.stringify(dimensions));
 (report.measurements??=[]).push({name,...dimensions});
}
async function search(q) {
 const before=b.requests.length;
 await b.fill('#evidence-search-query',q);await b.clickText('Search history',pane);await b.settle();
 const request=b.requests.slice(before).find(r=>r.path==='/api/evidence/search'&&r.response?.hits);
 assert(request,'Expected real search response for '+q);assert.equal(request.status,200);
 assert.equal(request.response.scope,'displayed-history-text/v1');
 for(const hit of request.response.hits) {assert([...hit.excerpt].length<=240);assert(hit.recordSeqs.length<=256);}
 return request.response;
}
async function inspect(hit) {
 const before=b.requests.length;
 await b.clickText('Inspect source',`document.querySelector('[data-evidence-hit-id="${hit.id}"]')`);
 await b.wait(`document.querySelector('[data-inspected-evidence-hit]')?.dataset.inspectedEvidenceHit===${JSON.stringify(hit.id)}`);await b.settle();
 const request=b.requests.slice(before).find(r=>r.path==='/api/evidence/hits/'+hit.id&&r.response?.records);
 assert(request,'Expected exact source read');assert.equal(request.status,200);
 assert.deepEqual(request.response.hit,hit);assert.deepEqual(request.response.records.map(r=>r.seq),hit.recordSeqs);
 assert.deepEqual(await b.evaluate(`[...document.querySelectorAll('[data-evidence-record-seq]')].map(e=>Number(e.dataset.evidenceRecordSeq))`),hit.recordSeqs);
 return request.response;
}
async function flow() {
 await b.wait("!!document.querySelector('#evidence-search-query')");
 await b.fill('#investigation-title','Independent draft preserved during evidence discovery');
 await b.fill('#investigation-question','Do not replace this unfinished question.');await b.settle();
 const pending={id:'authored-discovery-original-save',body:'{"id":null,"title":"independent draft","question":"Unresolved authored save","selections":[]}'};
 await b.evaluate(`(()=>{const value=JSON.parse(localStorage.getItem(${JSON.stringify(draftKey)}));value.pendingRequest=${JSON.stringify(pending)};localStorage.setItem(${JSON.stringify(draftKey)},JSON.stringify(value));})()`);
 await b.reload();await b.settle();const originalDraft=await draft();assert.deepEqual(JSON.parse(originalDraft).pendingRequest,pending);
 b.page.phase='remembered-decision';
 let results=await search(marker.queries.decision);assert.equal(results.hits.length,1);
 let hit=results.hits[0];assert.deepEqual(hit.recordSeqs,[marker.expected.decision]);
 await inspect(hit);assert.equal(await draft(),originalDraft);
 assert(await b.evaluate(`[...${pane}.querySelectorAll('button')].find(e=>e.textContent.trim()==='Add these source records').disabled`));
 await b.clickText('Show in history',pane);
 await b.wait(`document.querySelector('.workspace [data-item-id="fixture-long-history-turn-1100-answer"]')?.classList.contains('highlighted')`);await b.settle();
 assert.equal(await draft(),originalDraft);
 assert(await b.evaluate("[...document.querySelectorAll('.workspace .source-select')].every(e=>e.disabled)"));
 await shot('decision-with-pending-draft');
 const decisionReads=b.requests.filter(r=>r.phase==='remembered-decision');
 report.observations.rememberedDecision={requests:decisionReads.length,responseBytes:decisionReads.reduce((n,r)=>n+(r.bodyBytes??0),0),
  searchRequests:decisionReads.filter(r=>r.path==='/api/evidence/search').length,
  sourceReads:decisionReads.filter(r=>r.path.startsWith('/api/evidence/hits/')).length,
  surroundingReads:decisionReads.filter(r=>r.path==='/api/threads/'+marker.longThread).length};
 b.page.phase='scope-and-pending-guards';
 results=await search(marker.queries.split);assert.equal(results.hits.length,1);hit=results.hits[0];
 assert.deepEqual(hit.recordSeqs,marker.expected.split);const split=await inspect(hit);
 assert(!split.records.some(r=>r.seq===marker.expected.interleaved));
 await b.evaluate("document.querySelectorAll('[data-evidence-record-seq] details').forEach(e=>e.open=true)");
 await shot('split-raw-sources');
 await b.page.rpc('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:false});await shot('mobile-split-sources');
 await b.page.rpc('Emulation.setDeviceMetricsOverride',{width:1600,height:1100,deviceScaleFactor:1,mobile:false});
 for(const q of [marker.queries.absent,...marker.excludedQueries]) assert.deepEqual((await search(q)).hits,[],'Excluded or absent query matched: '+q);
 assert.equal(await draft(),originalDraft);
 // Hold a real exact-source response, then change query and leave the aperture.
 results=await search(marker.queries.split);hit=results.hits[0];b.page.holdPath='/api/evidence/hits/'+hit.id;
 await b.clickText('Inspect source',`document.querySelector('[data-evidence-hit-id="${hit.id}"]')`);
 for(let n=0;n<100&&!b.page.held;n++)await new Promise(r=>setTimeout(r,50));assert(b.page.held);
 await b.fill('#evidence-search-query',marker.queries.absent);await b.clickText('Compare');
 await b.page.rpc('Fetch.continueRequest',{requestId:b.page.held});b.page.held=null;await b.settle();
 await b.clickText('Investigation');await b.settle();
 assert.equal(await b.evaluate("document.querySelector('[data-inspected-evidence-hit]')?.dataset.inspectedEvidenceHit??null"),null);
 assert.equal(await draft(),originalDraft);assert.equal(posts().length,0);
 report.checks.push('Remembered decision and split-delta phrase found without supplied record coordinates; exact inspector excludes interleaved record.',
  'Search/inspection/history reveal preserve original dirty editor and pending request; source Add is disabled.',
  'Absent/unknown/replaced/control/provider/hidden phrases do not match; delayed inspection cannot revive after query/aperture change.');
 report.observations.originalDraft=originalDraft;
 // Separate authored browser context leaves the original recovery entry untouched.
 await b.fresh('unmapped-history-explicit-selection');await b.settle();
 b.page.phase='explicit-selection';
 await b.fill('#investigation-title','Recovered decision from unmapped history');
 await b.fill('#investigation-question','Which recorded decision and counterexample explain why automatic retry remains unsupported?');
 const inspected=[];
 for(const q of [marker.queries.decision,marker.queries.counterexample,marker.queries.split]) {
  results=await search(q);assert.equal(results.hits.length,1);const detail=await inspect(results.hits[0]);inspected.push(...detail.records);
  await b.clickText('Add these source records',pane);await b.settle();
 }
 const expected=[marker.expected.counterexample,marker.expected.decision,...marker.expected.split].sort((a,b)=>a-b);
 const selection=JSON.parse(await draft()).selections;
 const selected=[...new Set(selection.flatMap(s=>Array.from({length:s.endSeq-s.startSeq+1},(_,i)=>s.startSeq+i)))].sort((a,b)=>a-b);
 assert.deepEqual(selected,expected);assert(!selected.includes(marker.expected.interleaved));
 await b.clickText('Show in history',pane);
 await b.wait("document.querySelector('.workspace [data-item-id=\"discovery-streamed-answer\"]')?.classList.contains('highlighted')");
 await shot('selected-disjoint-records','.source-list');
 await b.clickText('Save and preview context');await b.wait("!!document.querySelector('.context-preview')");await b.settle();
 const creation=posts().find(r=>r.path==='/api/investigations');assert(creation?.response);assert.equal(posts().length,1);
 const work=creation.response;const context=work.contexts.find(c=>c.id===work.currentContextId);assert(context);
 assert.deepEqual(context.records.map(r=>r.seq),expected);
 assert.deepEqual(context.records,[...new Map(inspected.map(r=>[r.seq,r])).values()].sort((a,b)=>a.seq-b.seq));
 assert.equal(work.attempt,null);assert.equal(work.artifact,null);assert.equal(work.adoption,null);
 await b.evaluate("document.querySelector('.context-preview .exact-input').open=true");await shot('canonical-context','.context-preview');
 const savedDraft=await draft();await b.reload();await b.settle();assert.equal(await draft(),savedDraft);
 await b.wait(`document.querySelector('.context-preview')?.textContent.includes(${JSON.stringify(context.id)})`);
 assert.equal(posts().length,1);
 report.observations.savedDraft=savedDraft;report.observations.savedInvestigation=work;report.observations.savedContext=context;
 report.checks.push('Explicit independent fresh draft saves exactly4 inspected records from2threads; no interleaved neighbor, artifact, adoption or native attempt; reload sends nothing.');
}
async function reopened() {
 const prior=JSON.parse(await fs.readFile(prefix+'-flow.json','utf8'));
 await b.evaluate(`localStorage.setItem(${JSON.stringify(draftKey)},${JSON.stringify(prior.observations.savedDraft)})`);
 await b.reload();await b.settle();
 await b.wait(`document.querySelector('.context-preview')?.textContent.includes(${JSON.stringify(prior.observations.savedContext.id)})`);
 const work=await b.evaluate(`fetch('/api/investigations/'+${JSON.stringify(prior.observations.savedInvestigation.id)}).then(r=>r.json())`);
 assert.deepEqual(work,prior.observations.savedInvestigation);assert.equal(await draft(),prior.observations.savedDraft);
 await shot('same-canonical-context','.context-preview');
 await b.fresh('unmapped-history-original-pending-reopened');await b.settle();
 await b.evaluate(`localStorage.setItem(${JSON.stringify(draftKey)},${JSON.stringify(prior.observations.originalDraft)})`);
 await b.reload();await b.settle();const results=await search(marker.queries.split);await inspect(results.hits[0]);
 await b.evaluate("document.querySelectorAll('[data-evidence-record-seq] details').forEach(e=>e.open=true)");
 await b.page.rpc('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:false});
 await shot('mobile-exact-source','.evidence-source');
 await b.page.rpc('Emulation.setDeviceMetricsOverride',{width:1600,height:1100,deviceScaleFactor:1,mobile:false});
 await shot('desktop-exact-source','.evidence-source');
 const broad=await search('Routine review');assert.equal(broad.hits.length,20);assert(broad.nextCursor);
 await b.clickText('Next matches',pane);await b.settle();
 const next=b.requests.filter(r=>r.path==='/api/evidence/search'&&r.response?.hits).at(-1).response;
 assert.equal(next.hits.length,20);assert(next.hits.every(h=>!broad.hits.some(old=>old.id===h.id)));
 await b.clickText('Previous matches',pane);await b.settle();
 assert.deepEqual(b.requests.filter(r=>r.path==='/api/evidence/search'&&r.response?.hits).at(-1).response.hits,broad.hits);
 await b.select('#evidence-search-thread',marker.longThread);
 assert.deepEqual((await search(marker.queries.split)).hits,[]);
 await b.select('#evidence-search-thread','');assert.equal((await search(marker.queries.split)).hits.length,1);
 assert.equal(await draft(),prior.observations.originalDraft);assert.equal(posts().length,0);
 report.checks.push('After actual API restart, explicitly restored authored browser snapshots resolve same canonical context and original pending draft; zeroPOST.');
 report.checks.push('Actual 20-hit next/previous pages and exact thread filter preserve pending editor; desktop/mobile exact source inspection remains readable.');
 report.observations={restoration:'Explicit authored restoration into isolated browser contexts.',savedContext:prior.observations.savedContext};
}
