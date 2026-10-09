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
perform K1.Inspect(InspectRequest(target=Cut C2))
    |
    Reaction -> inspected Value, successor Socket K2
    |
perform K2.Consult(ConsultRequest(specialist, question))
    |
    Reaction -> specialist proposal/receipt, successor Socket K3
    |
return ModelProposal(...)
```

These are ordinary Core `Perform` nodes. Praxis suspends with a serializable
`Suspended` containing its residual `Continuation`. It has no special
ModelProcess evaluator cases.

The host-side `ModelProcessRunner` only handles two admitted operations:

- `model:Inspect`: read a Name in the transitive semantic neighborhood of
  the original Context/Cut input; return an ordinary `InspectedValue`.
- `model:Consult`: send a `ModelConsultation` Value to an explicitly
  admitted executor adapter; receive an ordinary `ModelProposal` response.

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

This is one finite synchronous driver over durable Eidos continuations.
The existing subprocess/delegated adapters can be used, but this is not yet a
distributed scheduler or a truly asynchronous actor transport.

- Only two informational operations are admitted so far; external discovery
  of entirely new Cuts is not yet represented as an explicit authority-bearing
  observation/handoff protocol.
- A Model can inspect only addressable Values reachable from its submitted
  Context/Cuts; a guessed Name alone does not expand that scope.
- A bounded `max_steps` prevents unlimited informational interactions in one
  run, but this is not a full token/currency/time resource scheduler.
- The in-process host remains trusted to establish which process owns a
  projection. This is not cryptographic proof of remote capability possession.
- The external executor is not necessarily pure or sandboxed, and exactly-once
  execution is not guaranteed across arbitrary crash windows.
- Consultation proposals remain attributable epistemic assertions. Requiring
  known premises does not prove that the proposed conclusion follows logically
  from them.

The next pressure test is to treat a Context-expansion request and a process
handoff as **ordinary protocol operations between nemata**, so a model can
discover an additional causal Cut after it has already begun, transfer its
suspended continuation to another place/agent, and keep provenance and
authority distinct throughout.
