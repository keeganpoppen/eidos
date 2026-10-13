# Runtime context manifests

**Integration update:** the investigation consumer, pre-send pin, read-only API and
provenance UI are now connected by [the shared integration contract](INVESTIGATION_INTEGRATION_CONTRACT.md).
The branch description and proposal table below retain their original as-of scope.

**Provisional implementation contract, 2026-10-13; starting revision
`ac2c093b675c5765abccaeff33a721f48f4318ce`.** The subsystem in
[`context_manifest.py`](../../src/eidos/context_manifest.py) serves
[V1-04 and V1-09](../roadmap/V1.md): inspect the intended context, compare an
ingredient revision, retain the context pinned to old requests, and explain
what evidence supports subsequent adoption. It implements the representation
and local persistence seam. Integration with investigation dispatch, native
capture, HTTP, and UI remains proposed below. It does not establish complete
native context capture or a completed V1 experience gate.

The governing distinctions are [MEMBRANE M2–M5](../vision/MEMBRANE.md),
[SEMANTICS S2–S5](../vision/SEMANTICS.md), and
[REFLECTION R3–R6](../vision/REFLECTION.md). A manifest describes context; it
does not activate instructions, dispatch work, authenticate a caller, or admit
an Eidos authority transition.

## One inspectable temporal loop

1. Freeze ingredient contents and the evidence supporting claims about them.
2. Assemble an immutable manifest, including explicit capture gaps.
3. Compare candidate and baseline by ingredient path. Resolve changed slots
   into their old/new content, knowledge state, boundary, scope, and support.
4. Persist the exact manifest reference on a uniquely named request attempt
   before sending anything. The sending adapter retains its existing dispatch
   admission and recovery obligations.
5. Record activation requests, observed adoption, and later correlations as
   separate immutable events. Evidence may produce a new manifest; it does not
   rewrite the request's original pin.

For example, `M17 -> replace skills/current with S8 -> M18` is a change of a
path's slot reference. `M17` continues resolving the previous slot and skill
content, and requests pinned to `M17` keep that reference. These short names
are display labels; actual references are content identities. The revision
event records that this particular edit led from `M17` to `M18`. Equal
manifest content reached through a different history shares the same content
identity and retains a different event history.

## Knowledge state and capture boundary are independent

Every claim records a `KnowledgeState`, a `Boundary`, an ingredient content
reference, a facet, a `RuntimeIdentity` scope, rationale, and evidence
references. A slot retains several claims and explicit gaps without electing
a winner.

| State | Meaning | Does not establish |
| --- | --- | --- |
| `AVAILABLE` | An ingredient was offered or accessible in the stated context. | It was selected, read, or included in a request. |
| `SELECTED` | The context builder selected this immutable ingredient. | The native harness loaded it. |
| `PROJECTED` | This is intended input at the stated boundary. | The boundary received it or a provider saw the same input. |
| `OBSERVED` | A claim is supported by frozen trace evidence at its stated boundary. | Arbitrary entailment, complete visibility, or capability authority. |
| `INFERRED` | An interpretation derived from stated support or rationale. | Direct observation or permission to act. |

`Boundary.LOCAL`, `Boundary.APP_SERVER`, and `Boundary.PROVIDER` name different
observation surfaces. A locally available skill and an observed app-server
`turn/start` input can coexist with unknown provider instructions. These
states are not a progress counter: selection need not lead to loading, and
inference never automatically upgrades to observation.

`OBSERVED` requires frozen TraceStore evidence appropriate to the declared
boundary. App-server traffic cannot support a provider observation merely
because it contains a prompt. Validation checks provenance and boundary
compatibility; it cannot prove that an arbitrary asserted facet follows from
raw JSON. TraceStore and this subsystem remain trusted-host interfaces. A
caller able to fabricate raw records is not made trustworthy by hashing them.

