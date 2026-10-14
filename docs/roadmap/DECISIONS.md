# Decision register and preserved design rationale

This is a reconstruction of the collaboration's important turns, not a verbatim transcript. **Accepted direction** records endorsed intent. **Provisional realization** records a current engineering choice. **Open obligation** identifies what still needs proof or implementation. **Deferred exploration** preserves an idea without making it a prerequisite. Source provenance is in [SOURCES](../agents/SOURCES.md).

## Endorsed direction

### D01 — Codex is the harness; build a meta-harness

The native subscription-backed agent loop is the initial evaluator. Nema adds durable observation, context/topology control, reflection, and presentation. Replacing the agent loop would distract from the distinct value and user constraint. Other executors remain possible later.

### D02 — A personal authority-local world, not a cloud dashboard

Persistence, control, and execution should feel owned by the user. A web app is a peer observation/intention surface. Remote execution is compatible with locality when admitted explicitly; cloud centralization is not a conceptual requirement.

### D03 — Preserve more than the first interpreter understands

Retain raw operational evidence and unknown native information. Normalize/index for utility without destroying source distinctions. Derive deeper models later from corresponding harness/provider observations. A perfect middle ontology is not needed before recording useful evidence.

### D04 — Names, roles, bindings, references, addresses, and holders differ

Names preserve identity; Roles are namespaced semantic positions; Bindings connect code to situated values/references. Binding identity differs from its address and target. Lexical closure capture differs from role binding at realization. This is the answer to namespace collapse and implicit dynamic environment, not just naming style.

### D05 — `perform` is the ordinary interaction boundary

Local reduction can construct new values without external effects. External suspensions expose continuation structure. Resolution may be ordinary local interpretation until it needs a remote interaction. There is no necessary universal `resolve` networking primitive.

### D06 — Derive the Smalltalk-like object world

Facet/structural-dispatch experiments showed wrappers and method dispatch can live in ordinary Records and Closures above Core. Keep reflective object/metaobject behavior without requiring a dedicated evaluator branch for every semantic noun. The surviving pattern is refer → wrap → rebind.

### D07 — Frame/cut is a useful reified view, not an absolute global state

Keep frame-content identity separate from event/occurrence identity. A persistent self need not literally embed its entire predecessor chain; named structural sharing and provenance express the relation more cleanly. Cuts across independent continuations need not all advance together.

### D08 — Sockets carry current relational continuation and authority

The intended socket is an authorized local projection of a named session relation, carrying its current continuation. Successor sockets make progress explicit. A copied historical frame or socket description does not duplicate live authority. Endpoint roles need not be tied permanently to participant identity.

### D09 — Multi-party Reaction, domain-local occurrence

A reaction can join several suspended computations, not one privileged sender. Its occurrence is the causal fact connecting histories. Atomic commitment does not imply simultaneous remote observation. A notification, an observer's incorporation, and a real external effect are different causal steps.

### D10 — Actualizer and Elaborator are roles

Elaboration interprets the actual into structured possible futures; actualization admits one occurrence. They differ semantically, not necessarily mechanically. Both can be ordinary Socket operations above shared authority mechanics. Neither must be a singleton daemon.

### D11 — Understanding is not authority

Two cuts, a better model, or more attention can reveal a new possibility. It does not grant world authority. Specialists may be closures, subagents, remote/virtual agents, subprocesses, humans, or compositions. Their placement does not define their semantic role.

### D12 — Historical reinterpretation is a first-class capability of the product

Later understanding can improve a model of an old world without reviving old authority. Keep original reports, derived interpretations, and counterfactual experiments distinct. Recompilation or replay under mocked effects requires an explicit new realization, not pretending the original live continuation survived unchanged.

### D13 — Many surfaces and many theories of attention

Surface, Lens, Focus, and Aperture capture the shared world and different ways of encountering it. The renderer is not the owner of meaning. Prompts and UIs can be alternative lowerings of an interaction. Preserve domain-native artifacts, not just textual summaries or JSON views.

### D14 — Reflection should apply to the apparatus itself

