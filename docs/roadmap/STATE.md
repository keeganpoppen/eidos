# Implementation state and proof obligations

**As of the seed audit: 2026-10-12.** Inspected implementation base: `6963a0c8d9530005a7998e71aa53e30fe13ea3da` on `main`, tree `a0ccb49d2129f53ed3729e16ee643df9615eb5eb`. These are the pre-seed code identities, not a claim about whatever HEAD a future reader has checked out.

The baseline GitHub Actions run `38240774514` completed successfully: pytest and UI check/build jobs passed. This seed does not claim a new live Codex integration test, local UI inspection, or comprehensive security audit. The seed turn used repository reads and existing CI evidence; its production artifact is documentation/agent context plus context-integrity tests, not a new runtime feature.

Refresh this file when implementation claims materially change. Keep historical audit IDs instead of quietly relabelling old evidence as current.

## Offline native-managed lifecycle — 2026-10-13

Integration base `13abac7`; [contract](../agents/NATIVE_MANAGED_LIFECYCLE_TASK.md),
[experiment and raw evidence](../evidence/NATIVE_MANAGED_LIFECYCLE_EXPERIMENT.md).
Native-owned ephemeral synthetic login now has ordering and refresh evidence.
Near-expiry Plus refreshes to Free before account readiness; the candidate rejects
it with zero threads/turns. Far-expiry Plus passes ordered account/config checks;
issuer closure before thread creation denies an endogenous refresh after two
provider 401s. The next CONNECT exceeds the fixed cap and deliberately closes
native. There is **no recovered native terminal or post-abort account read**.

Initial attempts discovered analytics and mandatory Git attribution settings.
Analytics is explicitly disabled. One reviewed settings-false response is admitted
on the existing local provider; native governance context remains distinct from
selected context. Failed attempts remain raw evidence. Per-authority tunnel
closure cannot recall token bytes already delivered or buffered inside native.
No global writer barrier, real account usability or production admission follows.

Parent default suite: **1,161 passed / 52 explicit native skips**. Independent
parent lifecycle reproduction matches both final development cases: two native
login RPCs, one acknowledged turn, seven issuer/four provider HTTP requests,
thirteen CONNECT attempts; zero real auth/model/upstream requests. Both recorded
cases satisfy current opt-in assertions; the original pytest summary was not
retained across context rollover. Workers joined, active tunnels zero, capture
intact. Parent earlier-TLS regression against shared helpers: **58 passed**.
No runtime or frontend change. Next: successful managed synthetic result recovery
and a private owned-lifecycle integration through the existing investigation.

## Opaque native HTTPS and independent inquiry recovery — 2026-10-13

Integration base `e708c9d`; [native experiment](../evidence/NATIVE_TLS_CONNECT_EXPERIMENT.md)
and [handoff](../agents/CURRENT_HANDOFF.md) identify this wave. Native HTTPS_PROXY
and custom CA behavior now have disconnected fixture evidence: valid TLS recovers
an authored result, a trusted wrong-host certificate delivers no plaintext HTTP,
and a redirected destination is refused before opening an endpoint. Native retries
were observed despite zero configured retry settings. The wrong-host case ends in
a consumer timeout with no observed terminal; that outcome remains incomplete.
The proxy carries encrypted bytes; a separate authored endpoint owns plaintext.
No DNS/upstream path, real account or production admission is introduced.

Parent checks: **1,026 Python passed / 50 explicit native checks skipped** and
**58 native TLS opt-in checks passed**. Parent reproduction made three contained
turns, six CONNECT attempts and three fixture HTTP requests, with zero real model,
upstream or auth calls. Received-byte/buffer/time limits, exact trusted capture
policy and worker shutdown passed. These are not aggregate CPU/RSS/SQLite quotas.
No frontend changed; previous-wave UI evidence is retained separately.

A new local process regression confirms two independent pending Discover inquiries,
B offered before A, database/executor restart, A refusal, ordered incorporation and
exact replay without new occurrences. It needs no runtime change; the product's
single-inquiry admission remains explicit. This does not establish native-stack
resumption or a user need for plural admission. Parent focused checks: **19 passed**.

