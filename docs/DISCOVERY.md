# Open discovery as a relational protocol

> **An observer can ask about a world they cannot yet name. Another observer can decide what, if anything, to disclose.**

This experiment extends the epistemic Model process with an actual pending
question, not another callback that resolves a previously supplied Cut Name.
Implementation: [`discovery.py`](../src/eidos/discovery.py) and
[`model_process.py`](../src/eidos/model_process.py).

## The requester names a question, not the evidence

A Model starts knowing a provider Name and a question, but **not** the Name
of the Cut it hopes to discover.

```text
perform K0.Discover(DiscoverRequest {
    provider: Provider(O2),
    question: "What else might illuminate my observations?"
})
     |
     | requester-domain ModelInteraction (the request has happened)
     v
DiscoveryOpened { inquiry: Q }
     |
     v
perform K1.AwaitDiscovery { inquiry: Q }
     |
     | remain suspended; K1 stays live
     v
                 ... an observer considers Q ...
```

The first operation commits an ordinary generic occurrence over the
requesting Model's private process projection and returns one permanently
named `DiscoveryInquiry` Value. The second operation is a genuine pending
continuation: repeated checks return `ProcessProgress(pending=Q)` without
consuming the waiting process projection or inventing an answer.

No background scheduler, global observer, or cross-domain lock is required.

The older synchronous Model convenience entry point cannot complete while an
inquiry remains pending. Rather than busy-loop, it raises a typed
`ModelProcessPending` carrying the persisted checkpoint and Inquiry Name. An
orchestrator can resume that process through `ModelProcessRunner.advance`
after the source decision arrives. The current outer `Elaborate` adapter does
**not** yet automatically correlate and resume its own pending attempt across
multiple invocations; that is a separate orchestration step.

## The observer's independent causal history

A `DiscoveryProvider` Value describes the source authority domain and
observer identity. Registering or referencing that Name does not grant the
Model access to the observer's Cuts. The Model must also be explicitly
admitted to discover through that provider when its process domain is born.

The provider can rebuild an inbox with `discovery_inbox(provider=...)`.
This is a derived lens over named Inquiry Values and committed authority
history, not an authoritative mailbox table.

When the observer chooses to engage, they spend a live ordinary
`Discloser` projection in their **own domain**:

```text
Discloser K_O
     |
     | DiscoveryAccept(Q)
     v
next Discloser K_O' + InquiryResponder(Q) S0
```

The source can now decide, through that specific InquiryResponder
continuation:

```text
S0 -- Defer(Q) --> S1 -- Defer(Q) --> S2
                                      |
                            /---------+---------\
                            |                   |
                          Offer(Cut C)         Refuse
                            |                   |
                       terminate S2       terminate S2
```

Deferral is itself a durable source-domain occurrence. It advances the
source's responder authority but does **not** advance the requesting
Model's suspended continuation.

An Offer or Refuse is terminal for that responder. Both consume its last
live projection; neither establishes a replacement InquiryResponder.

**The observer's decision is not an annotation on the requester. It is
a causal event in the observer's own history.**

The acceptance and deferral lineage is validated against generic TM
occurrences and their consumed/established projections. A forged
`DiscoveryAcceptance` or `DiscoveryDecision` Value cannot substitute
for the required source authority.

## Offering previously unknown evidence

An Offer names a Cut selected by the observer *after* the Inquiry exists.
It may only disclose a Cut belonging to the provider's authority domain
and observer.

The source-domain `DiscoveryOffer` occurrence is bound to an immutable
`CutDisclosure` Value, addressed to one requester run, one Model, one
Inquiry, and its source provider.

The waiting Model may now advance:

```text
Source domain:       DiscoveryOffer O, disclosing C
                                  |
                                  | causally cited evidence
                                  v
Requester domain:    AwaitDiscovery(Q) -> ModelInteraction A
                                  |
                                  v
                 AcquiredContext {
                     context: C_new,
                     disclosure: O,
                     cut: C
                 }
```

