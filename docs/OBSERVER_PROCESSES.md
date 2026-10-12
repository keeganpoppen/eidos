# The responding observer is an Eidos process

> **A requester and a responder can each have a durable, self-realizing history, and neither is the other's scheduler.**

This pressure test makes the observer-facing side of
[`DISCOVERY.md`](DISCOVERY.md) executable in the same ordinary Eidos
`Perform → Suspended → Reaction → Continuation` vocabulary as the requesting
Model.

Implementation: [`observer_process.py`](../src/eidos/observer_process.py).
The current test suite exercises the two participants together in
[`test_observer_process.py`](../tests/test_observer_process.py).

## One question, two independent processes

The requester has already committed a named `DiscoveryInquiry` and
suspended on `AwaitDiscovery`. The source observer may accept the inquiry
using the live `Discloser` projection in its authority domain. This is still
an **explicit host-admitted acceptance act**, which establishes one linear
`InquiryResponder` projection.

The observer can then execute an ordinary first-class Eidos Closure:

```text
ObserverInput {inquiry: Q, context: C_source, question}
           │
           ▼
perform responder.Inspect(Cut C_source)
           │
           └─ ObserverInspect → successor InquiryResponder
                              │
perform responder.Defer("need more context")
           │
           └─ DiscoveryDefer → successor InquiryResponder
                              │
perform responder.Consult(specialist)
           │
           └─ ObserverConsult → successor InquiryResponder
                              │
                       pure Eidos If
                       /           \
                 Offer(Cut)        Refuse
                       \           /
                   terminal source occurrence
```

The program decides whether to offer or refuse based on the specialist's
ordinary, inspectable `ObserverAdvice` Value. A new pure, serializable Eidos
`If` term implements the local branch; TM does not interpret the advice.

Every `Inspect` and `Consult` is a **generic TM occurrence in the source
authority domain** consuming the current InquiryResponder and establishing
its one successor. `Defer`, `Offer`, and `Refuse` use the existing
source-domain discovery decisions and the same responder chain.

The requester remains suspended through inspection, consultation, and
deferral. It resumes only after a terminal offer or refusal appears in the
observer's causal history.

## Durable observer self-description

The source side has ordinary immutable, named Values:

```text
ObserverProcess P
    ├── Inquiry Q
    ├── observer's admitted Context C_source
    ├── Closure program
    ├── original DiscoveryAcceptance
    └── allowed specialist executor Names

ObserverCheckpoint S0 -> ObserverCheckpoint S1 -> ...
    └── serialized Suspended Eidos continuation

ObserverInteraction I
    ├── checkpoint that performed the interaction
    ├── actual request and prepared response
    ├── consumed InquiryResponder Socket
    └── successor InquiryResponder Socket

ObserverOutcome O
    ├── terminal source decision
    ├── checkpoint and occurrence history
    └── result produced by the observer's Closure
```

Another source runner can reconstruct the continuation from a named
checkpoint. A test restarts the runner after deferral, receives specialist
advice, and finishes by offering evidence. Another test has the specialist
recommend **refusal** and proves the Eidos conditional takes the opposite
branch.

The source process's Scope is the observer's own admitted Context and its
explicit Knowledge/Model/Attention bindings, interpreted by the same helper
used on the requesting side. Generic Name references inside an Eidos Closure
do not expand that Scope.

## No new species of authority

The observer does **not** receive a special privileged daemon or a second
"model authority" that can answer inquiries independently.

Acceptance creates the linear InquiryResponder projection already defined
by the discovery protocol. Observer execution consumes that projection in
the same source domain, advancing it through actual inspect/consult/defer
occurrences. Source history validation follows that chain and checks both
the generic authority occurrence **and its saved Eidos process/checkpoint**.

The visitor (requester) has its own, separate ModelProcess projection in its
own authority domain. The world participant projections are consumed by
neither epistemic process.

```text
requester domain:  Discover ─── Await(Q) ────── Acquire / Refuse
                             ▲                    │
                             │ causal answer      ▼
source domain:     Accept ─ Inspect ─ Defer ─ Consult ─ Offer/Refuse
```

There is no global frontier or cross-domain atomic commit.

## Recovery

Observer consultations have durable `ObserverPreparedStep` Values.
The prepared external answer is bound before the source-domain authority
commit. If a host crashes after committing `ObserverConsult` but before
Praxis resumes, another runner can reuse the prepared answer, replay the
idempotent generic occurrence, bind its semantic event Value, and reconstruct
the next checkpoint without rerunning the specialist.

A specific test injects that failure window.

This does **not** make arbitrary specialist invocations exactly-once: a
crash between an external call and preparation may still repeat external
work. The initial acceptance, process descriptor, and first checkpoint are
currently separate transactions; one can be interrupted before the
remaining records are bound, although the acceptance itself can be replayed
idempotently with the same request ID.

## Authority and epistemic limits

- Initial observer acceptance is still a host-admitted action. The observer
  then governs its own deliberative Eidos continuation and terminal response.
- Consultation requires an explicitly admitted executor binding in the
  observer process description. Merely knowing an executor Name grants no
  invocation authority.
- An observer may offer only a Cut in its own admitted Context, and the
  source decision also verifies the Cut belongs to the provider's observer
  and authority domain.
- A foreign world Socket cannot be used as an InquiryResponder. The runner
  refuses terminal operations targeting anything but the current responder.
- The source and requester holders are trusted local identity strings, not
  cryptographically authenticated remote principals.
- Source workers are invoked synchronously by a host adapter. A future remote
  transport needs delivery, resource budgets, and authenticated authority
  transfer while retaining the same serialized continuation semantics.
- An `ObserverAdvice` is an attributable recommendation. Its truth and
  judgment are not guaranteed by TM.

## The shared process runtime

That mechanical unification is now implemented in
[`PROCESS_RUNTIME.md`](PROCESS_RUNTIME.md). Both participants name an
ordinary immutable ProcessProtocol Value defining their local Socket role and
legal operations; both advance through the same `ProcessRuntime`.

Source-side `Inspect`, `Consult`, and `Defer` establish successor
InquiryResponder projections. `Offer` and `Refuse` are terminal *because
the named protocol describes them as such*. No observer special case is
built into Praxis or the shared continuation engine.

The existing Model/Observer runner names survive as semantic interpretation
facades: they know what an Inquiry, Cut, consultation, or Context means, while
the shared machine does the checkpoint, authority, Reaction, and resume
work. A single host can interleave both protocols solely through the generic
registered-protocol entry point. A third unrelated Role is tested against
that same runtime.

What remains distinct is semantic authority genesis (including the observer's
initial Accept) and the host realization of each protocol operation. Those
are not yet a fully derived Eidos operation-handler library, nor remotely
authenticated actors.
