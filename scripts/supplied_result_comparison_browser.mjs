// Actual UI acceptance over the explicitly marked public/authored fixture.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {browserAcceptance} from './browser_acceptance_support.mjs';
const marker=JSON.parse(await fs.readFile(process.env.NEMA_COMPARISON_MARKER,'utf8'));
assert.equal(marker.schemaVersion,'supplied-result-comparison/v1');
assert.equal(marker.nativeOrModelCalls,0);
const mode=process.env.NEMA_COMPARISON_MODE??'flow';
const prefix=process.env.NEMA_UI_EVIDENCE_PREFIX??'/tmp/nema-supplied-result-comparison-browser-20261014';
const origin=process.env.NEMA_UI_ORIGIN??'http://127.0.0.1:5173',debug=process.env.NEMA_UI_DEBUG??'http://127.0.0.1:9233';
for(const address of[origin,debug]){const u=new URL(address);assert(u.protocol==='http:'&&['127.0.0.1','localhost','[::1]'].includes(u.hostname));}
const b=await browserAcceptance({origin,debug});
const report={mode,classification:marker.classification,checks:[],screenshots:[],observations:{}};
const posts=()=>b.requests.filter(r=>r.method==='POST');
const keys=['nema.investigation-draft.v1','nema.authored-finding.v1','nema.history-import.v1','nema.supplied-text.v1','nema.source-focus.v1'];
const expected={left:{investigationId:marker.sourceOwner,contextId:marker.F0.contextId,artifactId:marker.F0.id},right:{investigationId:marker.consumerOwner,contextId:marker.R0.contextId,artifactId:marker.R0.id},lens:'result',layout:'beside'};
const action=(result,input)=>`[data-result-artifact-id="${result.id}"] [data-compare-supplied-artifact="${input.id}"]`;
async function guards(){return b.evaluate(`Object.fromEntries(${JSON.stringify(keys)}.map(k=>[k,localStorage.getItem(k)]))`);}
async function fresh(name){await b.fresh('supplied-comparison-'+name);await b.settle();}
async function owner(id){
 const value=marker.owners[id];assert(value);
 await b.fill('#saved-investigation-search',value.title);await b.clickText('Search',"document.querySelector('#saved-investigation').closest('.catalog-picker')");await b.settle();
 await b.select('#saved-investigation',id);await b.settle();
}
async function shot(name,selector){
 if(selector)await b.evaluate(`document.querySelector(${JSON.stringify(selector)}).scrollIntoView({block:'start'})`);
 const path=prefix+'-'+mode+'-'+name+'.png';await b.screenshot(path);report.screenshots.push(path);
 const size=await b.evaluate('({width:innerWidth,scroll:document.documentElement.scrollWidth})');assert(size.scroll<=size.width+1,JSON.stringify(size));
}
async function draft(){return b.evaluate(`Object.fromEntries(['left','right'].map(side=>[side,{investigationId:document.querySelector('#compare-'+side).value,contextId:document.querySelector('#compare-'+side+'-context').value,artifactId:document.querySelector('#compare-'+side+'-artifact').value}]))`);}
async function reviewed(target=expected){
 await b.wait("!!document.querySelector('[data-supplied-result-review=\"true\"]')");await b.settle();
 assert.deepEqual(await draft(),{left:target.left,right:target.right});
}
async function apply(target=expected){
 await b.clickText('Apply arrangement',"document.querySelector('.arrangement-editor')");await b.settle();
 assert.deepEqual((await b.local('nema.composition.v1')).arrangement,target);
 for(const side of['left','right'])assert.equal(await b.evaluate(`document.querySelector('[data-aperture="${side}"]').dataset.artifactId`),target[side].artifactId);
}
async function seedIndependent(){
 await b.fill('#investigation-question','Independent dirty question; preserve the selected historical finding and every pending identity.');await b.settle();
 await b.evaluate(`(()=>{
  const key='nema.investigation-draft.v1',draft=JSON.parse(localStorage.getItem(key));draft.pendingRequest={id:'independent-comparison-save',body:JSON.stringify({requestId:'independent-comparison-save',question:'Keep the exact pending editor request.'})};localStorage.setItem(key,JSON.stringify(draft));
  localStorage.setItem('nema.authored-finding.v1',JSON.stringify({version:1,source:{investigationId:'investigation_independent',contextId:'context_independent',title:'Independent finding',question:'Preserve this pending finding'},text:null,request:JSON.stringify({requestId:'independent-comparison-finding',contextId:'context_independent',text:'Unfinished unrelated finding.'}),savedId:null}));
  localStorage.setItem('nema.history-import.v1',JSON.stringify({requestId:'independent-comparison-import',format:'appserver-jsonl/v1',source:'authored-independent',direction:'appserver_to_client',fileName:'independent.jsonl',fileSha256:'1'.repeat(64),byteLength:17,previewFingerprint:'2'.repeat(64),operationFingerprint:'3'.repeat(64)}));
 })()`);
 await b.reload();await b.settle();return guards();
}
async function flow(){
 await owner(marker.consumerOwner);
 assert.notEqual(marker.owners[marker.consumerOwner].currentContextId,marker.R0.contextId);
 assert.notEqual(marker.owners[marker.sourceOwner].currentContextId,marker.F0.contextId);
 const independent=await seedIndependent(),before=await b.local('nema.composition.v1');
 assert.equal(await b.evaluate("!!document.querySelector('.recorded-experiments')"),false);
 b.page.phase='stage-historical';await b.click(action(marker.R0,marker.F0));await reviewed();
 assert.deepEqual(await guards(),independent);assert.deepEqual((await b.local('nema.composition.v1')).arrangement,before?.arrangement??null);assert.equal(posts().length,0);
 assert.equal(await b.evaluate("document.querySelector('.synthetic-examples').open"),false);
 await shot('review-historical-pair','[data-supplied-result-review]');
 await apply();await shot('exact-historical-results','.comparison-apertures');
 await b.fill('#composition-title','Exact review and supplied basis');b.page.phase='save-comparison';await b.click('#save-comparison');await b.settle();
 const saved=posts().find(r=>r.phase==='save-comparison');assert.equal(saved?.status,201);const composition=saved.response.composition;
 assert.deepEqual(composition.arrangement,expected);assert.deepEqual(await guards(),independent);
 await b.page.rpc('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:false});await shot('narrow-exact-results','.comparison-apertures');
 report.observations={composition,independent,expected};report.checks.push('Historical R0 stages exact supplied F0 despite both owners advancing; review precedes Apply, only composition save POSTs, independent pending/editor/focus state remains exact.');
}
async function failure(){
 await owner(marker.consumerOwner);await b.clickText('Compare saved work',"document.querySelector('.work-picker')");await b.settle();
 await b.clickText('Review arrangement',"document.querySelector('.arrangement-editor')");
 const prior=await draft(),arranged=(await b.local('nema.composition.v1')).arrangement;
 await b.clickText('Return to investigation',"document.querySelector('.composition-actions')");
 const independent=await guards();
 b.page.failPath=`/api/investigations/${marker.sourceOwner}/artifacts/${marker.F0.id}/source`;
 await b.click(action(marker.R0,marker.F0));await b.settle();await b.wait("!!document.querySelector('[data-supplied-comparison-error]')");
 assert.deepEqual(await draft(),prior);assert.deepEqual((await b.local('nema.composition.v1')).arrangement,arranged);assert.deepEqual(await guards(),independent);
 await shot('failed-read-retains-proposal','[data-supplied-comparison-error]');
 await b.clickText('Retry exact comparison',"document.querySelector('[data-supplied-comparison-error]')");await reviewed();assert.deepEqual(await guards(),independent);
 assert.equal(posts().length,0);report.checks.push('Failed exact source read retains the previous unapplied draft and arrangement; typed retry stages the intended pair with zero POSTs.');
}
async function cancel(){
 await owner(marker.consumerOwner);const independent=await guards(),before=await b.local('nema.composition.v1');
 b.page.holdPath=`/api/investigations/${marker.sourceOwner}/artifacts/${marker.F0.id}/source`;
 await b.click(action(marker.R0,marker.F0));for(let n=0;n<100&&!b.page.held;n++)await new Promise(r=>setTimeout(r,50));assert(b.page.held);
 await b.clickText('Return to investigation',"document.querySelector('.composition-actions')");
 const held=b.page.held;b.page.held=null;let delivery;
 try{await b.page.rpc('Fetch.continueRequest',{requestId:held});delivery='released-after-close';}catch(error){if(!String(error).includes('Invalid InterceptionId'))throw error;delivery='browser-aborted-before-release';}
 await b.settle();assert.deepEqual(await guards(),independent);assert.deepEqual((await b.local('nema.composition.v1')).arrangement,before?.arrangement??null);
 assert.equal(await b.evaluate("document.querySelector('.comparison-surface').classList.contains('hidden-aperture')"),true);
 assert.equal(posts().length,0);report.observations={delivery};report.checks.push('Closing while exact source read is held preserves editor/focus and previous arrangement; release/cancellation outcome is recorded.');
}
async function sameOwner(){
 await owner(marker.sameOwner);await b.click(action(marker.A1,marker.A0));
 const target={left:{investigationId:marker.sameOwner,contextId:marker.A0.contextId,artifactId:marker.A0.id},right:{investigationId:marker.sameOwner,contextId:marker.A1.contextId,artifactId:marker.A1.id},lens:'result',layout:'beside'};
 await reviewed(target);await apply(target);assert.equal(posts().length,0);await shot('same-owner-exact-pair','.comparison-apertures');
 report.checks.push('Two exact results within one owner retain their distinct context and artifact pins.');
}
async function interrupted(){
 const saved=JSON.parse(await fs.readFile(prefix+'-flow.json','utf8')).observations.composition;
 const outcomes=[];
 for(const kind of['manual-edit','saved-open','new-result']){
  await fresh(kind);await owner(marker.consumerOwner);
  if(kind==='manual-edit'){
   await b.clickText('Compare saved work',"document.querySelector('.work-picker')");await b.settle();
   await b.clickText('Return to investigation',"document.querySelector('.composition-actions')");
  }
  const independent=await guards();
  const result=kind==='saved-open'?marker.R1:marker.R0,input=kind==='saved-open'?marker.F1:marker.F0;
  b.page.holdPath=`/api/investigations/${marker.sourceOwner}/artifacts/${input.id}/source`;
  await b.click(action(result,input));for(let n=0;n<100&&!b.page.held;n++)await new Promise(r=>setTimeout(r,50));assert(b.page.held);
  let retained;
  if(kind==='manual-edit'){
   await b.clickText('Edit arrangement',"document.querySelector('.composition-actions')");
   await b.select('#compare-left-context',marker.R0.contextId);await b.select('#compare-left-artifact',marker.R0.id);retained=await draft();
  }else if(kind==='saved-open'){
   await b.evaluate("document.querySelector('#saved-comparisons-browser').open=true");await b.select('#saved-composition',saved.id);
   await b.click('#preview-comparison');await b.click('#open-comparison');
   await b.wait(`document.querySelector('[data-aperture="left"]')?.dataset.artifactId===${JSON.stringify(marker.F0.id)}`);
  }else{
   await b.clickText('Return to investigation',"document.querySelector('.composition-actions')");
   await b.click(action(marker.R1,marker.F1));
   await b.wait("!!document.querySelector('[data-supplied-result-review=\"true\"]')");
   retained={left:{investigationId:marker.sourceOwner,contextId:marker.F1.contextId,artifactId:marker.F1.id},right:{investigationId:marker.consumerOwner,contextId:marker.R1.contextId,artifactId:marker.R1.id}};
  }
  const held=b.page.held;b.page.held=null;let delivery;
  try{await b.page.rpc('Fetch.continueRequest',{requestId:held});delivery='released-after-interruption';}catch(error){if(!String(error).includes('Invalid InterceptionId'))throw error;delivery='browser-aborted-before-release';}
  await b.settle();assert.deepEqual(await guards(),independent);
  if(kind==='saved-open'){assert.deepEqual((await b.local('nema.composition.v1')).arrangement,expected);assert.equal(await b.evaluate("!!document.querySelector('[data-supplied-result-review=\"true\"]')"),false);}
  else assert.deepEqual(await draft(),retained);
  outcomes.push({kind,delivery});
 }
 assert.equal(posts().length,0);report.observations={outcomes};report.checks.push('Actual manual binding edit, saved-comparison Open and a newer displayed-result request each supersede a held read without stale proposal replacement.');
}
async function reopened(){
 const prior=JSON.parse(await fs.readFile(prefix+'-flow.json','utf8')).observations;
 await b.clickText('Compare',"document.querySelector('.thread-rail')");await b.settle();
 await b.evaluate("document.querySelector('#saved-comparisons-browser').open=true");await b.settle();await b.select('#saved-composition',prior.composition.id);
 await b.click('#preview-comparison');await b.settle();await b.click('#open-comparison');await b.settle();
 assert.deepEqual((await b.local('nema.composition.v1')).arrangement,expected);
 for(const side of['left','right'])assert.equal(await b.evaluate(`document.querySelector('[data-aperture="${side}"]').dataset.artifactId`),expected[side].artifactId);
 assert.equal(posts().length,0);await shot('reopened-exact-pair','.comparison-apertures');report.checks.push('Fresh browser after API restart opens the exact saved F0/R0 comparison with zero POSTs.');
}
async function presentation(){
 await reopened();
 assert.equal(await b.evaluate("document.querySelector('[data-aperture=left]').getAttribute('aria-label')"),'A / Supplied result');
 assert.equal(await b.evaluate("document.querySelector('[data-aperture=right]').getAttribute('aria-label')"),'B / Result using this input');
 await shot('supplied-relationship-desktop','.comparison-apertures');
 await b.page.rpc('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:false});
 await shot('supplied-relationship-narrow','.comparison-apertures');
 assert.equal(posts().length,0);report.checks.push('Saved exact supplied-input relationship derives accurate labels at desktop and narrow widths without new persistence or intent.');
}
async function recoveryPanels(){
 await owner(marker.consumerOwner);
 assert.equal(await b.evaluate("!!document.querySelector('.recorded-experiments')"),false);
 const key='nema.experiment-request.v1.'+marker.consumerOwner,path='/api/investigations/'+marker.consumerOwner+'/experiments';
 const pending=JSON.stringify({path,body:{requestId:'authored-recovery-canary',rationale:'Retain this exact unknown request; do not send it automatically.'}});
 await b.evaluate(`localStorage.setItem(${JSON.stringify(key)},${JSON.stringify(pending)})`);b.page.failPath=path;
 await b.reload();await b.settle();
 assert.equal(await b.evaluate(`localStorage.getItem(${JSON.stringify(key)})`),pending);
 const text=await b.evaluate("document.querySelector('.recorded-experiments').textContent");
 assert.match(text,/Retry saved experiment action/);assert.match(text,/Synthetic one-shot read failure/);assert.doesNotMatch(text,/Respond to a specialist inquiry/);
 await shot('pending-experiment-still-visible','.recorded-experiments');
 await b.evaluate(`localStorage.removeItem(${JSON.stringify(key)})`);await b.reload();await b.settle();
 assert.equal(await b.evaluate("!!document.querySelector('.recorded-experiments')"),false);
 await b.clickText('Compare',"document.querySelector('.thread-rail')");await b.settle();
 await b.evaluate("document.querySelector('.synthetic-examples').open=true");
 await b.clickText('Open synthetic inquiry & experiment',"document.querySelector('.synthetic-examples')");await b.settle();
 await b.clickText('Apply arrangement',"document.querySelector('.arrangement-editor')");await b.settle();
 await b.click('#arrange-alternative');await b.clickText('Apply arrangement',"document.querySelector('.arrangement-editor')");await b.settle();
 const fixture=(await b.local('nema.composition.v1')).arrangement;
 assert(fixture.experimentId.startsWith('fixture:'));
 await b.reload();await b.settle();assert.deepEqual((await b.local('nema.composition.v1')).arrangement,fixture);
 assert.equal(await b.evaluate("!!document.querySelector('.experiment-heading[data-experiment-id]')"),true);
 await shot('synthetic-example-reopened','.experiment-heading');assert.equal(posts().length,0);
 report.checks.push('Authored-only clean experiment panel hides, pending retry plus load error remain visible without resend, and explicit synthetic example/named alternative remain available and reopen after reload.');
}
async function legacy(){
 const fixture=JSON.parse(await fs.readFile(process.env.NEMA_RECORDED_MARKER,'utf8'));
 assert.equal(fixture.schemaVersion,'synthetic-recorded-experiment/v1');assert.equal(fixture.nativeOrModelCalls,0);
 const work=await b.evaluate(`fetch('/api/investigations/'+${JSON.stringify(fixture.owner)}).then(r=>r.json())`);
 await b.fill('#saved-investigation-search',work.title);await b.clickText('Search',"document.querySelector('#saved-investigation').closest('.catalog-picker')");await b.settle();
 await b.select('#saved-investigation',work.id);await b.settle();
 for(const value of Object.values(fixture.experiments))assert.equal(await b.evaluate(`!!document.querySelector('[data-experiment-id="${value.id}"]')`),true);
 await shot('recorded-experiments-retained','.recorded-experiments');
 const baseline=work.artifactHistory.find(a=>a.id===fixture.artifacts.A1),context=work.contexts.find(c=>c.id===baseline.contextId),input=context.artifactInputs[0];
 assert.equal(input.sourceAdoption,null);
 const source=await b.evaluate(`fetch('/api/investigations/'+${JSON.stringify(input.investigationId)}).then(r=>r.json())`);assert.equal(source.adoption.decision,'reject');
 const selector=action(baseline,input.artifact);
 await b.evaluate(`(()=>{for(let e=document.querySelector(${JSON.stringify(selector)});e;e=e.parentElement)if(e.tagName==='DETAILS')e.open=true;})()`);
 await b.click(selector);
 const target={left:{investigationId:input.investigationId,contextId:input.sourceContextId,artifactId:input.artifactId},right:{investigationId:work.id,contextId:context.id,artifactId:baseline.id},lens:'result',layout:'beside'};
 await reviewed(target);await apply(target);await shot('native-source-review-difference','.comparison-apertures');assert.equal(posts().length,0);
 report.checks.push('Existing recorded experiments remain visible; historical synthetic native result compares its exact input despite later source adoption metadata, without changing native eligibility.');
}
try{
 await fresh(mode);
 if(mode==='flow')await flow();else if(mode==='failure')await failure();else if(mode==='cancel')await cancel();else if(mode==='same-owner')await sameOwner();else if(mode==='interrupted')await interrupted();else if(mode==='reopened')await reopened();else if(mode==='presentation')await presentation();else if(mode==='recovery-panels')await recoveryPanels();else if(mode==='legacy')await legacy();else throw Error('Unknown mode');
 assert.deepEqual(b.exceptions,[]);report.requests=b.requests;report.exceptions=b.exceptions;
 await fs.writeFile(prefix+'-'+mode+'.json',JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify({mode,requests:b.requests.length,posts:posts().length,checks:report.checks}));
}catch(error){report.error=String(error?.stack??error);report.requests=b.requests;await b.screenshot(prefix+'-'+mode+'-failure.png').catch(()=>{});await fs.writeFile(prefix+'-'+mode+'-failure.json',JSON.stringify(report,null,2)+'\n');throw error;}finally{await b.close();}
