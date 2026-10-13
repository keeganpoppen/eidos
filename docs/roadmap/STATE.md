# Implementation state and proof obligations

**As of the seed audit: 2026-10-12.** Inspected implementation base: `6963a0c8d9530005a7998e71aa53e30fe13ea3da` on `main`, tree `a0ccb49d2129f53ed3729e16ee643df9615eb5eb`. These are the pre-seed code identities, not a claim about whatever HEAD a future reader has checked out.

The baseline GitHub Actions run `38240774514` completed successfully: pytest and UI check/build jobs passed. This seed does not claim a new live Codex integration test, local UI inspection, or comprehensive security audit. The seed turn used repository reads and existing CI evidence; its production artifact is documentation/agent context plus context-integrity tests, not a new runtime feature.

Refresh this file when implementation claims materially change. Keep historical audit IDs instead of quietly relabelling old evidence as current.

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