Use single-valued facets such as `loaded_version` or `effective_model` for
mutually exclusive observations. Two different observed contents under the
same facet and boundary are compared using compatible runtime coordinates.
A shared known attempt ID anchors a conflict even if one observation lacks a
thread ID that the other captured. Incompatible known coordinates remain
different scopes. Compatible partial scopes without a shared attempt produce
a potential conflict (`scope_uncertain=True`); a shared request alone may
cover several retries. Pairwise conflicts retain both supporting records and
never choose a winner. Different boundaries are not collapsed.
Several simultaneously included instructions belong in separate ingredient
slots or in one explicitly ordered aggregate, not as competing values for a
single-valued facet.

`inspect(manifest, path, boundary=Boundary.PROVIDER)` returns claims, gaps,
and conflicts. Its `unknown` property reflects absent observations at that
boundary or explicit gaps. Even `unknown == False` for one slot proves no
completeness of the manifest or provider context. Missing slots and missing
native identifiers remain missing; absence is not evidence of exclusion.
An explicit `unknown(reason, boundary=..., details=...)` distinguishes a known capture
gap from an ingredient the builder did not describe at all.

## Identity, bindings, and occurrences

| Identity | Representation and lifetime |
| --- | --- |
| Content | A content identity addresses canonical immutable data plus labelled references. Equal content deduplicates; a changed reference creates different content. |
| Name | A durable name identifies an entity or local occurrence independently of changing content. Name allocation and uniqueness remain the caller's responsibility; request/event insertion durably reserves the local key. A name grants no authority. |
| Binding | `put_binding` stores a Role-to-target projection, optionally with its own Name. Binding name, Role, target content/name, entity name, capture mode, and placement remain distinct. Changing the target produces a new projection value. |
| Causal occurrence | A named event describes a revision, activation request, adoption observation, or correlation. Explicit parent event references carry claimed causal links. Equal outcomes can have different occurrence names. |
| Runtime incarnation | `RuntimeIdentity` carries optional `process_name`, `incarnation_id`, `thread_id`, `turn_id`, `request_id`, and `attempt_id`. Restarting a process may preserve its logical name and native thread while changing incarnation. |
| Activation/adoption | An activation request describes intent. An adoption observation records supported evidence at an explicit boundary and scope. Neither is implied by constructing a manifest or seeing a file change. |

The manifest identity excludes creation timestamps, predecessor manifests,
and runtime activation. These belong in event/request objects. Events are
descriptive causal records, not Trusted Machinery committed occurrences over
live authority. The store neither consumes nor creates capabilities.

`put_binding(role, target, name=None, target_kind="content",
capture="situated", entity_name=None, placement=None)` accepts existing
`core.Role` and optional `core.Name` values. `target_kind` distinguishes a
fixed content referent from a named entity reference. The latter does not
silently resolve to the entity's current value. `capture` distinguishes
`situated`, `lexical`, and `snapshot` projections; these labels describe the
builder's choice, rather than changing the evaluator's binding semantics.
Placement is descriptive data. Moving an entity or changing a path is not
renaming the entity, and copying a historical binding cannot revive its old
authority.

Local append order and wall-clock timestamps are useful indexes, not a
universal causal clock. There is no global mutable “current manifest” pointer.
A native turn can have multiple provider requests and retry attempts. A
manifest pinned at an app-server boundary must not be labelled as the exact
context of every provider attempt inside that turn.

Adapters must supply owner-qualified attempt identities, not bare retry
counters that collide across requests. Preserve native counters in captured
content and establish their correlation separately. Unknown coordinates stay
`None`; time proximity and matching display names do not establish identity.

## Ingredient conventions

`put_content(kind, data, refs=None)` accepts finite JSON content with string
object keys and labelled references to existing objects. The `cm.*` kind
namespace is reserved for validated subsystem objects. Schema 1 uses a
versioned Python JSON encoding, not a cross-language canonical JSON standard.
Data and reference labels are canonicalized for identity; ordering that
carries meaning must be represented explicitly.
Arbitrary additional JSON fields survive round trips. Missing fields, explicit
`null`, empty lists, and explicit unknown objects are different descriptions.
The subsystem does not read live instruction directories or silently expand
paths. Adapters freeze content deliberately before making claims about it.