Record and inspect context construction, orchestration, presentation, and improvement sessions with the same tools used for ordinary tasks. Adoption should be tested, versioned, attributable, and reversible. Recursive self-improvement is an evidence loop, not unbounded autonomous rewriting.

### D15 — The coherent useful whole outranks another minimal novelty

The current seed explicitly elevates the reflective Codex workbench and complete two-thread investigation loop. Minimality is valuable when it enables composition and delivery. Kernel exploration must not indefinitely postpone the recorder/controller and lived experience.

## Provisional realizations and open obligations

### D16 — One-shot local authority and explicit genesis

The prototype uses live/spent projections and a separately admitted genesis. Keep single-consumption as the starting discipline. Multi-shot exploration is possible through explicit new branches/authority, not copying a live token. Open: scope, admission, scheduling, and safe garbage collection of orphaned/abandoned projections.

### D17 — Generic TM with protected semantic admission

Accepted aim: narrow atomic local commit, no universal rich protocol interpreter in TM. Current realization: trusted Python adapters supply successor descriptions. Open obligation: who may submit such a transition, and what constrains those outputs? Burning any token is not sufficient proof. A hash labelled proof does not close this gap. Do not let prior celebration of “generic commit” conceal it.

### D18 — Python/uv plus current UI is the delivery substrate, not metaphysics

Earlier Flix/effects/CSP/Datalog work remains influential. The present repository is Python and Bun/Svelte. A replacement language or storage engine must justify a concrete benefit and migration path. Preserve semantic interfaces and native capabilities rather than restarting implementation to fit a favorite tool.

### D19 — Semantic tables may be removed; interpretation still exists

Canonical named Values and generic authority history replaced much bespoke observer storage. Derived indexes can be discarded/rebuilt. This does not establish that every schema convention is fundamental or that the host contains no semantic code. Keep archival experiments where useful; do not treat all old documents as simultaneous law.

### D20 — Disclosure and graph traversal are distinct

A generic lens may discover references within code. A scoped process cannot infer permission to inspect from reachability. Source disclosure and receiver incorporation are separate domain-local occurrences. Local holder/registration checks model this distinction; authenticated remote transport is not yet established.

### D21 — Requester/responder are positions in a protocol, not species

The newer implementation has one named-protocol ProcessRuntime. Pending, terminal, and continuing operations are locally described and checked; semantic handlers remain situated. Do not recreate duplicated engines for every participant type. Open: robust outer orchestration, resources, actual distributed placement, and handler composition driven by use cases.

**Provisional realization, 2026-10-13 (D01/D15/D21):** the first integrated investigation persists a pre-send native attempt beside TraceStore. Reusing `ModelProcessRunner.Consult` alone would still leave the external-completion-before-prepare window open, so this slice does not force a kernel adapter around the same unsafe seam. Repeated dispatch returns the existing attempt, recorded terminal evidence can recover its result, and missing evidence remains unknown. The calculus remains the intended continuation substrate; connecting visible offer/refuse/defer inquiry state to this durable outer identity is still an open delivery obligation. See the [contract](../agents/INVESTIGATION_CONTRACT.md) and [tested limits](../evidence/INVESTIGATION_CYCLE_A.md).

**Integrated realization, 2026-10-13 (D03/D13/D15/D21):** the four-lane integration
keeps Investigation/context/attempt identities canonical; manifests are immutable
ingredient projections, with a request pin committed before native launch. The visible
offer/refuse/defer step is a fixed, owner-started local evidence review using the existing
ProcessRuntime, not a native specialist question or new analysis. Its separate receipt
exposed a concrete identity defect: context-only result apertures silently followed a
replaced artifact. Comparison now pins the artifact version and retains the original
native answer through review. Reject competing current-context state, automatic resend
from historical pins/checkpoints, generic authority endpoints, and declaring V1 complete
from branch test counts. Defer specialist-originated interaction and broader capture
until a bounded real-native loop is verified. The [integration contract](../agents/INVESTIGATION_INTEGRATION_CONTRACT.md)
records compatibility; [evidence](../evidence/INTEGRATION_CYCLE_B.md) states the limits.

### D26 — Round 3 preserves native admission and separates measured alternatives

