# v0 contact report

This is a checkpoint after the first implementation pass. It distinguishes the things the code now makes concrete from the parts of the Nema/Eidos picture that remain hypotheses.

## The vertical slice that exists

```text
Praxis term
   |
   | local reduction
   v
perform(socket, op, value)
   |
   v
immutable Frame + durable offered socket
   |
   | Trusted Machinery
   v
Match + durable receipts + successor socket occurrences
   |
   v
next Frame + resumed Praxis continuation
```

This is end-to-end and restartable from SQLite. The scheduler has no authoritative in-memory state: current Frames, offers, Matches, receipts, and socket dispositions are sufficient to reconstruct what may happen next.

### Important refinement: receipt incorporation is a Frame transaction

The initial design had a separate `incorporate_receipt()` operation. That creates a crash hole:

```text
mark receipt consumed
CRASH
publish resumed Frame never happens
```

The Runtime therefore computes from an unincorporated receipt, then asks Trusted Machinery to atomically publish the successor Frame *and* mark the receipt incorporated. The old standalone method remains useful as a low-level experiment, but it is not the Runtime path.

## What survived contact with code

### Frame

A Frame works well as an immutable local causal cut. Binding changes are ordinary construction of a new Frame; there is no trusted `mutate_binding` primitive.

### Socket

The useful semantic invariant is not "socket belongs to one Frame." A socket occurrence may be referenced unchanged across many Frames. It is one-shot with respect to **session advancement**:

```text
K17 -- Match M --> K18
```

`K17` remains historical evidence. Trusted Machinery recognizes `K18` as the live successor authority.

### Live

`live` means only:

> Trusted Machinery still recognizes this socket occurrence as current, unspent authority.

It does not imply resident, reachable, scheduled, executing, or recently pinged.

### Match

A Match is the objective causal fact joining two local histories. Match durability precedes either participant incorporating its receipt. No simultaneous remote observation is assumed.

### perform

`perform` remains a good semantic membrane. Praxis stays local until it encounters a socket operation. It then returns an explicit serializable `Await`; it does not execute the effect itself.

## What became less fundamental

### Binding mutation

Bindings still look extremely useful as Eidos data, especially once roles and richer references return. But "rebinding" currently compiles to a new immutable Frame. Trusted Machinery need not know what an `executor` role means.

### Reify

Praxis continuations are already represented as data. At least inside the language we own, there is no separate magic `reify()` step. Native/opaque evaluators such as Codex remain a different matter.

### Static linearity

Eidos does not yet prove linear use. Socket descriptions may be copied freely; Trusted Machinery dynamically prevents duplicate authoritative advancement. A future type system can make races unrepresentable without becoming the ultimate enforcement boundary.

## The Codex boundary that exists

`AppServerClient` starts or connects to a stdio-style child evaluator and records every JSONL record before interpreting it enough for RPC correlation. Unknown methods and fields remain in the raw evidence.

`CodexPlace` is deliberately thin: one app-server process is treated as one evaluator realm that may host many native Codex threads.

The current OpenAI app-server interface gives us useful observable boundaries directly:

- thread lifecycle;
- turn lifecycle;
- item lifecycle;
- command execution and terminal interaction;
- file changes;
- approvals and other server requests;
- context compaction;
- raw response completion events.

Eidos does **not** claim these observations expose every intermediate Codex continuation or exact provider request. Opaque native state is allowed.

## Old history and future traffic converge

Future traffic can be recorded by `AppServerClient` or the transparent JSONL proxy.

Persisted old threads can be hydrated with the current paginated app-server APIs:

```text
thread/turns/list
thread/items/list
```

The native RPC request/response records are kept. The history importer additionally emits explicitly derived `$history/turn` and `$history/item` records so the same renderer can consume live observations and imported history.

That source distinction is preserved; presentation does not depend on it.

## The alternate UI that exists

`TraceStore` is an append-only-ish SQLite evidence boundary for protocol messages. It stores the complete raw JSON text plus disposable index projections:

```text
source
direction
RPC id / correlated method
threadId
turnId
itemId
item type
emitted / observed time
```

RPC correlation may enrich the projections on an earlier record (for example, attaching the newly returned `turnId` to the original `turn/start` request), but never rewrites its raw evidence.

`eidos serve TRACE.db` renders threads from **our** store. It already has independent renderings for user messages, assistant messages, command executions, file changes, tool calls, and the raw native event spine; unknown items fall back to inspectable JSON.

This is intentionally not yet a general compositor. A real trace should tell us what the first useful split/tab/window primitives need to be.

## Try the real boundary

Once `codex` is available on the machine where Eidos runs:

```bash
# Pull a few existing threads into our own evidence store.
uv run eidos codex-sync .eidos/traces.db --recent 3

# Render them with our own UI.
uv run eidos serve .eidos/traces.db
# -> http://127.0.0.1:8765
```

To record a JSONL client transparently instead:

```bash
uv run eidos codex-proxy .eidos/traces.db -- codex app-server --listen stdio://
```

The proxy is transport-level: stdin/stdout semantics stay app-server-native while both directions are persisted.

## Things v0 explicitly does not solve yet

- exact Responses API **request** capture from the native Codex harness;
- automatic mapping from every native Codex state to an Eidos socket continuation;
- multiple active Praxis fibers in one Frame;
- multi-party rendezvous;
- static linear/session typing;
- cross-host Trusted Machinery / consensus;
- Codex Place migration and reconciliation of outcome-unknown effects;
- persistent tabs/splits/compositor state;
- automated trace auditors / suggestion agents;
- actual terminal/process multiplexing outside the Codex events we already observe.

Those are now relatively crisp seams rather than one undifferentiated architecture problem.

## Next experiment

The highest-information next step is not another abstraction pass. It is:

1. run `codex-sync` against a few real personal threads;
2. look at what our renderer loses or improves relative to Codex Desktop;
3. run one new thread through the traced client/proxy;
4. compare imported history with the live event stream;
5. add the first compositor/windowing primitive demanded by that evidence;
6. only then deepen the Codex continuation mapping or provider-bound instrumentation.

The working maxim remains:

> **The calculus should sharpen the recorder/controller, not postpone it.**
