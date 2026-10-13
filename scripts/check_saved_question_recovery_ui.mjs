// Rendered saved-question acceptance; all fixture histories are synthetic.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {browserAcceptance} from './browser_acceptance_support.mjs';

const fixture=JSON.parse(await fs.readFile(process.env.NEMA_SAVED_RECOVERY_FIXTURE??'docs/evidence/SAVED_QUESTION_RECOVERY_SYNTHETIC_2026_10_13.json','utf8'));
const prefix=process.env.NEMA_SAVED_RECOVERY_UI_PREFIX??'docs/evidence/saved_question_recovery_ui_2026_10_13';
const baseline=process.env.NEMA_SAVED_RECOVERY_BASELINE==='1';
const h=await browserAcceptance({origin:process.env.NEMA_UI_ORIGIN,debug:process.env.NEMA_DEBUG_ORIGIN});
const {evaluate,wait,click,clickText,fill,select,local}=h;
const snapshot=fixture.recoverySnapshots;
const draft=()=>local('nema.investigation-draft.v1');
const comparison=()=>local('nema.composition.v1');
const previewRoot="document.querySelector('.snapshot-preview')";
const screenshots=[];
async function shot(name,selector) {
  if(selector)await evaluate(`document.querySelector(${JSON.stringify(selector)}).scrollIntoView({block:'start'})`);
  const path=`${prefix}_${name}.png`;await h.screenshot(path);screenshots.push(path);
}
async function eventually(fn) {
  for(let n=0;n<120;n++){if(await fn())return;await new Promise(r=>setTimeout(r,50));}
  throw Error('Synthetic transport checkpoint did not arrive');
}
async function search() {
  await fill('#composition-search',fixture.search);
  await evaluate("document.querySelector('#composition-search').closest('form').requestSubmit()");
  await wait(`document.querySelector('#saved-composition')?.options.length===${Object.keys(snapshot).length+1}`);
}
async function inspect(name) {
  await select('#saved-composition',snapshot[name].id);await click('#preview-comparison');
  await wait(`${previewRoot}?.dataset.compositionId===${JSON.stringify(snapshot[name].id)}`);
}
async function availability() {
  return evaluate(`(()=>{const root=document.querySelector('.snapshot-preview');return {
    question:root.innerText.includes(${JSON.stringify(fixture.frozenContexts[0].question)}),
    rationale:root.innerText.includes(${JSON.stringify(fixture.expectedRationale)}),
    baselineResult:root.innerText.includes('Synthetic retained A1 baseline'),
    contextOnly:!!root.querySelector('[data-preview-side="right"] .preview-context-only'),
    savedRawRecord:!!root.querySelector('.preview-saved-focus .raw-evidence'),
    currentReview:root.innerText.includes(${JSON.stringify(fixture.expectedCurrentReview)}),
    inspectSupport:!!root.querySelector('.preview-inspect-result[data-side="left"]')};})()`);
}
async function targetContent() {
  await wait("!!document.querySelector('.preview-experiment-rationale')&&!!document.querySelector('.preview-saved-focus .raw-evidence')");
  const available=await availability();assert(Object.values(available).every(Boolean),JSON.stringify(available));
  assert.equal(await evaluate("document.querySelector('.preview-current-review').dataset.reviewStatus"),'rejected');
  assert.equal(await evaluate("document.querySelector('[data-preview-side=right] .preview-result')===null"),true);
  assert.equal(await evaluate("document.querySelector('.snapshot-preview').innerText.includes('LATEST_C2_A2_NOT_PINNED')"),false);
  await evaluate("document.querySelector('.preview-saved-focus .raw-evidence').open=true");
  assert.equal(await evaluate("document.querySelector('.preview-saved-focus .raw-evidence pre').textContent"),fixture.rejectionRecord.rawText);
  return available;
}
async function pendingDraft() {
  await clickText('New investigation');
  const name=crypto.randomUUID().slice(0,8);
  await fill('#investigation-title',`DIRTY saved-question draft ${name}`);
  await fill('#investigation-question','Keep this unsaved question and its pending request while I recover another saved question.');
  await select('#context-artifact-picker',JSON.stringify([fixture.sourceOwner,fixture.sourceArtifact]));
  await clickText('Add selected result to context');
  await fill(`[data-selected-artifact-id="${fixture.sourceArtifact}"] input`,'Unsubmitted rationale must survive read-only recovery.');
  h.page.losePost='/api/investigations';await clickText('Save and preview context');
  await wait("!!JSON.parse(localStorage.getItem('nema.investigation-draft.v1'))?.pendingRequest&&!!document.querySelector('.work-error')");
  assert(h.page.lost.some(value=>value.committedStatus===201));
  const value=await draft();assert(value.pendingRequest?.id);return value;
}
async function originalSupport() {
  await click('.preview-inspect-result[data-side="left"]');
  await wait(`document.querySelector('.artifact-lineage[open] [data-lineage-context-id]')?.dataset.lineageContextId===${JSON.stringify(fixture.contexts.C0)}`);
  assert.equal(await evaluate("document.querySelector('.artifact-lineage[open] [data-lineage-artifact-id]').dataset.lineageArtifactId"),fixture.artifacts.A1);
  await wait("!!document.querySelector('.artifact-lineage[open] .lineage-record .raw-evidence')");
  await evaluate("document.querySelector('.artifact-lineage[open] .lineage-record').open=true;document.querySelector('.artifact-lineage[open] .lineage-record .raw-evidence').open=true");
  assert.equal(await evaluate("document.querySelector('.artifact-lineage[open] .lineage-record .raw-evidence pre').textContent"),fixture.originalRecord.rawText);
}
async function closeSupport(){await clickText('Close result provenance',"document.querySelector('.artifact-lineage[open]')");}
async function retain(compositionBefore,draftBefore) {
  assert.deepEqual(await comparison(),compositionBefore);assert.deepEqual(await draft(),draftBefore);
}
let evidence;
try {
  await h.fresh(baseline?'baseline-555a317':'saved-question-recovery');
  const hasEntry=await evaluate("!!document.querySelector('#return-to-saved-work')");
  if(baseline) {
    assert.equal(hasEntry,false);await clickText('Compare');
    await evaluate("document.querySelector('#saved-comparisons-browser').open=true");
    await search();await inspect('target');
    const observed=await availability();assert(Object.values(observed).every(value=>value===false));
    await shot('desktop_baseline','.snapshot-preview');
    evidence={schemaVersion:'nema-saved-question-preview/1',classification:'BASELINE_555a317_SYNTHETIC_FIXTURE',
      availableBeforeOpen:observed,investigationReturnEntry:hasEntry,appliedComparison:await comparison(),humanBenefitMeasured:false};
  }else{
    assert.equal(hasEntry,true);
    const pending=await pendingDraft();
    h.page.phase='read-only-preview';
    await click('#return-to-saved-work');
    await wait("document.querySelector('#saved-comparisons-browser').open&&document.activeElement?.id==='composition-search'");
    await search();assert.equal((await comparison())?.arrangement??null,null);
    await inspect('broader');
    await wait("!!document.querySelector('[data-preview-side=right] .preview-selected-record[data-record-seq=\"3\"]')");
    assert.equal(snapshot.broader.focus,null);
    assert.equal(await evaluate("document.querySelector('[data-preview-side=right] .preview-selected-record .raw-evidence')===null"),true);
    await evaluate("document.querySelector('[data-preview-side=right] .preview-selected-inputs').open=true;document.querySelector('[data-preview-side=right] .preview-selected-record[data-record-seq=\"3\"]').open=true");
    await wait("!!document.querySelector('[data-preview-side=right] .preview-selected-record[data-record-seq=\"3\"] .raw-evidence')");
    await evaluate("document.querySelector('[data-preview-side=right] .preview-selected-record[data-record-seq=\"3\"] .raw-evidence').open=true");
    assert.equal(await evaluate("document.querySelector('[data-preview-side=right] .preview-selected-record[data-record-seq=\"3\"] .raw-evidence pre').textContent"),fixture.rejectionRecord.rawText);
    assert.equal((await comparison())?.arrangement??null,null);assert.deepEqual(await draft(),pending);
    await shot('desktop_unfocused_support','[data-preview-side=right] .preview-selected-inputs');
    await click('#open-comparison');
    await wait(`JSON.parse(localStorage.getItem('nema.composition.v1'))?.snapshotId===${JSON.stringify(snapshot.broader.id)}`);
    await clickText('Edit arrangement');await select('#compare-layout','stacked');await select('#compare-lens','result');
    const appliedBefore=await comparison();
    const editBefore=await evaluate("[document.querySelector('#compare-layout').value,document.querySelector('#compare-lens').value,document.querySelector('#compare-right-context').value]");
    await clickText('Investigation');await click('#return-to-saved-work');
    await wait("document.querySelector('#saved-comparisons-browser').open&&document.activeElement?.id==='composition-search'");
    await retain(appliedBefore,pending);
    assert.deepEqual(await evaluate("[document.querySelector('#compare-layout').value,document.querySelector('#compare-lens').value,document.querySelector('#compare-right-context').value]"),editBefore);
    await inspect('target');const observed=await targetContent();
    await retain(appliedBefore,pending);
    await shot('desktop_preview','.snapshot-preview');
    await shot('desktop_reason_support','.preview-saved-focus');
    await originalSupport();await shot('desktop_original_support','.artifact-lineage[open]');
    await click(`.artifact-lineage[open] .lineage-input[data-artifact-id="${fixture.sourceArtifact}"]`);
    await wait("document.querySelector('.artifact-lineage[open]')?.textContent.includes('No matching adoption decision was included in this frozen input.')");
    await clickText('Back to previous result',"document.querySelector('.artifact-lineage[open]')");await closeSupport();
    await retain(appliedBefore,pending);
    assert.deepEqual(await evaluate("[document.querySelector('#compare-layout').value,document.querySelector('#compare-lens').value,document.querySelector('#compare-right-context').value]"),editBefore);

    h.page.phase='stale-preview';h.page.holdPath='/api/compositions/'+snapshot.target.id;
    await select('#saved-composition',snapshot.target.id);await click('#preview-comparison');await eventually(()=>h.page.held);
    await inspect('current');assert(await evaluate("document.querySelector('[data-preview-side=left]').innerText.includes('LATEST_C2_A2_NOT_PINNED')"));
    await h.page.rpc('Fetch.continueRequest',{requestId:h.page.held});h.page.held=null;await h.settle();
    assert.equal(await evaluate("document.querySelector('.snapshot-preview').dataset.compositionId"),snapshot.current.id);
    await retain(appliedBefore,pending);

    h.page.phase='stale-experiment-read';h.page.holdPath=`/api/investigations/${fixture.owner}/experiments/${fixture.recoveryExperiment.id}`;
    await select('#saved-composition',snapshot.target.id);await click('#preview-comparison');await eventually(()=>h.page.held);
    await inspect('broader');await h.page.rpc('Fetch.continueRequest',{requestId:h.page.held});h.page.held=null;await h.settle();
    assert.equal(await evaluate("document.querySelector('.snapshot-preview').dataset.compositionId"),snapshot.broader.id);
    assert.equal(await evaluate(`document.querySelector('.preview-current-review').innerText.includes(${JSON.stringify(fixture.expectedCurrentReview)})`),false);
    await retain(appliedBefore,pending);

    h.page.phase='failed-preview';h.page.failPath='/api/compositions/'+snapshot.target.id;
    await select('#saved-composition',snapshot.target.id);await click('#preview-comparison');
    await wait("document.querySelector('.saved-comparisons').innerText.includes('Synthetic one-shot read failure')");
    await retain(appliedBefore,pending);await clickText('Retry preview');
    await wait(`${previewRoot}?.dataset.compositionId===${JSON.stringify(snapshot.target.id)}`);await targetContent();

    h.page.phase='failed-experiment';h.page.failPath=`/api/investigations/${fixture.owner}/experiments/${fixture.recoveryExperiment.id}`;
    await inspect('target');await wait("!!document.querySelector('.retry-preview-experiment')");
    assert.equal(await evaluate("document.querySelector('.preview-current-review')===null"),true);
    await retain(appliedBefore,pending);await click('.retry-preview-experiment');await targetContent();

    h.page.phase='missing-source';await inspect('missing');
    await wait("document.querySelector('[data-preview-side=left]').innerText.includes('exact saved context is unavailable')");
    assert.equal(await evaluate("document.querySelector('[data-preview-side=left] .preview-result')===null"),true);
    await click('.retry-preview-sources');await wait(`${previewRoot}?.dataset.compositionId===${JSON.stringify(snapshot.missing.id)}`);
    await retain(appliedBefore,pending);
    h.page.phase='unknown-renderer';await inspect('oldRenderer');
    await wait("!!document.querySelector('.preview-saved-focus [data-unresolved-selector]')");
    assert.equal(await evaluate("document.querySelector('.preview-saved-passage')===null"),true);
    await evaluate("document.querySelector('.preview-saved-focus .raw-evidence').open=true");
    assert.equal(await evaluate("document.querySelector('.preview-saved-focus .raw-evidence pre').textContent"),fixture.originalRecord.rawText);
    await retain(appliedBefore,pending);

    h.page.phase='mobile-preview';await inspect('target');await targetContent();
    await h.page.rpc('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
    await shot('mobile_preview','.snapshot-preview');await shot('mobile_reason_support','.preview-saved-focus');
    await originalSupport();await shot('mobile_original_support','.artifact-lineage[open]');await closeSupport();
    const mobile=await evaluate("({width:innerWidth,document:document.documentElement.scrollWidth-innerWidth,preview:document.querySelector('.snapshot-preview').scrollWidth-document.querySelector('.snapshot-preview').clientWidth})");
    assert.equal(mobile.width,390);assert(mobile.document<=1&&mobile.preview<=1,JSON.stringify(mobile));
    await retain(appliedBefore,pending);

    h.page.phase='explicit-open';await click('#open-comparison');
    await wait(`JSON.parse(localStorage.getItem('nema.composition.v1'))?.snapshotId===${JSON.stringify(snapshot.target.id)}`);
    const opened=await comparison();assert.deepEqual(opened.arrangement,snapshot.target.arrangement);assert.deepEqual(opened.focus,snapshot.target.focus);
    assert.deepEqual(await draft(),pending);
    await h.reload();await clickText('Compare');
    await wait(`document.querySelector('.recorded-comparison')?.dataset.experimentId===${JSON.stringify(fixture.recoveryExperiment.id)}`);
    assert.deepEqual((await comparison()).arrangement,snapshot.target.arrangement);assert.deepEqual(await draft(),pending);

    await h.fresh('fresh-browser-recovery');await click('#return-to-saved-work');await search();await inspect('target');await targetContent();
    assert.equal((await comparison())?.arrangement??null,null);
    await click('#open-comparison');await wait(`JSON.parse(localStorage.getItem('nema.composition.v1'))?.snapshotId===${JSON.stringify(snapshot.target.id)}`);
    assert.deepEqual((await comparison()).arrangement,snapshot.target.arrangement);assert.deepEqual((await comparison()).focus,snapshot.target.focus);
    evidence={schemaVersion:'nema-saved-question-preview/1',classification:'REAL_BROWSER_SYNTHETIC_SAVED_HISTORY',
      availableBeforeOpen:observed,investigationReturnEntry:true,similarNamedSnapshots:Object.values(snapshot).map(({id,title})=>({id,title})),
      originalSupportRecoveredBeforeOpen:true,contextOnlyUnfocusedRawSupportBeforeOpen:true,frozenInputReviewPreserved:true,currentReviewSeparatelyLabelled:true,
      previewRetainedAppliedArrangement:true,previewRetainedUnsavedArrangementEdits:true,pendingDraftRequestId:pending.pendingRequest.id,
      latePreviewIgnored:true,lateExperimentReadIgnored:true,failedPreviewRetried:true,failedExperimentReadNotSubstituted:true,unavailableSourceNotSubstituted:true,
      unknownRendererRetainsRawSupport:true,explicitOpenRetainsHistoricalPins:true,freshBrowserExactRecovery:true,mobile,
      nativeOrModelCalls:0,humanBenefitMeasured:false,
      limits:'Synthetic histories; one deliberately lost save reply and labelled held/503 reads. Objective availability/navigation only, no human participants or speed claim.'};
  }
  await h.settle();assert.deepEqual(h.exceptions,[]);
  const writes=h.requests.filter(row=>row.method!=='GET');
  assert.equal(writes.length,baseline?0:1);assert(writes.every(row=>row.path==='/api/investigations'));
  const reads=h.requests.filter(row=>row.path.startsWith('/api/compositions/')||row.path.endsWith('/source')||/\/experiments\//.test(row.path));
  assert.equal(h.requests.filter(row=>row.path==='/api/investigations'&&row.method==='GET').length,0);
  evidence={...evidence,screenshots,javascriptExceptions:h.exceptions,browserWrites:writes.map(({path,body,status})=>({path,body,status})),
    lostReplyCommittedStatus:baseline?null:201,legacyFullCatalogGets:0,
    ownerViews:h.requests.filter(row=>row.path.endsWith('/view')).map(({context,phase,path,query,status,bodyBytes})=>({context,phase,path,query,status,bodyBytes})),
    exactReads:reads.map(({context,phase,path,query,status,bodyBytes})=>({context,phase,path,query,status,bodyBytes}))};
  await fs.writeFile(prefix+'.json',JSON.stringify(evidence,null,2)+'\n');
  console.log(JSON.stringify({passed:true,baseline,evidence:prefix+'.json'}));
}catch(error){await h.screenshot(prefix+'_failure.png').catch(()=>{});throw error;}
finally{await h.close();}