**Accepted, 2026-10-13**, integration base `50d1bc9`. Concrete incompatibilities:
A2 rollover broke C/D baseline resolution; D's authored fixture was not a durable
inquiry/evaluation controller; startup profile evidence did not establish safe live
model execution. Resolve exact artifacts and attempts through retained history,
adapt the existing experiment graph to scoped owner actions, and expose explicit
startup refusal. Terminal evidence requests use the existing Eidos continuation
and one separately admitted native follow-up; do not call that hidden-stack resume.

Preserve Ultra's transactional pre-send attempt/pin. Retry and recovery never send.
Source disclosure remains distinct from recipient incorporation. Evaluation records
selection/size or structured synthetic checks; adoption is a separate bounded
decision and activates no configuration. Historical host evidence, not output text,
classifies synthetic/native-observed/unverified results. Legacy HTTP model actions
remain gated alongside investigation dispatch. Generic TM stays privileged and
unexposed; its arbitrary-successor limitation is retained as a counterexample.

Reject competing controllers, dynamic latest-result baselines, automatic model
retries, fixture-derived claims of live readiness and measurement-derived authority.
Native resource authorization is separate from the prior no-model probes. See the
[contract](../agents/ROUND3_INTEGRATION.md) and
[verification](../evidence/INTEGRATION_ROUND3.md). This amends D21's deferred inquiry
and alternatives list within the documented one-inquiry/one-follow-up scope; the
V1 destination and language commitments remain unchanged.

### D27 — Page by stable evidence; resolve membership from constituent records

**Accepted, 2026-10-13**, integration base `ad73408`. The old browser window
limited rendering but fetched and projected the entire thread on every poll.
Server retrieval now projects at most 40 complete turns, addressed by their first
record rather than array positions. Exact source jumps validate thread membership;
saved anchors follow the original record through delayed native acknowledgement.
A read snapshot binds page, interpretation metadata and version. Unchanged polls
return a compact envelope and preserve the browser's existing evidence objects.

A concrete counterexample sharpened the reference contract: a late tool event or
interleaved turn can make an item's min/max extent cover records it never contained.
Projected turns and items therefore carry their constituent record sequences.
Highlights, support indicators and source navigation use those sequences; range
labels remain extents. Context range selection still means all selected-thread
records in that range and exposes them in preview. It is not implicit item-only
selection.

The additive SQLite index is replaceable. Raw evidence and immutable semantic
revisions remain authoritative; pages and conditional versions are derived. The
bound is on projected turn count, not bytes in one turn, outline size or all SQL
aggregation work. Browser-local focus is still not a server-saved arrangement.
See [current evidence](../evidence/PAGED_HISTORY_INTEGRATION.md).

### D28 — Compose exact results as frozen inputs; inspect support separately

**Accepted, 2026-10-13**, integration base `29a164a`. Investigation context may
select exact artifacts alongside trace ranges. The store resolves each artifact
within its source investigation, validates its context/attempt relationship, and
freezes its complete recorded content, manifest references and matching adoption
decision. The selection carries historical data, including unknown fields and
typed inquiries/receipts; it grants no continuation, adoption or execution authority.

Only directly supplied inputs support output citations in the recipient packet.
An inherited evidence or artifact citation remains unsupported until that input
is explicitly supplied. Original support stays separately addressable through the
source context; composing A→B→C does not recursively insert A/B transcripts into C.
Later source review cannot rewrite an already frozen input or manifest. A2 retains
the original input snapshots. Legacy packets without artifacts retain their exact
prompt, context ID and manifest IDs.

A review counterexample sharpened comparison: the same artifact selected before
and after rejection has different frozen input content. Dropping that rejection
must not pass retention because the artifact name and count match. Version 2
selection metrics compare the full frozen input except inclusion rationale and
report changed inputs separately. These are retention/size measurements, not
answer-quality evaluation. The synthetic entailment evaluator does not grade
derived artifact inputs.

This narrow adapter uses canonical Investigation/context/attempt/artifact identity;
it adds no competing provenance store or new authority kernel. Local manifests
describe supply, not truth, authentication or complete provider context. See the
[composition evidence](../evidence/ARTIFACT_COMPOSITION_INTEGRATION.md).