The following paths and payload shapes are integration conventions, not a
second native protocol schema:

| Path family | Suggested immutable content |
| --- | --- |
| `instructions/<source>` | Exact text, source locator, declared version, source type, and content/byte digest as appropriate. A path alone is not a version. |
| `instructions/agents_layers` | Ordered layer identifiers, scope roots, intended precedence, resolver/version identity, and labelled references to frozen AGENTS.md files. Record omissions and uncertain native loading separately. |
| `skills/catalogue`, `skills/<name>` | Available catalogue metadata and exact skill versions. Separate availability from `loaded_version` claims at a captured scope. Loading a main file does not imply loading every referenced resource. |
| `tools/<name>`, `capabilities/<name>` | Description/schema versions and configured policy declarations. Configured availability is not live capability possession or proof of invocation. |
| `model/configuration` | Intended model/settings, explicit defaults when established, native version, and unsupported/unknown settings. Preserve provider-observed settings independently. |
| `workspace/identity`, `workspace/revision` | Logical workspace identity, repository locator, checkout identity, commit, dirty-state description, and references to captured changes when capture policy permits. A commit alone does not describe dirty contents. |
| `evidence/<selection>`, `builder/decisions` | Frozen selected records/ranges, inclusion and exclusion rationales, selection ordering, truncation decisions, builder version, and exact projected prompt. |
| `runtime/scope`, `bindings/<role>` | RuntimeIdentity descriptions and Role/Binding projections. Native IDs not yet returned remain null/absent. |
| `native/unknown` | Explicit gaps for hidden instructions, compaction/history transformations, tool injection, request retries, or other uncaptured native ingredients. |

A catalogue discovery can itself be observed at the local boundary without
proving a skill was loaded. An inferred AGENTS precedence rule must retain its
resolver/version and inference status; directory nesting alone is not proof
of native precedence for a particular request. Referencing the same frozen
instruction from a layer stack and an availability slot shares its content.

## Persistence and public Python seam

Construct `ContextManifestStore(trace)` with the existing `TraceStore`.
`cm_*` tables store immutable content and request/event indexes in the same
SQLite database, using its connection and lock. Savepoints allow operations
to compose inside a caller-owned SQLite transaction without committing that
outer transaction; an independent operation starts an immediate transaction.
Constructors and builders persist immutable objects; they
do not send native requests. Callers must commit the pre-send pin before
crossing the external boundary.

Manifests use a persistent segment trie. Replacing `skills/current` rebuilds
that branch and its ancestors; unrelated tool/instruction subtrees retain
their content identities. A manifest root is not a flattened copy of every
ingredient, and old roots continue resolving their old graph. Path segments
are addresses within the manifest, not durable entity names.

| Interface | Result/obligation |
| --- | --- |
| `put_content(kind, data, refs=None)`, `get(cid)` | Create/retrieve an immutable `ContextObject`; `.data` returns a fresh JSON value, `.refs` is immutable, `.ref(label)` resolves a labelled reference. |
| `claim(content_cid, state=..., boundary=..., facet="included", evidence=(), rationale="", scope=RuntimeIdentity())` | Persist a qualified content claim; observation requires compatible frozen evidence. |
| `unknown(reason, boundary=..., details=None)`, `slot(*claim_or_gap_cids)` | Persist explicit uncertainty and a collection of qualified ingredients. |
| `manifest(path_to_slot)`, `replace(manifest, path, slot_or_None)` | Return `ContextManifest(cid, root)`; `None` removes a path in a new manifest. |
| `at(manifest, path)`, `entries(manifest)`, `diff(before, after)` | Resolve slots and list semantic path changes; `ContextChange` contains `path`, `before`, `after`, and `operation` (`add`, `remove`, or `replace`). |
| `inspect(manifest, path, boundary=Boundary.PROVIDER)` | Expose claims, explicit gaps, and contradictory observations without choosing a winner. |
| `freeze_trace(seq)` | Freeze original raw text, its digest, and provenance. It must not import today's mutable correlation/index overlay as historical knowledge. |
| `pin_request(name, manifest, identity=..., boundary=Boundary.APP_SERVER, state=KnowledgeState.PROJECTED, evidence=())` | Persist a uniquely named boundary/attempt pin in `PROJECTED` or `OBSERVED` state. Identical replay returns the existing object; reusing the name with different content fails. |
| `get_request(name)`, `requests_for(manifest)` | Read exact recorded pins. Do not infer affected requests from timestamps or current configuration. |
| `record_event(name, kind=..., manifest=..., previous_manifest=None, identity=..., boundary=Boundary.LOCAL, evidence=(), parents=(), request_name=None, supplemental_manifest=None, details=None)` | Persist a named `revision`, `activation_requested`, `adoption_observed`, or `correlation` event. `parents` contains existing local event names. Adoption and correlation need evidence at their stated boundary. A correlation may link a later supplemental view without repinning the request. |
| `get_event(name)`, `events(manifest=None)` | Read recorded lineage/correlation/adoption descriptions. |

