# Models as resumable epistemic processes

> **A Model can be a self-realizing participant in an epistemic protocol, rather than a one-shot function from input to proposal.**

The first vertical slice lives in [`model_process.py`](../src/eidos/model_process.py).
It extends the existing Model Role: a Model Value can select the `process`
engine with a first-class Eidos Closure as its program. It still ultimately
produces the familiar `ModelProposal` and `ModelDerivation`.

A process may suspend, inspect named contextual Values, consult a delegated
specialist, resume its serialized continuation, and eventually return a
proposal. Those steps are themselves ordinary generic TM occurrences over
**process-local authority**, not over any participant projection in the
observed world.

## The membrane

The program receives a `ModelInput` and situates the ordinary Eidos Role
`elaboration/process-socket` at the current one-shot process projection.

It is free to construct terms of this form:

```text
perform processSocket.Inspect(InspectRequest(target=Cut C1))
    |
    Reaction -> inspected Value, successor Socket K1
    |
perform K1.Acquire(CutRequest(provider, Cut C2))
    |
    Reaction -> named successor Context with {C1,C2}, Socket K2
    |
perform K2.Inspect(InspectRequest(target=Cut C2))
    |
    Reaction -> inspected Value, Socket K3
    |
perform K3.Handoff(HandoffRequest(worker:remote))
    |
    Reaction -> one successor Socket held by remote worker
    |
perform K4.Consult(ConsultRequest(specialist, question))
    |
    Reaction -> specialist proposal/receipt, Socket K5
    |
return ModelProposal(...)
```

These are ordinary Core `Perform` nodes. Praxis suspends with a serializable
`Suspended` containing its residual `Continuation`. It has no special
ModelProcess evaluator cases.

The host-side `ModelProcessRunner` currently handles four admitted
informational operations:

- `model:Inspect`: read a Value **explicitly in the current Context's
  admitted inspection scope**; return an `InspectedValue`.
- `model:Consult`: send a `ModelConsultation` to a separately admitted
  executor; receive an attributable `ModelProposal`.
- `model:Acquire`: request a new Cut from an explicitly authorized
  `CutProvider`, verify its source-domain `DiscloseCut` occurrence, and
  construct a new immutable Context incorporating that Cut.
- `model:Handoff`: consume the current process projection and establish
  exactly one successor held by a separately admitted target runner.

The generic semantic lens follows every Name in every Value, including Names
inside executable Closures. **It is not an authorization system.** The process
runner derives inspection rights only from explicitly admitted Context/Cut,
Knowledge, Model, and Attention bindings, so merely mentioning an unacquired
Cut's Name in code does not permit inspecting it.

A Model cannot invoke an arbitrary Socket through this runner. A terminal
suspension must target the current process projection, be in the process's
own authority domain, and use an admitted operation.

## Two distinct kinds of authority

Starting a process is an explicit authority genesis act:

```text
ModelProcess domain
    process projection K0  (live)
```

Each informational interaction is an ordinary generic occurrence:

```text
ModelInteraction  consumes K0, establishes K1
ModelInteraction  consumes K1, establishes K2
ModelInteraction  consumes K2, establishes K3
ModelProcessFinish consumes K3
```

The process has its own separate domain. It never consumes the world
projections A/B that its Cut describes.

When a new Cut comes from another observer, there are **two distinct causal
occurrences**: `DiscloseCut` in the source observer's authority domain, and
`Acquire` in the Model's private process domain. The receiver's occurrence
names the disclosure as its source. TM does not invent an atomic commit
spanning both domains; see [`CUT_EXCHANGE.md`](CUT_EXCHANGE.md).

Meanwhile, the enclosing Eidos meta-protocol retains the existing distinction:

```text
Elaborator(C1) + Elaborator(C2)
    -> admitted possibility + Actualizer(R)

Actualizer(R) + participant projections
    -> authoritative world Occurrence
```

Executing a Model—including delegated calls—does not bypass this boundary.

## Consultation authority

An executor Name identifies an inspectable `ModelExecutor` Value. **That
does not authorize running it.**

First, the host explicitly registers an adapter for that exact executor Name.
Second, it explicitly admits that a particular Model may consult that
executor through `authorize_model_consultation(model, executor)`.

Each process genesis description records the admitted executor Names. A process
may only `Consult` those admitted executors, even if it knows the Names of
many other registered services.

