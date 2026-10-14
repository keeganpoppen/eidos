// Actual browser acceptance for scripts/managed_attempt_demo.py, using authored
// subprocesses only. Seed a fresh demo/marker, serve it on :8767, and point Vite's
// /api proxy there. Start isolated Chromium CDP on :9231. Example:
// NEMA_MANAGED_ATTEMPT_MARKER=/tmp/managed-demo.json NEMA_UI_ORIGIN=http://127.0.0.1:5173 \
// NEMA_UI_DEBUG=http://127.0.0.1:9231 NEMA_UI_EVIDENCE_PREFIX=/tmp/managed-ui \
// bun scripts/managed_attempt_browser.mjs
// Then restart only the fixture API, retaining the same database, and rerun with
// NEMA_MANAGED_ATTEMPT_MODE=reopened and the same output prefix. Reopened mode is
// read-only. Flow dispatches the two seeded cases, cancels one, and writes/removes
// only each authored fixture's release-login file. The sign-in link is inspected,
// never followed. No actual native/auth/model/DNS/upstream call.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import { browserAcceptance } from './browser_acceptance_support.mjs';

const markerPath=process.env.NEMA_MANAGED_ATTEMPT_MARKER;
assert(markerPath,'Set NEMA_MANAGED_ATTEMPT_MARKER to the authored fixture marker.');
const marker=JSON.parse(await fs.readFile(markerPath,'utf8'));
assert.equal(marker.schemaVersion,'synthetic-owned-attempt-demo/v1');
assert.equal(marker.classification,'authored-managed-preparation-fixture');
assert.equal(marker.nativeOrModelCalls,0);
assert(path.isAbsolute(marker.fixtureDirectory));
const mode=process.env.NEMA_MANAGED_ATTEMPT_MODE ?? 'flow';
assert(['flow','reopened'].includes(mode));
const prefix=process.env.NEMA_UI_EVIDENCE_PREFIX ?? '/tmp/nema-managed-attempt-browser';
const origin=process.env.NEMA_UI_ORIGIN ?? 'http://127.0.0.1:5173';
const debug=process.env.NEMA_UI_DEBUG ?? 'http://127.0.0.1:9231';
for(const address of [origin,debug]) {
 const url=new URL(address);
 assert(url.protocol==='http:' && ['localhost','127.0.0.1','[::1]'].includes(url.hostname));
}
const directories=async()=>{try{return (await fs.readdir(marker.fixtureDirectory,{withFileTypes:true})).filter(e=>e.isDirectory()&&e.name.startsWith('nema-investigation-')).map(e=>path.join(marker.fixtureDirectory,e.name)).sort();}catch(error){if(error.code==='ENOENT')return [];throw error;}};
const optionalText=async (directory,name)=>{try{return await fs.readFile(path.join(directory,name),'utf8');}catch(error){if(error.code==='ENOENT')return '';throw error;}};
const requestsIn=async directory=>(await optionalText(directory,'requests.jsonl')).trim().split('\n').filter(Boolean).map(line=>JSON.parse(line));
const nativeRequests=async()=> (await Promise.all((await directories()).map(requestsIn))).flat();
const launches=async()=> (await Promise.all((await directories()).map(async directory=>(await optionalText(directory,'launches')).trim().split('\n').filter(Boolean).length))).reduce((a,b)=>a+b,0);
const newDirectory=async previous=>{for(let n=0;n<100;n++){const added=(await directories()).filter(d=>!previous.includes(d));if(added.length){assert.equal(added.length,1);return added[0];}await new Promise(r=>setTimeout(r,20));}throw Error('Authored launch directory absent');};
const b=await browserAcceptance({origin,debug});
const checks=[],screenshots=[],measurements=[],networkUrls=[];
const stateRoot="document.querySelector('.investigation-state')";
const controlRoot="document.querySelector('.attempt-control')";
const button=label=>`[...${controlRoot}?.querySelectorAll('button')??[]].find(e=>e.textContent.trim()===${JSON.stringify(label)}&&!e.disabled)`;
const owner=which=>marker.investigations[which].investigationId;
const posts=()=>b.requests.filter(request=>request.method==='POST');
const fullView=which=>b.requests.findLast(request=>request.path===`/api/investigations/${owner(which)}/view`&&request.response?.investigation)?.response.investigation;
const controlPath=(which,attempt)=>`/api/investigations/${owner(which)}/attempts/${attempt}/control`;
async function select(which){await b.select('#saved-investigation',owner(which));await b.wait(`${stateRoot}?.textContent.includes(${JSON.stringify(owner(which))})`);await b.settle();}
async function shot(name,selector='.investigation-state'){
 await b.evaluate(`document.querySelector(${JSON.stringify(selector)}).scrollIntoView({block:'start'})`);
 const file=`${prefix}-${mode}-${name}.png`;await b.screenshot(file);screenshots.push(file);
 const size=await b.evaluate('({width:innerWidth,document:document.documentElement.scrollWidth,body:document.body.scrollWidth})');
 assert(size.document<=size.width+1,JSON.stringify(size));
 if(name.startsWith('mobile'))assert.equal(size.width,390);
 measurements.push({name,...size});
}
async function held(which){
 await b.wait(`${controlRoot}?.textContent.includes('Awaiting sign-in') && !!(${button('Stop this attempt')}) && !!document.querySelector('.attempt-sign-in')`);
 await b.settle();const current=fullView(which);
 assert(current?.attempt);assert.equal(current.currentContextId,marker.investigations[which].contextId);
 assert.equal(current.attempt.contextId,current.currentContextId);
 assert.equal(current.attempt.lifecycle.phase,'awaiting-sign-in');
 assert(!JSON.stringify(current).includes('PRIVATE_'));
 const control=b.requests.findLast(request=>request.path===controlPath(which,current.attempt.id)&&request.response?.signIn)?.response;
 assert.equal(control?.attemptId,current.attempt.id);assert.equal(control.owned,true);assert.equal(control.canCancel,true);
 assert.equal(control.signIn.verificationUrl,'https://auth.openai.com/codex/device');assert.equal(control.signIn.userCode,'NEMA-FIXTURE');
 assert(control.signIn.expiresAtMs>Date.now()&&control.signIn.expiresAtMs<=Date.now()+180001);
 const rendered=await b.evaluate(`(()=>{const s=document.querySelector('.attempt-sign-in'),a=s.querySelector('a');return {attempt:s.dataset.attemptSignIn,code:s.querySelector('code').textContent,url:a.href,target:a.target,rel:a.rel,deadline:s.querySelector('time').dateTime};})()`);
 assert.equal(rendered.attempt,current.attempt.id);assert.equal(rendered.code,control.signIn.userCode);
 assert.equal(rendered.url,control.signIn.verificationUrl);assert.equal(rendered.target,'_blank');
 assert(rendered.rel.includes('noopener')&&rendered.rel.includes('noreferrer'));
 assert.equal(Date.parse(rendered.deadline),control.signIn.expiresAtMs);
 await assertNoStoredChallenge();
 return current;
}
async function assertNoStoredChallenge(){
 const storage=await b.evaluate('JSON.stringify({local:{...localStorage},session:{...sessionStorage}})');
 for(const forbidden of ['NEMA-FIXTURE','auth.openai.com/codex/device','PRIVATE_','fixture@example.invalid'])assert(!storage.includes(forbidden),`Storage retained ${forbidden}`);
}
async function assertCleanResponses(){
 await b.settle();
 assert.deepEqual(b.exceptions,[]);
 for(const request of b.requests){
   if(request.response!==undefined){
     const expectedStatus=request.method==='POST'&&request.path.endsWith('/dispatch')?202:200;
     assert.equal(request.status,expectedStatus,`${request.method} ${request.path}`);
     assert(!JSON.stringify(request.response).includes('PRIVATE_'));
     assert(!JSON.stringify(request.response).includes('https://fixture.invalid'));
     assert(!JSON.stringify(request.response).includes('fixture@example.invalid'));
     if(!request.path.endsWith('/control')) {
       assert(!JSON.stringify(request.response).includes('NEMA-FIXTURE'));
       assert(!JSON.stringify(request.response).includes('auth.openai.com/codex/device'));
     }
   }
 }
 assert(!(await b.evaluate('document.body.textContent')).includes('PRIVATE_'));
 await assertNoStoredChallenge();
 assert(networkUrls.every(url=>new URL(url).origin===new URL(origin).origin),JSON.stringify(networkUrls));
}
try {
 await b.fresh(`managed-attempt-${mode}`);
 const forward=b.page.event;b.page.event=message=>{if(message.method==='Network.requestWillBeSent')networkUrls.push(message.params.request.url);forward(message);};
 await b.settle();
 const capabilities=b.requests.find(request=>request.path==='/api/investigations/capabilities')?.response;
 assert.equal(capabilities?.nativeExecution.mode,'synthetic');
 assert.equal(capabilities.nativeExecution.available,true);
 let observations;
 if(mode==='flow') {
   assert.equal(await launches(),0,'Use a newly seeded fixture for flow mode.');
   assert.equal((await nativeRequests()).length,0);
   const directoriesBeforeA=await directories();
   await select('cancel');assert.equal(fullView('cancel').status,'draft');
   await b.clickText('Start specialist with this context');
   await b.settle();assert.equal(posts().at(-1)?.status,202,JSON.stringify(posts().at(-1)));
   const initial=await held('cancel'),attempt=initial.attempt.id;
   const directoryA=await newDirectory(directoriesBeforeA);
   await shot('held');
   await b.page.rpc('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:false});
   await shot('mobile-held','.attempt-sign-in');
   const reachable=await b.evaluate(`(()=>{const a=document.querySelector('.attempt-sign-in a'),r=a.getBoundingClientRect(),p=document.elementFromPoint(r.left+r.width/2,r.top+r.height/2);return {left:r.left,right:r.right,visible:p===a||a.contains(p)};})()`);
   assert(reachable.visible&&reachable.left>=0&&reachable.right<=390,JSON.stringify(reachable));
   await b.page.rpc('Emulation.setDeviceMetricsOverride',{width:1600,height:1100,deviceScaleFactor:1,mobile:false});
   const draftQuestion='Authored unsent draft: keep this question separate from the pinned C0.';
   await b.fill('#investigation-question',draftQuestion);
   await b.fill('[aria-label="Why include source 1"]','Authored unsent rationale.');
   await b.wait(`JSON.parse(localStorage.getItem('nema.investigation-draft.v1')).question===${JSON.stringify(draftQuestion)}`);
   const pendingSave={id:'authored-pending-save',body:'{"id":null,"title":"Authored unsent save"}'};
   await b.evaluate(`(()=>{const draft=JSON.parse(localStorage.getItem('nema.investigation-draft.v1'));draft.pendingRequest=${JSON.stringify(pendingSave)};localStorage.setItem('nema.investigation-draft.v1',JSON.stringify(draft));})()`);
   const draftBefore=await b.local('nema.investigation-draft.v1');
   const readsBeforeNavigation=b.requests.length;
   await b.clickText('Compare',"document.querySelector('.aperture-switch')");
   await b.wait("!document.querySelector('.attempt-sign-in')");
   assert.deepEqual(await b.local('nema.investigation-draft.v1'),draftBefore);
   await b.clickText('Investigation',"document.querySelector('.aperture-switch')");
   await held('cancel');
   assert(b.requests.slice(readsBeforeNavigation).some(request=>request.path===controlPath('cancel',attempt)));
   assert.deepEqual(await b.local('nema.investigation-draft.v1'),draftBefore);
   const postsBeforeReload=posts().length;await b.reload();await held('cancel');
   assert.equal(posts().length,postsBeforeReload);
   assert.deepEqual(await b.local('nema.investigation-draft.v1'),draftBefore);
   checks.push('held preparation survives reload with exact C0/attempt, dirty fields and authored pending-save identity');

   const cancellationPath=controlPath('cancel',attempt);
   b.page.losePost=cancellationPath;
   await b.clickText('Stop this attempt',controlRoot);
   await b.wait(`!!(${button('Retry stopping this attempt')})`);
   assert.equal(await b.evaluate("!!document.querySelector('.attempt-sign-in')"),false);
   assert(b.page.lost.some(request=>request.path===cancellationPath&&request.committedStatus===200));
   const retryKey=`nema.attempt-stop.v1.${JSON.stringify([owner('cancel'),attempt])}`;
   const expectedRetry={version:1,investigationId:owner('cancel'),attemptId:attempt,action:'cancel'};
   assert.deepEqual(await b.local(retryKey),expectedRetry);
   assert.deepEqual(await b.local('nema.investigation-draft.v1'),draftBefore);
   await shot('lost-reply');
   const postCount=posts().length;await b.reload();await b.wait(`!!(${button('Retry stopping this attempt')})`);await b.settle();
   assert.equal(posts().length,postCount);assert.deepEqual(await b.local(retryKey),expectedRetry);
   assert.deepEqual(await b.local('nema.investigation-draft.v1'),draftBefore);
   await b.clickText('Retry stopping this attempt',controlRoot);
   await b.wait(`localStorage.getItem(${JSON.stringify(retryKey)})===null`);
   await b.settle();
   const stopPosts=posts().filter(request=>request.path===cancellationPath);
   assert.equal(stopPosts.length,2);assert(stopPosts.every(request=>request.body==='{"action":"cancel"}'));
   assert.equal(await b.evaluate(`!!(${button('Stop this attempt')})`),false);
   assert.deepEqual(await b.local('nema.investigation-draft.v1'),draftBefore);
   checks.push('real committed stop reply is lost, reload sends nothing, retry stays on the same attempt and preserves the draft');

   const beforeLateRelease=await nativeRequests();
   assert(!beforeLateRelease.some(request=>['thread/start','turn/start'].includes(request.method)));
   await fs.writeFile(path.join(directoryA,'release-login'),'authored late completion\n');
   await new Promise(resolve=>setTimeout(resolve,200));
   assert.deepEqual(await nativeRequests(),beforeLateRelease);
   assert.equal(await launches(),1);
   await fs.unlink(path.join(directoryA,'release-login'));
   await b.wait(`${controlRoot}?.textContent.includes('Closed locally')`);
   await shot('cancelled');
   checks.push('release after cancelled preparation creates no thread/start or turn/start and no new launch');

   const directoriesBeforeB=await directories();
   await select('release');assert.equal(fullView('release').status,'draft');
   await b.clickText('Start specialist with this context');
   await b.settle();assert.equal(posts().at(-1)?.status,202,JSON.stringify(posts().at(-1)));
   const second=await held('release');assert.notEqual(second.attempt.id,attempt);
   const directoryB=await newDirectory(directoriesBeforeB);assert.notEqual(directoryB,directoryA);
   await shot('second-held');
   assert.equal(await b.evaluate("document.querySelector('.attempt-sign-in').dataset.attemptSignIn"),second.attempt.id);
   assert.equal(await launches(),2);
   await fs.writeFile(path.join(directoryB,'release-login'),'authored successful preparation\n');
   await b.wait("!!document.querySelector('.investigation-result') && document.querySelector('.investigation-state')?.textContent.includes('completed')");
   await b.wait(`${controlRoot}?.textContent.includes('Closed locally')`);await b.settle();
   const completed=fullView('release');
   assert.equal(completed.status,'completed');assert.equal(completed.attempt.id,second.attempt.id);
   assert.equal(completed.currentContextId,second.currentContextId);assert.equal(completed.artifact.contextId,second.currentContextId);
   assert.equal(completed.artifact.executionEvidence,'synthetic');
   assert.equal(completed.artifact.outputEvidence.kind,'private-capsule-publication');
   assert.equal(await b.evaluate("!!document.querySelector('.attempt-sign-in')"),false);
   const recorded=await nativeRequests(),turns=recorded.filter(request=>request.method==='turn/start');
   assert.equal(recorded.filter(request=>request.method==='thread/start').length,1);assert.equal(turns.length,1);
   const c0=second.contexts.find(context=>context.id===second.currentContextId);
   assert.deepEqual(turns[0].params.input,[{type:'text',text:c0.projectedPrompt}]);
   assert(!turns[0].params.input[0].text.includes(draftQuestion));
   assert.equal(await b.evaluate(`!!(${button('Stop this attempt')})`),false);
   await shot('completed');
   await b.page.rpc('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:false});
   await shot('mobile-completed');
   await b.reload();await b.wait(`document.querySelector('.investigation-result')?.dataset.resultArtifactId===${JSON.stringify(completed.artifact.id)}`);await b.settle();
   assert.equal(fullView('release').attempt.id,second.attempt.id);
   assert.equal(fullView('release').artifact.id,completed.artifact.id);
   assert.equal(await launches(),2);
   checks.push('separate preparation completes one authored turn using exact C0; publication and identities survive reload');
   assert.equal(posts().length,4);assert(posts().filter(request=>request.path.endsWith('/dispatch')).every(request=>JSON.parse(request.body).contextId===marker.investigations[request.path.includes(owner('cancel'))?'cancel':'release'].contextId));
   await assertCleanResponses();
   assert.equal(b.requests.filter(request=>request.response===undefined).length,1,'Only the deliberately lost cancel reply may lack a captured JSON body.');
   observations={initial,second,completed,directoryA,directoryB,draftBefore,pendingSave,expectedRetry,lateReleaseRequests:beforeLateRelease,finalNativeRequests:recorded,launches:2,lostCancelReplies:b.page.lost};
 } else {
   const prior=JSON.parse(await fs.readFile(`${prefix}-flow.json`,'utf8'));
   assert.deepEqual(prior.marker,marker);
   const previousRequests=await nativeRequests(),previousLaunches=await launches();
   for(const which of ['cancel','release']) {
     await select(which);
     const value=fullView(which),expected=which==='cancel'?prior.observations.initial:prior.observations.completed;
     assert.equal(value.attempt.id,expected.attempt.id);assert.equal(value.currentContextId,expected.currentContextId);
     await b.wait(`${controlRoot}?.textContent.includes('Live control is unavailable in this app.')`);
     assert.equal(await b.evaluate(`!!(${button('Stop this attempt')})`),false);
     const state=b.requests.findLast(request=>request.path===controlPath(which,value.attempt.id)&&request.response)?.response;
     assert.equal(state.owned,false);assert.equal(state.canCancel,false);
     if(which==='release')assert.equal(value.artifact.id,expected.artifact.id);
   }
   await b.reload();await b.wait(`${controlRoot}?.textContent.includes('Live control is unavailable in this app.')`);
   await shot('unowned-history');await assertCleanResponses();
   assert.equal(posts().length,0);assert.deepEqual(await nativeRequests(),previousRequests);assert.equal(await launches(),previousLaunches);
   checks.push('after controller restart, reads/reload recover the same pinned history with no owner, cancellation control, child launch or resend');
   observations={nativeRequestCount:previousRequests.length,launches:previousLaunches};
 }
 const result={classification:'real-local-api-authored-managed-preparation-fixture',nativeOrModelCalls:0,mode,marker,checks,observations,screenshots,measurements,apiRequests:b.requests,networkUrls,exceptions:b.exceptions};
 await fs.writeFile(`${prefix}-${mode}.json`,JSON.stringify(result,null,2)+'\n');
 console.log(JSON.stringify({mode,checks,apiRequests:b.requests.length,postRequests:posts().length,screenshots,measurements}));
} catch(error) {
 await b.settle().catch(()=>{});
 await fs.writeFile(`${prefix}-${mode}-failure.json`,JSON.stringify({
   classification:'real-local-api-authored-managed-preparation-fixture',nativeOrModelCalls:0,
   mode,marker,checks,screenshots,measurements,apiRequests:b.requests,exceptions:b.exceptions,
   failure:{message:error.message,stack:error.stack},
 },null,2)+'\n');
 throw error;
} finally { await b.close(); }