The [independent managed-auth review](../evidence/NATIVE_ADMISSION_FRONTIER.md#2026-10-13-independent-follow-up-exact-personal-plan-lifecycle)
finds issuer closure could constrain future OAuth refresh, but a successful response
already buffered in native code may still commit. A synthetic issuer lifecycle
experiment is the next discriminator. No global auth-writer barrier or live
admission follows from a cached account/config acknowledgement.

## Saved-question recovery and derived startup catalog — 2026-10-13

Integration base `555a317`; [rendered acceptance](../evidence/SAVED_QUESTION_RECOVERY_INTEGRATION.md)
and [handoff](../agents/CURRENT_HANDOFF.md) identify this integration. Investigation
now offers Return to saved work. Snapshot preview exposes the exact saved question,
historical result, context-only alternative, rationale and raw support before Open.
Current review remains separately labelled. Read-only inspection preserves applied
comparison, unapplied arrangement edits, dirty drafts and pending save identities.
No new backend API, persistence or dispatch. Full selected-owner reads remain a cost.

Parent verification: **973 Python passed / 44 explicit native checks skipped;
78 Bun tests / 416 assertions; Svelte 0 errors / 0 warnings; build passed**.
Independent and parent browser runs preserve exact old pins through later results,
lost save replies, delayed reads, failures/retry, source loss and unknown renderers.
Desktop/390px UI was inspected; no overflow or JavaScript exceptions. Fixture
histories reopened byte-identically. Scripted availability is not human benefit.

The [paired native catalog experiment](../evidence/NATIVE_DERIVED_CATALOG_EXPERIMENT.md)
retains exact upstream metadata beside a labelled two-field local startup policy.
With the same supported agent/sleep controls, original Astra Lite still declares
code/async tools and executes the clock challenge; the derived catalog declares
empty tools and rejects both resource/clock calls. Both return exact synthetic text.
Parent reproduced **24 opt-in checks**, two contained native turns/six authored
local provider requests, zero real models/upstream/credentials and no reported
capture gap. No account entitlement, exhaustive handler proof or production
admission change follows. Supported opaque HTTPS transport is the next discriminator.

## Bounded native recording and capture-aware recovery — 2026-10-13

Integration base `eab1653`; [acceptance and counterexamples](../evidence/NATIVE_CAPTURE_ACCEPTANCE.md)
and [handoff](../agents/CURRENT_HANDOFF.md) identify the containing integration.
AppServerClient reads bounded binary frames before decode, limits combined received
bytes and retained events across queues/wait_for/backlog, and records exact rejected
or partial bytes in a valid internal capture-gap envelope. Configured limits are
recorded per incarnation. Closure wakes waiting consumers independently of queue
capacity. Accepted raw JSON/unknown fields stay intact; non-JSON constants are
rejected. Recovery stops at the first source-scoped trusted capture gap, preserving
completion before it while excluding later imported terminals and contradictions.

Parent final Python suite: **947 passed, 41 explicit native checks skipped**.
Independent acceptance: **24 passed**, including exact-limit completion, truncated
terminals, child marker copies, malformed bytes and durable reopen. Independent
review reproduced equal accepted prefixes across combined and split pipe writes.
The parent also ran **100 native opt-in checks** across three existing contained
fake-provider probes: seven turns/fourteen local provider requests, zero real
model/upstream requests or credentials. Future reports include actual capture
limits/status; historical reports remain unchanged. No frontend or production
native admission change. These budgets do not limit process CPU/RSS, outbound RPC
allocation or total SQLite size; internal direction is a trusted-host convention,
not authentication of arbitrary imports.

## Recorded experiment composition and exact-model challenge — 2026-10-13

Integration base `2c447e4`; [rendered/API acceptance](../evidence/RECORDED_EXPERIMENT_COMPOSITION_INTEGRATION.md)
and [current handoff](../agents/CURRENT_HANDOFF.md) identify the combined delivery.
Recorded context experiments now open reviewable comparisons with their exact
historical baseline result/attempt and context-only alternative, retain those pins
through lens changes, and save/reopen named snapshots. Current review is separately
refreshed; source-input differences and original raw support remain accessible.
No new backend route or dispatch is introduced. New snapshot saves now reject
artifact/attempt inconsistencies; immutable prior receipts remain readable.

Parent integrated verification: **891 Python tests passed, 41 explicit native
checks skipped; 73 Bun tests / 385 assertions; Svelte 0 errors / 0 warnings; build
passed**. Independent acceptance and parent Chromium reproduction preserve dirty
and pending drafts, exact source bytes, old pins despite new results, and delayed
request ordering at desktop/390px widths. Long citation controls now wrap. This is
scripted same-database recovery over labelled synthetic historical results, not
historical-context execution, human speed or model-reasoning evidence.

The independently reviewed [model-catalog experiment](../evidence/NATIVE_MODEL_CATALOG_EXPERIMENT.md)
uses exact public 0.154.0 metadata. Astra exposes code/async/collaboration tools
through Responses Lite despite the previous feature flags, and a safe clock call
executes without a native tool-action item. The ordinary-Responses control has
empty tools and rejects the two challenged calls. Both reject disabled MCP resource
access. Parent reproduced **29 opt-in checks**, two local native turns/six authored
provider requests, zero real model/upstream/credentials. No production profile or
admission changes. Model-specific registry behavior and provider-wire declarations
cannot be inferred from flags or an empty top-level tools field alone.

The later [bounded capture integration](../agents/BOUNDED_NATIVE_TRANSPORT_TASK.md)
addresses the line/event capture and honest-loss obligations identified here.

## Pre-turn tool control challenge — 2026-10-13

Integration base `579af9d`; [raw evidence and source review](../evidence/NATIVE_TOOL_BOUNDARY_EXPERIMENT.md)
record three guarded native turns and six local synthetic provider requests. An
empty per-server tool allowlist still permits the built-in resource reader.
Disabling the fixture MCP server removes its resource handlers; the same authored
call is rejected before access, with zero MCP HTTP contact. Grouped user-input and
skills controls remove their wire schemas, but their handlers were not dynamically
challenged. This uses fallback model metadata, not an authenticated account catalog.

Parent combined native opt-in: **71 passed**, covering the prior text-only probe
and all three new cases. Combined default suite: **849 passed, 38 skipped**.
Independent source/default-test review accepted the narrow result. The shared
bounded HTTP parser is reused without changing the earlier fake-provider behavior.
No real model, credentials, upstream request, authentication claim or production
profile/admission change. Transport stdout/event/trace totals and aggregate CPU,
memory/disk limits remain separate obligations; the consumed-event counter is not
a recorder quota. The recorded-experiment UI loop proceeds independently.

## Durable comparison snapshots and synthetic native transport — 2026-10-13

Integration base `b9f75ea`; [current handoff](../agents/CURRENT_HANDOFF.md) identifies
this wave's containing integration. [Browser acceptance](../evidence/COMPOSITION_SNAPSHOT_INTEGRATION.md)
was independently reproduced by the parent on main. Named comparisons
now save their compiled historical arrangement and focus as immutable ordinary
Values. A bounded metadata catalog, explicit preview/open and save-copy ancestry
recover them in another browser on the same database. Browser drafts remain local.
Exact retries survive a lost response and later source loss. New saves validate
reference ownership; unknown renderer versions retain references without silently
reinterpreting passage offsets. See [D29](DECISIONS.md).

Combined Python verification: **821 passed, 34 explicit native opt-ins skipped**.
Final UI verification: **67 tests / 344 assertions**, Svelte **0 errors / 0 warnings**,
build passed. Actual desktop/mobile recovery preserves dirty drafts, exact source
bytes, old inquiry pins and retry identities; missing-source repair and unknown
renderer handling pass without dispatch. This covers same-database synthetic
recovery, not authentication, shared workspace synchronization or human speed.
First preview still loads full referenced owners through the existing cache.

The parent reproduced **39 tests** in the disconnected
[synthetic-provider native experiment](../evidence/NATIVE_SYNTHETIC_TURN_EXPERIMENT.md).
Two real native turn RPCs completed with authored SSE, persisted artifacts and
reopen recovery under the process-denial boundary. **Zero real model/upstream calls**,
no credentials or production gate change. Actual provider wire included native
instructions and remaining tool schemas; text-only completion does not establish
pre-effect tool admission or caller authentication. A separate active experiment
challenges supported pre-turn tool controls with authored tool-call responses.

## Saved work at scale and native process boundary — 2026-10-13

Integration base `1ee2821`; [measured acceptance](../evidence/SAVED_WORK_SCALE_INTEGRATION.md)
and [handoff](../agents/CURRENT_HANDOFF.md) identify the containing integration.
Saved-work/result discovery now uses paged metadata and title search. Conditional
selected-owner reads avoid repeated history transfer; exact source links return
one artifact/context/attempt with preserved historical input review. Canonical
source and legacy envelopes remain unchanged; read indexes are replaceable.

Combined verification: **732 Python tests passed, 31 explicit native opt-ins skipped**;
**58 Bun tests / 287 assertions**, Svelte **0 errors / 0 warnings**, build passed.
Real HTTP over 1,000 synthetic owners measured 8,189-byte 20-owner catalogs,
99-byte unchanged replies, and a 6,501-byte exact A source versus its 417,697-byte
full owner. Hot catalog/unchanged paths parse no canonical owners and issue no
source SELECTs. Initial recovery, cold/dirty indexing and changed full-owner reads
remain material costs. These are read-path measurements, not aggregate resource
or human-speed claims.

Independent Chromium acceptance and parent reproduction preserve dirty drafts,
historical previews/comparison pins, exact source bytes and retry identities at
desktop and 390px widths. A committed save with a lost reply is retried after
reload without creating a duplicate owner. Missing-owner repair remains available.
No dispatch occurred. All completions in this fixture are authored synthetic data.

The [process-boundary experiment](../evidence/NATIVE_PROCESS_BOUNDARY_EXPERIMENT.md)
was independently reproduced on the combined tree: **34 opt-in tests passed**.
Native 0.154.0 starts under pre-exec kernel restrictions permitting threads while
denying tested child/exec transitions. In-process HTTP MCP still reaches a fake
broker, so this does not establish provider-only authenticated egress. Production
startup remains closed. The next separate experiment exercises real native turn
transport against an isolated synthetic provider; it is not subscription execution.

## Exact result composition and rejected gateway — 2026-10-13

Integration base `29a164a`; [composition evidence](../evidence/ARTIFACT_COMPOSITION_INTEGRATION.md)
and [current handoff](../agents/CURRENT_HANDOFF.md) own final verification. Contexts
can now select exact stored results alongside raw ranges. The server freezes complete
artifact content and separate adoption, validates source context/attempt identity,
and retains source-manifest references. Derived citations support only direct inputs;
original evidence remains separately inspectable. The UI connects result reuse,
frozen preview and C→B→A provenance. Selection and inspection start no native work.

Combined verification: **697 Python tests passed, 6 native opt-ins skipped**;
**52 Bun tests / 259 assertions**, Svelte **0 errors / 0 warnings**, build passed.
Rendered synthetic acceptance covers exact support recovery, artifact-only creation
and revision, and dirty draft preservation through navigation/reload at desktop and
390px mobile widths. This is not a claim of human speed or answer-quality improvement.

Compatibility tests preserve legacy hashes and A2 frozen inputs. A review
counterexample exposed dropped rejection snapshots behind equal artifact IDs;
comparison now checks complete frozen inputs except rationale and reports changed
inputs. These measurements grade neither answer quality nor entailment. A synthetic
persist/reopen chain recovers exact controlling evidence without recursively adding
source transcripts to recipient prompts. See [D28](DECISIONS.md).

The parent reproduced the real no-model
[gateway experiment](../evidence/NATIVE_GATEWAY_ADMISSION_EXPERIMENT.md): **26 tests
passed**, including the expected falsification of caller authentication through a
shared relay. A startup sibling can consume the intended request's permit. No
credentials, model turns or external forwarding were used; the production gate
remains closed. The next independent experiment tests process restrictions before
native startup. It is not yet an admitted execution profile.

## Paged history and native startup experiment — 2026-10-13

Integration base `ad73408`; see [verification](../evidence/PAGED_HISTORY_INTEGRATION.md)
and [current handoff](../agents/CURRENT_HANDOFF.md). Source retrieval now returns at
most 40 complete turns using stable record anchors. Exact thread/turn/item evidence
membership controls navigation and highlighting; late events cannot impersonate
intervening support. Snapshot-bound versions permit compact unchanged polls, and
selected semantic revisions/focus survive page changes and reload. Selected source
ranges also have direct header links when the support pane is hidden at narrow widths.

Combined verification: **653 Python tests passed, 5 explicit native probes skipped**;
**46 Bun tests / 225 assertions**, Svelte **0 errors / 0 warnings**, production build
passed. Actual Chromium navigated a persisted 1,200-turn fixture, preserved distant
support through reload, rejected a wrong-thread record, and kept an old page/focus
stable when an independent writer extended history. These are scripted synthetic
observations, not measured human speed or full V1 acceptance.

A profiled worker now requires an `account/read` acknowledgement before thread
creation. The default native startup gate remains closed. A fresh real no-model
[outer namespace experiment](../evidence/NATIVE_OUTER_ADMISSION_EXPERIMENT.md)
passed independently in the lane and integrated tree (**8 tests**, Codex 0.154.0,
bubblewrap 0.12.0): an unexpected fixture MCP's tested startup effects remained
within a disconnected, disposable Linux boundary before inventory admission.
No credentials, private configuration or authenticated model calls were involved.
Authenticated egress, account/managed-policy lifecycle and aggregate resources
remain unverified; the probe does not itself admit production execution.

History limits bound projected turn count, not individual-turn/outline bytes or
all SQL work. Browser arrangements remain local. Exact result-as-context composition
is the next semantic integration; a synthetic restricted gateway is the next native
experiment. The [program](../agents/PROGRAM.md) records the revisable destination
conjectures and current decomposition.

## Round 3 integrated investigation — 2026-10-13

The commit containing this update integrates actual branches A `18f25c1`, B
`f3d7228`, C `c8b701e`, D `6e491b5` from clean main
`50d1bc91870b9118a84706606d6a06008dffcdf7`. See the
[integration report](../evidence/INTEGRATION_ROUND3.md),
[identity/admission contract](../agents/ROUND3_INTEGRATION.md), and
[current handoff](../agents/CURRENT_HANDOFF.md). Older audits below retain their
original scope and are not statements about current native availability.

The actual workbench now connects durable specialist terminal inquiries,
offer/refuse/defer/cancel, separate source disclosure and recipient incorporation,
immutable expanded context, explicit A2 admission, preserved original/receipt/result
artifacts, saved alternative evaluation and durable adoption/rejection/rollback.
One canonical investigation owns the lifecycle. Original durable pre-send attempt
and manifest-pin admission is preserved; HTTP retry, recovery, disclosure and
experiment evaluation never authorize additional native execution.

**Default live native startup is unavailable.** The accepted profile refuses before
startup because authenticated cloud configuration remains outside verified admission.
Interactive native replies remain unsupported. The API/UI clearly expose this gate;
legacy HTTP chat and model-indexing actions cannot bypass it. No fresh native probe,
subscription model turn or paid API call ran. Earlier no-model authorization grants
no permission for model turns. Source branch no-model reports remain historical.

Combined verification: **607 Python tests passed, 4 native probes skipped**;
**38 Bun tests / 193 assertions**, Svelte **0 errors / 0 warnings**, production
build passed. Fresh/reopened joined synthetic demo reports match with two explicit
fixture attempts/pins and three exact artifact versions. Actual Chromium acceptance
covers inquiry/defer/reload/offer/A2/evaluation/adopt/rollback/reject and evidence
navigation; screenshots were inspected independently at desktop/narrow widths.
Actual subprocess deaths and cross-process requests test atomic follow-up admission
and disclosure/incorporation separation. Native review also repaired malformed
completion envelopes and historical execution classification.

Improvement evidence is bounded: recorded-packet comparison measures record/byte
changes, not answer quality. C's fixed synthetic annotation suite improves three
cases and preserves nonregression on all six; unchanged guardrails do not satisfy
the stricter improvement predicate. No real model reasoning, cost or human speed
improvement is measured. Decisions activate neither configuration nor authority.

Generic TM remains privileged and can accept arbitrary successor grants from Python
host callers; new HTTP paths cannot supply grants/holders/executors. Full native
containment, provider context, account entitlement, resource caps, authenticated
multiuser isolation and exactly-once external effects remain unproved. One inquiry
and one follow-up are supported; arrangements are browser-local and server history
retrieval is not bounded. Next: resolve native admission, then seek separate live
resource authorization. The synthetic joined workflow is runnable meanwhile.

## Authorized native preflight follow-up — 2026-10-13

After explicit owner authorization, both no-model probes were rerun against integrated
implementation `ebcead9a3d05b5ea2da7a066300d057ea304ac8b`: **13 passed, zero skips,
zero model turns**, Codex **0.154.0** on Linux/aarch64. The binary fingerprint and
native observations match the earlier branch artifact; MCP discovery ordering is the
only report difference. See [fresh evidence](../evidence/NATIVE_VERIFICATION_INTEGRATED.md)
and its complete sanitized observation artifact.

This closes the formerly pending no-model preflight action. The worker's policy
acknowledgement and empty-inventory gate work on this host's disposable configuration.
The probes also reconfirm that MCP startup effects precede inventory admission and
read-only permits outside-file reads. No worker gate was weakened. Account-backed
model execution, provider-context capture and complete containment remain unverified;
the owner's authorization covered only these no-model probes.

## Integrated Cycle B — 2026-10-13

The integration commit containing this update starts at `ac2c093b675c5765abccaeff33a721f48f4318ce`
and incorporates reviewed content from native-boundary `e18322e`, investigation-continuations
`70e7c73`, context-manifests `26a606b`, and reflective-workbench `0cca35c`. See the
[integration contract](../agents/INVESTIGATION_INTEGRATION_CONTRACT.md) and
[acceptance evidence](../evidence/INTEGRATION_CYCLE_B.md).

Observed combined behavior: immutable manifests derived from existing frozen packets;
atomic native attempt/request pin; evidence-backed later correlations; an owner-started
local Eidos evidence review with offer/refuse/defer and restart; original native answer
preserved beside a separately named receipt; comparison/focus bound to exact artifact
versions. The UI exposes context gaps and pending decisions instead of inventing native
loading or a specialist question. No competing current-context controller was added.

Combined verification: **361 Python tests passed, 2 native probes skipped**; frontend
check **0 errors / 0 warnings**, **17 tests passed**, build passed. Synthetic end-to-end
demo and reopen retained one native turn/pin and the same inquiry/checkpoint/outcome.
Rendered Chromium acceptance and inspected screenshots cover provenance, comparison,
deferral/reload/offer/adoption and preservation of the native baseline. Independent
reviews attacked concurrency, abrupt crashes, copied authority and miscorrelation.

This advances V1-03/04/07/08/09/10/12, with a local realization of the disclosure part
of V1-06. It does **not** establish a specialist-originated native inquiry, a new model
analysis after disclosure, or all V1 acceptance gates. The generic outer Elaborate
correlation obligation is not universally solved by this fixed review program.

No fresh native call ran during integration: explicit no-model probe authorization was
requested but had not arrived. Imported Codex 0.154.0 evidence is no-model branch evidence,
not a live model verification of this combined tree. In particular, ambient MCP startup
can act before inventory admission; read-only/temporary cwd does not provide universal
containment. Provider context, token/cost bounds, real native delegation and a measured
self-improvement cycle remain unverified. Older audits below retain their original scope.

## Post-seed delivery — 2026-10-13

Starting at `b40d9ac4758ac1129fbfe0ab26c00b28f777b3ae`, the commit containing this update adds a durable two-thread investigation through the existing trace/API/UI: frozen source records, immutable context revisions and exact prompt preview, one transactional dispatch claim, a bounded native worker adapter, evidence-only recovery, attributable artifact, and conclusion adoption. See the [contract](../agents/INVESTIGATION_CONTRACT.md) and [acceptance report](../evidence/INVESTIGATION_CYCLE_A.md).

Verification: 176 Python tests passed; UI check has no errors/warnings and build passed; a scripted Chromium workflow exercised selection, revisions, synthetic dispatch, reload, source return and adoption. Codex 0.154.0 schemas were inspected without a model call. Actual native specialist behavior is **unverified**. This partially closes the product integration gap below, not all V1 gates or the separate P4 Elaborate/Model continuation gap.

The generic ProcessRuntime and trusted authority machinery are unchanged. Native sends need their own durable pre-send attempt; the existing inner prepared-step protocol cannot establish delivery. The new service remains a trusted loopback owner interface, with browser-origin admission and fixed executor settings. The snapshot below remains the original seed audit.

## What is present

| Area | Starting points | Evidence level and caveat |
| --- | --- | --- |
| Native Codex client, process realm, import/proxy | [codex.py](../../src/eidos/codex.py), [codex_proxy.py](../../src/eidos/codex_proxy.py), [trace.py](../../src/eidos/trace.py) | Real adapter/recorder code and existing tests; not proof of exact provider-context capture or every native-version behavior. |
| Live API and UI | [api.py](../../src/eidos/api.py), [serve.py](../../src/eidos/serve.py), [ui](../../ui), [dev script](../../scripts/dev.sh) | Existing client supports chat/trace/semantic-tree work; build/check success is not a usability evaluation of V1. |
| Hindsight semantic tree | [semantic_tree.py](../../src/eidos/semantic_tree.py), [summary checkpoint](../SUMMARY_TREE.md) | Weighted retrospective pipeline with source support; must remain distinct from prospective knowledge and raw source evidence. |
| Local language and object conventions | [core.py](../../src/eidos/core.py), [objects.py](../../src/eidos/objects.py), [CORE](../CORE.md), [OBJECTS](../OBJECTS.md) | Serializable Eidos terms/values, closures, bindings, suspended interactions, multi-input Reactions; not a finished type system or proof of universal semantic minimality. |
| Authority substrate and semantic Values | [trusted.py](../../src/eidos/trusted.py), [authority.py](../../src/eidos/authority.py), [semantic_values.py](../../src/eidos/semantic_values.py), [genesis.py](../../src/eidos/genesis.py) | Local domain/name/holder/disposition and occurrence mechanisms. Storage is much smaller conceptually; semantic adapters and legacy code still coexist in a large Python module. |
| Knowledge and executable Models | [epistemics.py](../../src/eidos/epistemics.py), [model_execution.py](../../src/eidos/model_execution.py), [cuts.py](../../src/eidos/cuts.py) | Rule, closure, delegated, and process experiments with attributable derivations. Known premises are not a general entailment proof. |
| Cut exchange and open discovery | [cut_exchange.py](../../src/eidos/cut_exchange.py), [discovery.py](../../src/eidos/discovery.py), [DISCOVERY](../DISCOVERY.md) | Source/receiver domain occurrences, offer/refuse/defer, recipient-scoped evidence; local trusted-host tests, not authenticated remote service. |
| Shared continuation machine | [process_runtime.py](../../src/eidos/process_runtime.py), [PROCESS_RUNTIME](../PROCESS_RUNTIME.md), [model_process.py](../../src/eidos/model_process.py), [observer_process.py](../../src/eidos/observer_process.py) | Named protocol resolution and generic local checkpoint advancement; requesters/responders are roles. Domain-specific facades still interpret operation semantics. |
| Semantic lenses/indexes | [lenses.py](../../src/eidos/lenses.py) | Name traversal and rebuildable indexes; unrestricted graph reachability is not scoped disclosure authority. |
| Historical experiments | [experiments](../../experiments/README.md), [source archive](../../src/eidos/experiments), [docs archive](../experiments) | Useful rationale/counterexamples; some older Frame/Match runtime remains active for existing paths. Do not treat all archived vocabulary as normative. |

[IMPLEMENTATION.md](../../IMPLEMENTATION.md) preserves the baseline README's feature account. Source and tests outrank claims in that narrative.

## Important advances beyond the last visible founding-chat step

The inspected default branch already contains open discovery, a source observer implemented as a resumable process, and a universal `ProcessRuntime` registered by named `ProcessProtocol`. A third Echo-role test is described in its runtime checkpoint. Do not spend the next session rediscovering requester/responder unification or adding the first pending inquiry because an older document suggested it as future work.

## What is not yet established as a complete product

There is no evidence in this audit that the full [V1](V1.md) acceptance loop is delivered: many-aperture reflective interaction, reliable two-thread context composition, durable outer investigation orchestration, versioned native context manifests, isolated alternative comparison, and one evaluated self-improvement cycle still need integration and acceptance artifacts.

Complete native provider prompts/tools/skills at every request are not assumed observable. Native process coexistence, interruption recovery, side-effect isolation, and input lineage require version-specific probes. A local Eidos checkpoint is not Codex's hidden internal continuation.

## Obligations that strong language in earlier reports did not close

### P1 — Generic commit is privileged, not intrinsically safe for arbitrary callers

The inspected `commit_projection_occurrence` accepts caller-supplied consumed IDs, output grants, kind, and fact. Its local mechanics validate liveness, duplicate inputs, unique output keys, a common domain, and transactional persistence. It does not authenticate a remote principal or prove that arbitrary output descriptions follow legitimately from the inputs.

Therefore “consumes at least one live capability” does **not** establish semantic authority conservation. An exposed caller must not be able to trade a low-privilege token for arbitrary powerful outputs. Preserve the narrow TM mechanism but identify the protected semantic admission path. Add adversarial tests before widening access.

### P2 — Names and holder strings are a model of authority, not remote possession proofs

The current host supplies identities, adapter registrations, and holder strings. A source occurrence can validate local lineage without cryptographically authenticating an independent machine. Keep the trust domain explicit. Do not advertise secure multi-tenant or internet-facing capability transfer on the strength of local tests.

### P3 — Storage simplification is not elimination of semantic interpretation

The observer-specific table reductions are valuable. However, `trusted.py` still hosts semantic adapters and legacy runtime code. “The schema no longer contains Cut tables” does not mean every operation is now a verified ordinary Eidos program or that all policy disappeared. Refactor only against a concrete integration requirement and preserve existing behavior.

### P4 — Inner process recovery is not outer task recovery

The discovery checkpoint explicitly notes that the synchronous convenience path can signal a pending Model while the outer Elaborate attempt is not yet automatically correlated/resumed across invocations. This is a high-value next integration seam. A UI request retry must not silently create a new model process and duplicate external work.

### P5 — Crash and concurrency guarantees are seam-specific

There are meaningful tests around prepared responses, local commits, and resumption. Separate transactions around genesis, first checkpoint, semantic bindings, or external calls can still leave orphaned authority or ambiguous outcomes. Discovery docs note a concurrency obligation around admission of one source responder chain. Test actual races and interruptions rather than extrapolating from sequential replay.

### P6 — Linear authority does not fully solve computation resource safety

A bounded number of informational steps or accepted inferences does not bound arbitrary local evaluation time, memory, subprocess output, tokens, or external side effects. Review fuel/cancellation and process isolation separately. “Pure closure” means no admitted external effect, not guaranteed termination.

### P7 — Historical semantics can accidentally read current mutable metadata

Cut and context Values are immutable, but convenience projections may combine them with current holder/disposition. Verify that historical lenses expose that overlay as current state rather than claiming it was the old observer's knowledge. Historical reinterpretation must not silently rewrite the meaning of its original inputs.

### P8 — Claim provenance is not proof of truth

Model proposals record premises, implementations, receipts, and context. Requiring recognized premise strings establishes attribution/availability, not general logical entailment or external factual truth. A content hash is identity, not a semantic validity certificate.

### P9 — User experience and native integration require direct observation

CI checks Python behavior and frontend compilation/type checking. It does not establish long-history responsiveness, good native rendering, safe live fork behavior, user reorientation speed, or complete capture. Those need their own artifacts and tests.

## How a fresh session should verify this state

Inspect HEAD, git status, root/subtree instructions, test collection, and native versions. Run `uv sync && uv run pytest`; in `ui`, run `bun install`, `bun run check`, and `bun run build`. Read current CLI help before invoking live native operations. Use sanitized fixtures first; obtain explicit scope for live work and preserve user data.

Compare the implementation against the V1 scenarios. Report each area as observed, covered by a named test, locally simulated, inferred, proposed, or unverified. Never carry a historical green count forward as proof that a new tree passed.