Frozen trace snapshots protect against later index hydration and retain unknown
raw fields. Original raw TraceStore evidence remains the source. A snapshot
does not create an independent source of truth, and a snapshot's digest is not
a certificate that its claims are true. Native correlation learned later is
a new `correlation` event referring to the request name and evidence, not a
mutation of the request or an old snapshot. A later evidence-enriched manifest
can coexist with the manifest originally projected for that request.

Trace sequence numbers are local to the owning TraceStore database. Moving
graphs between databases needs an explicit source-database namespace and
import mapping; this module does not define cross-database import, garbage
collection, or a new evidence authority. Direct SQL writers remain trusted;
digest verification detects altered object content on reads, not malicious
replacement of the entire local database.

Claim objects reference their ingredient as `content`; request and event
objects reference their context as `manifest`. Correlation requires an existing
`request_name` and must retain that request's exact manifest. Its optional
`supplemental_manifest` reference describes a later evidence-enriched view;
it neither repins the request nor establishes complete provider visibility.
A request-linked adoption event has the same primary-manifest constraint.
Adoption cannot be asserted at the
local boundary, and app-server adoption requires incoming app-server evidence;
an outbound request alone is insufficient. Interpreting that evidence remains
the caller's responsibility. Event parents must already exist, so neither a
self-parent nor an unresolved future parent becomes a causal edge.

A minimal synthetic revision and pin use only the local representation:

```python
from eidos.context_manifest import Boundary, ContextManifestStore, KnowledgeState
from eidos.trace import TraceStore

trace = TraceStore()
contexts = ContextManifestStore(trace)

def selected_skill(version, text):
    content = contexts.put_content("skill", {"version": version, "text": text})
    selected = contexts.claim(
        content, state=KnowledgeState.SELECTED, boundary=Boundary.LOCAL,
    )
    gap = contexts.unknown("Native loading is not captured", boundary=Boundary.PROVIDER)
    return contexts.slot(selected, gap)

m17 = contexts.manifest({"skills/current": selected_skill("S7", "Synthetic v7")})
pin = contexts.pin_request("synthetic/attempt-1/app-server-input", m17)
m18 = contexts.replace(m17, "skills/current", selected_skill("S8", "Synthetic v8"))
contexts.record_event("synthetic/edit-1", kind="revision", manifest=m18, previous_manifest=m17)
assert contexts.diff(m17, m18)[0].operation == "replace"
assert pin.ref("manifest") == m17.cid
assert contexts.inspect(m18, "skills/current").unknown
trace.close()
```

The module provides local persistence guarantees, not exactly-once external
execution. A durable pin with no observed send can remain pending or uncertain
after interruption. Recovery reads evidence and existing attempt state; it
must not interpret a pin as permission to resend.

## Proposed integration interfaces; protected modules remain unchanged

These are precise next-consumer contracts, not implemented endpoint or native
adapter behavior in this delivery:

