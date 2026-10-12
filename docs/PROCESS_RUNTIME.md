# A process runtime over Roles, Sockets, and named Protocols

> **Requester and responder are roles in interactions, not kinds of execution engine.**

The current [`ProcessRuntime`](../src/eidos/process_runtime.py) is one
continuation machine for any local Eidos process. It has no branch for
requesters, responders, Models, observers, specialists, or inquiry decisions.

A process is characterized by **a named protocol, a live local projection, and
an ordinary suspended Eidos computation**.

## ProcessProtocol is an Eidos Value

Each process description binds the Name of an immutable `ProcessProtocol`
Value with the local projection role and legal operations:

```text
ProcessProtocol {
    projection_role: "ModelProcess" | "InquiryResponder" | another role
    operations: (
        ProtocolOperation { name: OperationName, terminal: bool, may_wait: bool },
        ...
    )
    checkpoint_kind: string
    process_alias: string
}
```

The last two fields preserve compatibility with historical
`ModelCheckpoint`/`ObserverCheckpoint` readers. Every new checkpoint
also carries the same canonical `process: Name`, `suspension`, `step`,
`previous`, and `parent_occurrence` relation.

An ordinary ProcessProtocol Value is **semantic description, not permission**.
The host must separately register a realization for its Name, and the
runtime must also verify that the suspended Socket denotes a projection in
the expected authority domain with the expected role.

## One mechanical advancement

The universal progression rule is:

```text
named process + checkpoint + Socket K
    |
    | resolve ProcessProtocol Name
    | verify local authority domain / role / holder
    | verify Operation is legal for this protocol
    v
registered operation interpretation
    |                  \
    |                 Pending (only if protocol permits it)
    v
TM-backed Reaction R
    |
    | verify R's causal inputs equal consumed Sockets
    | verify R actually established the successor Socket
    | verify terminal/nonterminal continuation shape
    v
Praxis.resume(saved Suspended, R)
    |
    +-- Done      --> protocol's outcome interpreter
    |
    +-- Suspended --> one durable successor checkpoint
```

Everything above and below operation *interpretation* is shared.

The protocol interpreter remains responsible for semantics: deciding whether
a Model can inspect a Cut, whether an inquiry can be offered, what a specialist
may consult, and what a resulting Value means. It must ground its Reaction in
the existing generic authority-occurrence substrate; it cannot merely invent
a Reaction Name.

The runtime is deliberately **not** a universal semantic judge. It enforces
the local continuation contract and verifies the mechanical evidence of an
already-committed occurrence.

## Pending is part of the protocol

`ProtocolOperation.may_wait` explicitly allows a handler to return a
`ProcessPending` instead of a Reaction. No authority is consumed; the
existing checkpoint and live Socket remain available.

For the requesting Model, only `AwaitDiscovery` currently declares
`may_wait=True`. The source observer's `Defer` is different: it is an
*actual source-domain occurrence* that consumes one InquiryResponder
projection and produces the next. Thus the requester's pending continuation
and the observer's active deferral history remain distinct.

A third protocol that does not permit waiting cannot return Pending simply
because its interpreter wishes to.

## The same host progresses both parties

The older `ModelProcessRunner` and `ObserverProcessRunner` remain as
**domain-specific interpreters/facades**, but no longer implement separate
continuation engines. Both:

1. bind a named ProcessProtocol during genesis/acceptance;
2. register its interpretation with the shared host runtime;
3. hand the checkpoint to `ProcessRuntime.advance_registered`.

That last entry point resolves the process and its named protocol itself. A
single host can interleave both parties without invoking either specialized
`advance` method.

```text
            ProcessRuntime
                  |
           ProcessProtocol Name
             /           \
        ModelProcess   InquiryResponder
           |                |
      AwaitDiscovery       Consult / Defer
           |                |
        [pending]       Offer / Refuse
           |                |
           +---- causal evidence ----+
```

Nothing requires these two protocols to be exhaustive.

The tests establish a third, unrelated `Echo` protocol that executes a
terminal `Reply` operation through the **same** machine without importing
either Model or observer interpreter. Its result is an ordinary named Value
backed by a generic authority occurrence.

## What has and has not been unified

**Unified:** named protocol resolution; legal local operations; live Socket
role/domain/holder checks; committed-Reaction verification; Praxis resume;
successor checkpoint storage; pending behavior; generic causal lineage; host
registration by protocol identity.

**Still situated:** semantic meaning of each operation; host-side placement
and executor registration; explicit genesis of authority domains; initial
source inquiry acceptance; and meaning of Model/Observer outcomes.

Those distinctions are *appropriate* so long as they are interpreted through
ordinary role/protocol Values, not elevated into another global scheduler or
privileged Eidos syntax.

Currently a trusted local host registers Python interpreters for these
protocols. Naming a ProcessProtocol cannot by itself invoke an external
process, authenticate a remote holder, or grant authority to inspect any
named Value.

There is no distributed atomic transaction spanning the requesting Model's
domain and the source observer's domain. Their occurrences remain separately
authoritative and causally linked.

## Pressure tests

[`tests/test_process_runtime.py`](../tests/test_process_runtime.py) tests:

- an unrelated third Role with its own named protocol and terminal operation;
- invalid operations rejected by the protocol Value before authority changes;
- a projection with the wrong role rejected even with a valid operation Name;
- unregistered protocols not executable merely because their Name is known;
- pending rejected for a non-waitable operation;
- a single host interleaving a requesting Model and responding observer
  **through one generic entry point**, including pending/refusal and idempotent
  replay;
- the same legacy Model/Observer continuations retaining restart, delegation,
  source responder lineage, and authoritative occurrence semantics.

## The next useful pressure point

The two domain-specific facades now contain mostly **semantic operation
interpreters**, not machine loops. Those interpreters can be factored further
into an addressable operation-handler library / protocol elaborator, perhaps
itself an Eidos Value with a Closure and effectful continuation.

But the next pressure test should be chosen by a concrete interaction that
needs composition or delegation—not by assuming that every Python function
must immediately be reified as a metaclass.

The invariant worth protecting is:

> **A nema is a self-realizing process. Its place in an interaction is defined
> by its situated Roles and live Sockets, not by an intrinsic
> requester/responder species.**