### D29 — Save compiled arrangements as immutable reference snapshots

**Accepted, 2026-10-13**, integration base `b9f75ea`. A named comparison captures
its exact applied arrangement and focus, rather than a semantic request to resolve
again against newer inquiry or result state. It is an ordinary immutable context
manifest Value with a thin local metadata/idempotency index. Opening is an explicit
browser operation. Changed arrangements create copies with ancestry; no mutable
shared workspace head or automatic browser-state synchronization is introduced.

New saves validate source ownership and inquiry/experiment relationships. Existing
snapshots and exact successful retries survive later missing sources; unresolved
references remain inspectable and repair creates a copy. Snapshots contain no
draft prose, raw histories, executable handles or transferred authority. The same
database is the persistence boundary; cross-database sharing is not established.

Passage selectors record their renderer/parser version. A different renderer
keeps exact artifact and record references but cannot silently reinterpret a block
offset. Retry identity is independent of installed renderer compatibility: after
a browser upgrade, an exact previously committed receipt still confirms the old
captured request. Save-copy uses a new request. See the
[contract](../agents/DURABLE_ARRANGEMENTS_TASK.md) and current handoff for verification.

### D30 — Preserve private native evidence; publish attributable results

**Accepted, 2026-10-13**, integration base `6ea405a`. An annotation on a main-store
source cannot prevent raw control fields entering ordinary source selection or
export. New investigation incarnations therefore record wholly in a separate
private SQLite store. A trusted host resolver validates the original request and
terminal evidence before a transactional, uniquely bound derived result publication
enters the main workbench. Unknown fields, late control traffic, stderr and exact
capture-gap bytes remain private under the existing bounded recorder semantics.

Artifact outputSeqs name main publication records; optional outputEvidence names
that provenance explicitly. Private inquiry causes use version 2 capsule-scoped
request/event references, never bare main-store sequence numbers. Existing public
recordings retain version 1 behavior. A copied capsule name is a locator, not an
inspection grant, authenticated identity or reconstructed execution authority.

A real authored subprocess counterexample rejected publishing while recorder
cleanup could still accept a contradictory terminal. Publication now requires
reader termination and revalidation while holding per-capsule writer exclusion;
concurrent recovery cannot publish an actively changing capture. Host crash
releases the advisory exclusion and permits evidence-only recovery without resend.
These Unix locks and file permissions guard trusted host operations, not arbitrary
owner code. Logical budgets do not establish a physical database quota.

A derived publication is inspectable, reusable and retained if its private proof
later disappears; missing proof cannot admit a new inquiry. Existing admitted
continuations preserve their host ledger. Public context lineage describes local
publication, never manufactures raw native acknowledgements or provider context.
No native admission exemption or real login flow follows from this change. See
[contract](../agents/PRIVATE_NATIVE_EVIDENCE_TASK.md) and
[integration evidence](../evidence/PRIVATE_NATIVE_EVIDENCE_INTEGRATION.md).

**Owned-control extension, base `7d3354a`:** the live host reserves the existing
attempt before worker launch and latches exact-attempt cancellation. A durable
stopped claim prevents prelaunch retry from reviving execution. Persisted lifecycle
phases describe the last observation; they never reconstruct current control.
Preparation reuses the worker's bounded pump and private recorder, with a finite
cooperative deadline. Cancellation and native outcome remain distinct: closed
evidence may support a completed result even after a stop request. See the
[owned-control evidence](../evidence/OWNED_ATTEMPT_CONTROL_INTEGRATION.md).

### D31 — Separate contained startup, fresh readiness and recorded closure

**Accepted implementation direction, 2026-10-13**, base `8ed2f0a`. One deliberately
enabled managed attempt uses the existing private worker and frozen context. A
fresh disposable runtime, device login and ordered account/config observations
precede one private pre-turn receipt. Closing issuer paths precedes provider
readiness. A reusable profile is a factory, never a cached admission or credential.
Exact historical identity and readiness hashes support evidence interpretation;
they cannot reconstruct the live runtime. The ordinary native profile stays closed.