| Consumer | Integration point |
| --- | --- |
| `investigation.py` | Preserve the existing `InvestigationContext` and its ID. Add a `manifestId` reference when creating/revising a preview. Freeze each selected raw record, store the exact `projectedPrompt`, and record selection/builder decisions as slots. Preserve native gaps. A preview revision creates a new manifest and a named revision event. |
| `investigation_worker.py` | At the last local boundary before sending the reviewed native input, build the runtime/configuration snapshot and persist `pin_request` using an attempt-qualified local name and `PROJECTED`/`APP_SERVER`. Reference the preview manifest through builder provenance if the final manifest adds runtime information. Commit before send. After matching raw traffic, freeze it and record a supported app-server observation/correlation; retain unknown provider ingredients. |
| `codex.py` | Supply process logical name/incarnation, known thread/turn/RPC IDs, actual recorder sequence, and configuration evidence to the context builder. Return unknown identifiers explicitly. A supported provider recorder may later add provider-attempt pins; app-server IDs alone cannot manufacture them. |
| `api.py` | Expose read-only manifest, path inspection, diff, request-pin, and event queries through the existing local owner API. Suggested resources: `GET /api/context-manifests/:cid`, `GET /api/context-manifests/:cid/slots?path=...&boundary=...`, and `GET /api/context-manifests/diff?before=...&after=...`. Serialize explicit state/boundary/scope and support references. Keep dispatch admission in the existing investigation API. |
| `ui/` | Render a baseline/candidate ingredient diff, separate availability/loading labels, scope and boundary labels, explicit gaps, conflicting observations with source links, and pinned requests. Offer a preview of an activation proposal. Do not display “provider saw” from projected or app-server evidence. |

The worker's request name must identify its own boundary attempt; the outer
investigation attempt ID can appear separately in `RuntimeIdentity`. If a
turn later exposes two provider attempts, each gets its own request name and
manifest/evidence association. The API should return both exact pins and
separately attributed later correlations; it must not manufacture one
flattened “actual context” by merging them.

## Capture policy and acceptance counterexamples

Capture is explicit and local. This subsystem neither scans nor overwrites
global Codex instructions, skills, auth directories, or configuration. Real
context may contain private instructions, tool secrets, workspace contents,
and conversation evidence. Keep those artifacts in the existing private trace
storage policy; never commit them to this public repository. Capture adapters
must apply disclosure policy before persistence. When material is omitted or
redacted, retain a safe reason, capture provenance, and an explicit gap rather
than claiming complete capture or storing the removed secret in a rationale.
Hashes provide identity, not confidentiality.

The synthetic tests in
[`test_context_manifest.py`](../../tests/test_context_manifest.py) are the
acceptance seam. Required counterexamples are:

- Mutating a caller's original JSON, rereading a modified skill file, or
  learning new native IDs must not change an old object, manifest, or pin.
- Replacing one skill must preserve unrelated ingredient/subtree references;
  deleting it must yield a removal diff while keeping the old manifest usable.
- Equal manifests reached through distinct events must share content while
  keeping distinct occurrence identities and explicit parent relationships.
- An available catalogue entry must not become a loaded skill. A projected
  user prompt or app-server send must not become observed provider input.
- Missing model fields and native IDs must round-trip without invented
  defaults. Unknown raw fields must survive frozen evidence.
- Two observations of different model/skill versions at the same boundary,
  facet, and scope must remain inspectable as a conflict. Different incarnations
  or provider attempts must not be conflated into one observation.
- A file-change or activation-request event must not count as observed adoption.
  A later adoption event must not repin an old request or imply universal hot
  reload.
- Reusing a request/event name with altered content must fail across reopen;
  identical replay must preserve its immutable reference. Outer transaction
  rollback must not leave a committed request pin.
- A frozen historical binding must remain descriptive, with lexical capture,
  situated target, entity identity, and placement independently inspectable.

These tests establish local representation and persistence behavior. Supported
native loading boundaries, real provider capture, inspection usability, and
the complete dispatch/adoption loop require separate integration evidence.
