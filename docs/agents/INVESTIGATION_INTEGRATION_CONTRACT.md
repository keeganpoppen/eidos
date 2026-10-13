# One investigation across context, native work, review, and comparison

**Integration contract, 2026-10-13; implementation base `ac2c093b675c5765abccaeff33a721f48f4318ce`.**
This additive contract reconciles the four branch deliveries. It supersedes their
proposed integration seams, not their historical evidence or the V1 destination.

## Identity and ownership

| Object | Owner and meaning |
| --- | --- |
| `Investigation.id` | Durable outer work identity in `InvestigationStore`; UI always reads its saved state. |
| `context.id` | Existing immutable packet: question, selection, original bytes, rationale and exact native user prompt. Identity encoding is unchanged. |
| `context.manifestId` | Immutable, derived ingredient projection of that packet. Never a separate mutable current-context pointer or an authority grant. |
| `attempt.id` | One admitted native operation; persists before launch. Its status remains distinct from outer review status. |
| `attempt.manifestId`, `contextRequestName` | Runtime projection and immutable PROJECTED/app_server request pin, committed atomically with the attempt. |
| Native source/thread/turn | Native ownership/correlation, learned only through recorded operations. Unknown fields/IDs remain unknown. |
| `continuation.id`, `contextName` | Host-admitted local review and inner Eidos Context; neither replaces the native packet or revives a native continuation. |
| Response `evidenceContext` | Separately frozen offered packet, with its own manifest. It was never sent to the original native turn. |
| `nativeArtifact`, `artifact` | Original native result is retained unchanged; review produces a separately named decision receipt containing that result. |
| Comparison target | `{investigationId, contextId, artifactId?}`. Result lenses require an exact artifact ID. Context identity alone cannot identify a result version. |

The manifest adapter (`investigation_context.py`) derives from saved packet bytes,
not current trace-index overlays or live files. Unchanged ingredients share content
identities. Manifest content excludes timestamps and predecessor links; explicit
revision annotations retain those relationships. Workflow context IDs keep their
existing encoding. A manifest is an attributable projection, not replacement history.

Dispatch fixes the projected policy shared with the worker, the exact input, and a
request pin inside the same SQLite transaction as the attempt. A failure before
commit rolls back both. A crash after commit leaves one uncertain attempt; a pin
does not authorize a resend. Legacy unattempted packets can receive a derived
manifest at claim. Already attempted legacy work gets no invented pre-send pin.

Later reconciliation reads only the attempt's recorded incarnation. It requires
one turn request, exact input equality, matching known thread/turn coordinates,
and a response after that request with the exact RPC ID type/value. Outbound
logging precedes pipe writing: its observation is **not delivery**. A correlated
native acknowledgement is **not provider input capture**. These immutable events
reference the original pin and a supplemental view; neither rewrites the pin.
Projection errors remain visible and independently repairable through recovery.

## Integrated read seam

- `GET /api/investigations/:id/context-lineage` returns schema version, context
  references, the attempt's pin and separately recorded correlation events, plus
  an optional projection error.
- `GET /api/investigations/:id/contexts/:contextId/manifest` returns that packet's
  ingredient claims, explicit gaps, and changes from its parent. It accepts only
  context IDs owned by this investigation, including its offered packets.

These routes are pure reads. No generic manifest mutation, Name resolution,
arbitrary executor, or authority endpoint is exposed. Legacy missing manifests
remain visibly unavailable. This is the existing trusted loopback owner service,
not authenticated multiuser isolation.

## Local review and presentation

The [Cycle B API](INVESTIGATION_CYCLE_B_CONTRACT.md) is exposed as **Local evidence
review**. It is owner-started, uses a fixed Eidos continuation, and records an
offer/refusal/deferral. It does not claim Codex emitted the question or synthesized
a new answer. The native result stays visible while adoption waits for the review.
The response scope and retry ID persist before sending. An offer preview names
exact ranges; the server freezes their bytes at admission and exposes that receipt.

Comparison reads saved objects, including both artifact versions. Browser storage
holds only arrangement/focus references and undo state. Legacy result arrangements
without artifact IDs remain unpinned until a reviewed edit; missing versions are
never replaced silently. Arrange/inspect/apply/undo has no execution side effect.

## Accepted and deferred design

Accepted: native transport/admission repairs; the immutable manifest store consumed
by real investigation dispatch; the existing outer continuation consumed by a
visible local review; reflective comparison with explicit result-version binding.
This combination improves one recoverable work loop rather than exposing four
unrelated modules.

Rejected: treating all branches as fully delivered V1; a second context controller;
dynamic "latest result" baselines; automatic resend from a pin/checkpoint; generic
manifest/TM mutation routes; presenting local disclosure as a new model conclusion.

Deferred: specialist-originated native inquiries, an actual subscription-backed
model acceptance turn, complete instruction/skill/provider capture, durable
cross-device arrangements, named alternative lineage, and bounded server-side
history retrieval. Native MCP startup can act before inventory refusal; temporary
cwd/read-only policy do not contain arbitrary ambient integrations. No universal
isolation, cost cap, or exactly-once external-effects guarantee is established.

Evidence and verification belong in [the integration report](../evidence/INTEGRATION_CYCLE_B.md)
and [CURRENT_HANDOFF](CURRENT_HANDOFF.md), not in this contract as evergreen claims.