The challenge is transient current-attempt control, with explicit navigation to
sign-in and the local preparation deadline. It never enters public history or
browser storage. Each attempt requires fresh sign-in; this isolation choice has
an unmeasured usability cost. Product bounds are explicit in the
[accepted contract](../agents/MANAGED_ATTEMPT_TASK.md), independent of older probe
limits. Neither the flag nor these docs establish real account/model availability.

Independent review found completed evidence could publish after failed cleanup
when its negative close marker could not be stored. Managed recovery now requires
one successful exact closure record after all native protocol rows. Missing
closure retains private terminal evidence but leaves outcome uncertain; invalid
closure refuses recovery. This deliberately narrows crash recovery after native
completion and before closure commit. Legacy completed-prefix recovery remains
unchanged. Copying any closure record grants no live capability. Cancellation
also signals pending startup before waiting for registration locks, so a held
startup guard cannot launch a child after observing Stop.

### D32 — Reuse frozen historical inputs through a new canonical question

**Accepted implementation direction, 2026-10-13**, base `2a62d68`. A historical
context can supply its frozen evidence ranges, records and result snapshots to a
new investigation. This copies data from an exact owner/context, not the current
editor selection, latest artifact review, old prompt or native continuation.
One shared projector builds the new question and applies current bounds. Local
inputOrigin records where those inputs came from; parentContextId remains the
within-investigation revision relation. Neither describes live authority.

Thin selectors were rejected for this operation because ordinary resolution
refreshes source adoption/manifests and may lose the snapshot a person reviewed.
The frozen context can therefore supply inputs even after underlying raw/source
owners disappear; missing the actual source context still refuses. Original raw
and unknown fields remain untouched. Later ordinary revisions can change inputs,
with their parent leading back to the original reuse rather than claiming equality.

Creation is staged separately from the working draft, persists an exact request
before sending, and recovers without automatically dispatching or opening work.
An initial created context remains pinned even if a retry returns a newer owner
revision. Read-only inspection precedes deliberate Open; pending editor saves and
later navigation cannot be overwritten by a delayed response. This is explicit
historical data reuse, not automatic adoption/default activation or a native fork.
See the [contract](../agents/CONTEXT_INPUT_REUSE_TASK.md).

### D33 — Discover recorded text through exact source contributors

**Accepted implementation direction, 2026-10-13**, base `1698f6a`. Text discovery
uses the same final/delta projection rules as history display, applied to an
explicit eligible public-record subset. It indexes typed text fields, not generic
raw JSON or hidden/private/control records. An excluded provider/control row cannot
replace eligible text by borrowing its item coordinates. Literal matching discovers
candidate evidence; it does not establish a claim or choose a conclusion.

The disposable index records exact contributors and source versions. A cursor binds
its query and generation; changed history requires refresh. Exact raw inspection
requires the selected hit version. Surrounding current history remains a separate
view and may differ. Excerpt limits alone do not bound imported metadata, so both
search and inspection envelopes have an explicit size refusal. Cold/dirty indexing
and literal scans remain corpus-dependent work.

Explicit Add stages exact record membership, never an item's min/max extent.
Existing semantic support ranges retain their intentional range meaning. Busy or
pending editor saves block source additions; read-only discovery stays available.
Canonical Save freezes selected references using the existing builder; an unsaved
inspection is not a new source-hash precondition or live capability. This closes a
27-page recovery case without claiming human-speed or model-quality improvement.
See the [contract](../agents/EVIDENCE_DISCOVERY_TASK.md).

### D34 — Import supplied bytes as one isolated, recoverable operation

**Accepted implementation direction, 2026-10-13**, base `2386b29`. A malformed
JSONL tail currently leaves a committed prefix; retry duplicates displayed deltas.
Explicit file ingestion must atomically retain the original bytes, parsed records,
physical line mappings and immutable receipt. Request replay resolves the committed
operation before current parser, discovery or collision checks. The receipt survives
source deletion and never recreates deleted records. Identical lines within a file
remain distinct events. This is one local SQLite transaction, not an exactly-once
external-effects claim or evidence that the supplied file is authentic native output.

