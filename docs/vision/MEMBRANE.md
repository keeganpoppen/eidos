# The Codex membrane

**Status:** target specification, not a claim of complete capture or control. Check [STATE](../roadmap/STATE.md) and the installed native protocol before implementing an operation.

## M1. Codex is the harness; Nema is the meta-harness

The original comparison of agent harnesses exposed a decisive constraint: use the owner's authorized Codex subscription and native harness capabilities. Nema begins as a smart proxy/controller around one or more app-server processes. It owns observation, durable references, context projections, process topology, explicit interventions, forks, recovery, and presentation. It does not replace the native agent loop.

Initially pass through and record rather than speculate about hidden semantics. Derive explanations incrementally from independent evidence. Other executors may later inhabit compatible roles without reducing all providers to a lowest-common-denominator agent API.

## M2. Keep the runtime levels separate

Distinguish personal authority domain, place/executor realm, app-server process incarnation, native thread, user-visible turn, provider request/attempt, tool/external effect, and Eidos process/checkpoint. One native process may host many threads; one turn may generate several provider requests. A retry is not a new user intention. A restart may preserve logical/native thread identity while changing process incarnation.

Begin with few app-server processes under explicit Nema ownership. Add processes for isolation, configuration, resource scheduling, or failure domains—not one process per nema by definition. Do not assume that the Desktop app's process is attachable or jointly owned merely because a filesystem or auth directory is shared. Detect and test coexistence rather than terminating or modifying a separate client.

## M3. Trace both sides; label the unknown middle

The target has two independently useful streams. At the harness boundary: client requests, app-server replies and notifications, available hooks, native control/tool events, imported history, and Nema's semantic actions. At the provider boundary: actual outbound model requests and responses/attempts, where supported and legitimately observable.

Each record needs source, recorder/native version, process incarnation, correlation identities, observed ordering, timestamps, raw payload reference, and any established causal parent. Preserve unknown fields. Keep imported historical hydration distinct from live observation. Correlate using evidence, not coincident timestamps alone.

```text
observed records -> normalized indexes -> semantic interpretations -> views/actions
```

An app-server request is not necessarily the exact provider prompt. A field inferred from code/configuration is not an observed field. Hidden provider instructions or server-side transformations remain unknown unless a supported capture path exposes them. Coverage gaps must be visible. Preserve raw evidence privately according to capture policy; deliberate redactions should have provenance without revealing the removed secret.

## M4. Persistent, structurally shared runtime context

The owner explicitly wants to know when context changes and what was available at a particular moment. Context construction must therefore be a first-class inspectable artifact.

A proposed ContextManifest references immutable versions of instruction sources, skills/catalogue, tool definitions and policies, workspace revision and dirty state, resolver/bindings, model configuration, native version, history/compaction state, selected evidence, and Nema wrappers. Distinguish available, discovered, selected, demonstrably included, and unknown ingredients.

Associate each request/attempt with the manifest actually used when observable; otherwise label the coarser boundary. A turn-level snapshot alone cannot explain changes between multiple provider attempts. Historical references must not resolve silently to today's mutable files.

Store content once and share unchanged structure. Keep content identity distinct from the event that adopted it. A current-skills-directory binding can change while old manifests still resolve old skills. Do not embed the whole historical world in every self-value.

## M5. Updating context deliberately

Controlled generation directories, content-addressed bundles, or immutable snapshots may help. They are implementation tools, not a requirement to virtualize the entire filesystem.

```text
proposed edit -> reviewed content -> candidate manifest
    -> supported activation boundary -> observed adoption -> affected requests
```

A file watch proves a file changed, not that an existing harness reloaded it. Test process-, thread-, turn-, and request-scope loading for each ingredient and record the native version. Neither mandatory restarts after every edit nor assumed universal hot reload are adequate.

Keep desired context, projected context, and observed model input distinct. Preview selected evidence and instruction changes before adoption. Persistent instruction changes must be reviewable and reversible. Preserve existing user configuration and native state.

## M6. Forks are several different things

A semantic fork reinterprets immutable evidence. A native conversation fork branches supported Codex history. A workspace fork isolates file/process changes. A speculative run uses bounded or mocked effects. A live handoff transfers a continuation. Reintegration adopts a selected result; it is not concatenating every child transcript.

Record base evidence, branch point, context, executor, authority scope, workspace isolation, expected output, and reintegration decision separately. A conversation fork does not by itself isolate filesystem effects. Ephemeral workers must still be recorded. A historical checkpoint does not carry resurrected live authority.

For Codex, describe observable native continuations: thread resume, supported pending requests, and actual control operations. Do not claim access to the provider's internal stack. For Eidos, code migration/re-elaboration must name the compatibility step and retain the original code and checkpoint.

## M7. Recovery is part of the experience

Distinguish pending, not sent, sent-but-unknown, externally completed, locally committed, locally resumed, and incorporated elsewhere. Command idempotency helps only at the boundary it actually controls. A database transaction does not guarantee exactly-once external tool execution.

Show uncertain outcomes honestly and require deliberate recovery for irreversible effects. Preserve native IDs and logical process references across app-server restart. Cancellation and shutdown need explicit handling of live authority and useful checkpoints. No promise of resuming arbitrary native computation from a serialized description.

## M8. Practical implementation preferences

Current code uses Python/uv and Bun/Svelte. Earlier Flix exploration motivated effects, CSP, Datalog, inspectable continuations, and recompile/resume; preserve those goals without making a language rewrite a release prerequisite. Systemd, local sockets, namespaces, message streams, and polyglot executors are possible realizations, not the definition of the project.

Prefer small local services and explicit ownership. Avoid unnecessary container orchestration or a new distributed substrate for a personal workbench. Detect the actual environment; do not bake old machine paths into the seed.

## M9. Required boundary tests

Exercise unknown-field retention, fragmented/interrupted streams, repeats and reordering, several provider attempts per turn, context changes with stable historical references, crash/resume, coexistence with another native client, bounded workers, unsupported operations, labelled capture gaps, redaction, and native version/schema drift. These protect the validity of every explanation and action built above the membrane.