The receiving process consumes **only** its private waiting Socket,
and its next checkpoint uses a fresh immutable Context:

```text
Context C0: cuts = {C1}

Context C_new:
    parent      = C0
    acquisition = O
    cuts        = {C1, newly discovered C}
```

The old Context still exists. Its own past Cut remains unchanged.
The new Context permits the Model to inspect the newly admitted Cut.

Crucially, the Model's world participant capabilities have **not** changed.
Any subsequent Actualize still requires independently live world authority.

## Refusal, pending, and retries

A Refusal names an authoritative `DiscoveryRefuse` source occurrence.
The waiting Model resumes with `DiscoveryRefused` and retains its
previous Context. The recipient's own ModelInteraction records the
refusal occurrence as its causal source.

While the source is silent or deferring, the request remains pending. The
requester Socket stays live and can be resumed by another runner with the
same admitted holder identity; checking status does not consume it.

Acceptance and terminal decisions have idempotency keys. Replaying the
same request returns the existing occurrence, even after its original
source projection was spent. A *new* answer cannot spend the same
responder capability twice.

This preserves the ordinary TM guarantee within each domain. It is
**not** a cross-domain atomic transaction or a guarantee that external
transport and arbitrary callbacks run exactly once.

## Addressability versus authority

The requester knows the provider Name and eventually the Inquiry Name.
Neither grants source-domain disclosure authority.

The generic semantic lens may reveal a Name inside arbitrary code or
historical Values. That does not confer admission to inspect the named
Cut. ModelProcess inspection scope is derived separately from explicitly
admitted Context/Cut/Knowledge/Model/Attention bindings and expanded only
through verified source disclosure.

Likewise, knowing the Inquiry Name is not authority to answer it. The
source must hold the appropriate live `Discloser` or
`InquiryResponder` projection in the named observer domain.

Thus:

> **Naming a question, answering a question, and incorporating an answer
> are distinct occurrences, with distinct participating authority.**

## Executable pressure tests

[`tests/test_discovery.py`](../tests/test_discovery.py) exercises:

- a Model asking without naming the Cut eventually offered;
- causal issuance and pending `AwaitDiscovery` suspension;
- a derived source inbox;
- observer acceptance and repeated deferrals;
- an authorized Offer and receiver-side Context expansion;
- explicit Refusal, with no Context expansion;
- spent responder authority and replay of accepted/terminal decisions;
- a guessed responder Name or foreign Cut failing source-domain checks;
- a forged acceptance Value failing without its source occurrence;
- a named inquiry failing until the requester actually commits `Discover`.

The earlier [`CUT_EXCHANGE.md`](CUT_EXCHANGE.md) protocol remains valid for
requesting an already-known Cut by Name. This experiment adds the more
general question-first path.

## Current limits

This is an in-process, durable *pull-style* protocol. A future provider UI
or messaging transport can surface the derived inbox and deliver events, but
no actual network messages or autonomous background workers are provided
by this experiment.

Source observer identity is a trusted, local holder string—not a
cryptographically authenticated remote principal. The same authority-local
SQLite TM engine persists both domains, but commits remain domain-local.

Provider and inquiry queries currently scan immutable named Values. Durable
derived indexes can accelerate those scans without becoming sources of
authority.

The code assumes one admitted linear responder chain per Inquiry. Host-side
concurrent acceptance must eventually be serialized as a protocol admission,
rather than relying on an in-process precheck before generic commit.

The responding observer can now itself execute a resumable Eidos
Closure over the existing InquiryResponder projection. It can inspect its own
Context, defer, consult a specialist, and dynamically choose Offer or Refuse
using the ordinary Eidos `If` term. Its continuations, informational
Reactions, and terminal answer remain named and durably inspectable.

See [`OBSERVER_PROCESSES.md`](OBSERVER_PROCESSES.md) for the full source-side
semantics, restarted observer tests, and strict responder lineage checks.

The next worthwhile pressure test is to factor the requester's and
responder's separate host drivers into one general way to interpret ordinary
protocol operations over the Sockets each participant locally possesses.