The adapter can be implemented by a local subagent, remote process, virtual
subagent, subprocess, model invocation, or a human-managed service. Its
placement is not an Eidos semantic primitive.

## Consultation, acquisition, and handoff admission

All three extensions use explicit host-side bindings rather than treating a
discoverable Name as permission:

- `Consult` requires a registered executor and a Model-specific consultation
  admission.
- `Acquire` requires a registered `CutProvider` and a Model-specific
  acquisition admission, plus a source Cut disclosure supported by live
  observer Discloser authority and addressed to this exact recipient run.
- `Handoff` requires a Model-specific admitted target holder. The successor
  process projection belongs to that target; an old runner may replay the
  historical handoff receipt but cannot progress the new continuation.

The admitted provider, executor, and handoff target lists are snapshotted in
the process's immutable genesis description. The new Context points to its
previous Context and the causal disclosure that justified its expansion.

## Durable intermediate states and recovery

The semantic history is ordinary named Values:

```text
ModelDerivation D
   |
   +-- ModelProcessOutcome O
           |
           +-- ModelProcess domain P
           +-- ModelCheckpoint S0  (suspended continuation)
           +-- ModelInteraction I1
           |     +-- ModelPreparedStep (request + response)
           +-- ModelCheckpoint S1
           +-- ModelInteraction I2
           |     +-- ModelPreparedStep (request + response)
           +-- ... 
```

The runner durably binds a checkpoint **before invoking an external responder**.
It binds each prepared answer before committing its generic interaction
occurrence. On retry, it reuses that prepared answer and the idempotent
occurrence receipt.

A test simulates a crash **after** a consultation's TM occurrence was
committed but **before** Praxis resumed. A new runner recovers the checkpoint,
prepared answer and occurrence, resumes the same continuation, and does not
reinvoke the specialist.

This is crash recovery at a specific supported seam, not a blanket
exactly-once claim. A crash between external work and durable preparation can
still cause external work to be repeated. Process genesis and its first
checkpoint also currently use separate transactions; the initial process can
be left with an orphaned live local capability if interrupted at that point.

The executable process outcome records every informational occurrence and
checkpoint. The enclosing `ModelDerivation` points to its outcome Name.
A generic semantic lens can inspect the program, input, suspension, replies,
receipts, and eventual proposal without a ModelProcess-specific graph walker.

## Progressively understanding two Cuts

One end-to-end test creates two independent observer Cuts, each containing one
participant projection. Neither observer's Cut alone can derive a joint
Reaction.

A specialist receives **both Elaborator projections by delegation**.
Its process reads Cut C1, then C2, then consults a registered specialist using
the two grounded facts. It returns the new joint fact.

The outer Elaborate consumes both delegated Elaborator capabilities and
produces the corresponding Actualizer projection. A and B remain live.

The world only advances when a separate Actualize operation consumes its
Actualizer and the required participant projections.

This is the sense in which a Model process can progressively build its own
understanding **without acquiring the world it understands**.

## Deliberate limitations

This remains a finite synchronous driver over durable Eidos continuations,
not a distributed scheduler or an authenticated remote actor transport.

- `Acquire` currently requests a Cut whose Name the process already knows;
  unknown-Cut discovery and provider refusal are still future protocols.
- Provider callbacks execute in a trusted host. The observer's source-domain
  occurrence authenticates local linear authority, but this is not
  cryptographic proof of remote capability possession.
- Inspect scope is explicit Context admission, **not** arbitrary graph
  reachability. A Name embedded in Model code cannot grant evidence access.
- Context growth is monotonic, and each new Cut needs recipient-bound
  `CutDisclosure` evidence. The Context/Model proposal can still make
  unsound epistemic claims; none of this makes a general proof checker.
- A local Model process can be handed to another configured runner, but
  automatic network transport and distributed scheduling remain absent.
- A bounded `max_steps` is not a general token/currency/time resource
  scheduler.
- External providers/executors may be side-effecting. Some commit/preparation
  crash windows are recoverable by idempotent replays; exactly-once external
  execution is not guaranteed.
- Genesis and first checkpoint remain separate transactions, leaving a
  possible orphaned process capability on interruption.
- Only a later `Actualize` against the world's live participant projections
  can authoritatively change the world.

The next pressure test is to allow an observer to **defer or refuse**
disclosure, and to let a Model seek an initially unnamed Cut using a resumable
relational discovery protocol rather than an immediate host callback.