A supplied origin label cannot borrow a live recorder's RPC correlation scope.
Each new import receives a host-derived capture source; native coordinates and raw
bytes remain intact. New operations refuse existing thread identities, including
retained annotations and semantic maps, instead of silently replacing their current
interpretation. Coordinate rewriting was deferred, and a future incremental/merge
operation needs an explicit review contract. Reserved host publication shapes refuse;
ordinary unknown fields and strings remain evidence, never execution authority.

Preview is bounded and file-local. Browser admission requires recognizable displayed
history, while the CLI still permits explicitly labelled raw-only imports. Pending
browser recovery stores metadata only; receipt checking and exact-file retry are
deliberate, never automatic. Import cannot replace a dirty/pending investigation.
The byte CLI now defaults to operation replay; the trusted legacy iterable API keeps
source/correlation/count semantics and gains bounded atomicity, without claiming
original-byte retention or durable idempotency. See the [contract](../agents/HISTORY_IMPORT_TASK.md).

### D35 — Authored findings are reusable knowledge, independent of native completion

**Accepted implementation direction, 2026-10-13**, base `2aae982`. Public repository
excerpts reproduced a practical gap: an owner's conclusion survived as selection
rationale but was absent from result discovery. Completing an artifact correctly
required an attempt. Add an immutable finding to its existing investigation and
exact saved context, with explicit local-workbench attribution. Reuse the current
result catalog, source inspection, frozen inputs and plain comparisons. Do not
manufacture output records, attempts, inquiry state or adoption authority.

An uncited hypothesis is legitimate if labelled. Recognized citations establish
membership in the directly supplied packet, not entailment or verified truth.
Citing another finding does not supply its original raw records. A finding keeps
its original context even after the investigation advances. Revisions are further
values; source history and old context/prompt/manifest bytes stay intact.

Canonical collection membership, shape and owner-bound content identity distinguish
authored findings from native results. A copied kind cannot bypass native attempt
provenance. Dedicated immutable request receipts recover the exact finding after
lost replies and restart; returning the current mutable owner would be insufficient.
Submission attribution is not authentication of a human author. These are narrow
local owner operations, not a new general artifact or permissions framework.
See the [contract](../agents/AUTHORED_FINDING_TASK.md).

## Deferred explorations, kept for their potential

### D22 — Names, routing, locality, and leases

The DNS/routing/subdomain intuition aimed at composable names and movable computation: bind a remote participant locally, route through admitted places, and preserve identity when residency changes. Systemd/process trees and namespace/tun/tap ideas similarly suggested a personally controllable execution fabric.

Do not implement a 20 ms DNS lease system or bounded 255-slot routing scheme as a prerequisite. Ordinary cached DNS does not give simultaneous authoritative observation; leases need explicit clocks/fencing/renewal semantics. Durable identity reservation is not the same as a lease on current residency or authority. Prototype a real handoff/locality need before choosing network machinery.

### D23 — ITCs, causal DAGs, ledgers, and rendezvous tags

Dynamic causal clocks may be useful for split/join history; DAGs avoid an unnecessary global total order. They are not by themselves capability systems, anti-double-spend mechanisms, or distributed agreement. A common rendezvous tag shows a naming relation, not that peers hold complementary unforgeable authority. Prefer the smallest local substrate until cross-domain work demands more.

### D24 — Types, kinds, protocol projection, and unification

Role subtyping, dependent descriptions, session types, proof witnesses, and unification may sharpen admissible continuations. Keep them as research directions with executable counterexamples. Do not infer a complete type theory from a few typed records. The expression language needs to serve real composition across surfaces and places before type machinery becomes a new product gate.

### D25 — Natural metaphors are guides, not premises

Cells, membranes, receptors, catalysts, impulses, the arrow at rest, forests, astronomy, glaciers, and seed crystals helped articulate boundaries, latent possibilities, and evidence. Preserve their explanatory value. No requirement depends on a claim about quantum observers creating reality, biology proving a runtime rule, or the absence of an observer preventing an actual event.

## How to change a decision

Create a short amendment naming the decision ID, concrete pressure/counterexample, alternatives, chosen revision, impact on tests/data/migration, and evidence of review. Mark supersession instead of erasing the reason the old decision existed. A fresh session should inherit judgment, not be imprisoned by slogans.
