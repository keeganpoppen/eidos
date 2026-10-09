# Acquiring a Cut across observer domains

> **To know a Cut's Name is not to have acquired its evidence. To acquire its evidence is not to acquire its authority.**

The first executable exchange lives in
[`cut_exchange.py`](../src/eidos/cut_exchange.py) and
[`model_process.py`](../src/eidos/model_process.py). It is an intentionally
small but causal protocol between an observer supplying an addressable Cut and
a running Model process requesting additional context.

## Two authority domains, two occurrences

The observer's authority domain and the Model process's private domain are
distinct. Trusted Machinery commits locally within one authority domain; it
does not pretend to provide a distributed atomic transaction across both.

The observer explicitly consumes an ordinary `Discloser` projection to
authorize a source-domain occurrence:

```text
observer's Cut C2
    + observer's live Discloser K
        |
        | DiscloseCut (source-domain occurrence S)
        v
CutDisclosure {
    cut: C2
    recipient_run: P
    recipient_model: M
    source: K
}
    + successor Discloser K'
```

The disclosure's Value is bound to the **same Name** as its generic authority
occurrence. It cannot be substituted by a forged `CutDisclosure` record: the
receiver checks its named Value against the actual source-domain occurrence,
including its source domain, observer, consumed Discloser projection, Cut,
recipient process, and recipient Model.

The Model performs an ordinary informational Socket operation:

```text
perform processSocket.Acquire(CutRequest {
    provider: CutProvider Name,
    cut: C2
})
```

The receiving runner first checks a separately admitted CutProvider binding
for the specific Model. A registered provider Name alone does not authorize
acquisition. Its provider adapter returns the source disclosure occurrence S,
whose source-domain authority is then verified.

The receiver's next ordinary `ModelInteraction` occurrence consumes **only
its private ModelProcess projection** and names S as its causal source.
That establishes a directed causal relationship:

```text
Source world domain:    DiscloseCut S
                               |
                               | addressed evidence
                               v
Model process domain:   Acquire occurrence A
                               |
                               v
                       successor process Socket
```

There is no simultaneous remote observation assumption and no global commit
between the two domains. A source disclosure may exist before the receiving
Model has incorporated it.

## A new Context, not a mutation of the old world

The `Acquire` result is an `AcquiredContext` Value pointing to an immutable
successor `ElaborationContext`:

```text
Context C0:
    Cuts = {C1}

Acquire Cut C2 (source = S)

Context C1:
    parent = C0
    acquisition = S
    Cuts = {C1, C2}
```

Each new Context is independently addressable. Its ancestry is monotonic:
new contexts may add Cuts, but cannot silently discard the Cuts visible to
their parents. An added Cut requires a `CutDisclosure` Value naming precisely
the new Cut. The receiving runner also verifies that its named disclosure
corresponds to the source-domain authority occurrence.

A process checkpoint carries the current Context Name. Subsequent `Inspect`
and `Consult` operations use that Context, and the final ModelProcessOutcome
records it. That outcome links the Context back into the enclosing ModelDerivation
and Elaboration provenance graph.

Importantly, **the outer Elaborator still has only the world projections it
was actually delegated**. Acquiring C2 as knowledge does not authorize
actualizing a Reaction requiring C2's participant projections. Tests exercise
a richer Model result obtained from C2 while the outer Reaction can consume
only the original C1 participant projection.

## Graph reachability is not disclosure authority

Our generic semantic lens is deliberately indiscriminate about Names inside
Values—including Names mentioned in executable Eidos Closures. This is good
for interpretation, auditing, and debugging. It is **not an access-control
mechanism**.

The ModelProcess runner uses a separate inspection-scope interpreter over
explicitly admitted Context/Cut/Knowledge/Model/Attention bindings. It never
converts the mere appearance of an unacquired Cut Name inside a program into
permission to `Inspect` that Cut.

One test demonstrates both facts simultaneously: the generic lens can find the
Cut Name in the Model's code, but `Inspect` rejects it until the provider
has authorized disclosure and the Model has committed its `Acquire`.

## Handoff of a single linear continuation

A Model can also perform:

```text
perform processSocket.Handoff(HandoffRequest {
    target: "worker:remote"
})
```

The host must have explicitly admitted the target holder for this Model
*before* the process begins. The request is another generic
`ModelInteraction` that consumes the current process projection and
establishes exactly one successor with the target as its holder.

Its captured continuation and current Context remain immutable named Values.
The former holder can replay the already-completed handoff receipt, but
cannot advance the successor continuation. A new runner configured for the
target holder can load its checkpoint and resume.

This is a local executable handoff of live, linear process authority. It is
not yet a cryptographically authenticated transfer across independent remote
machines. Identity and authorization are still trusted host configuration.

## Recovery and failed deliveries

A source-domain disclosure may commit before its immutable semantic Value is
bound. Replaying the same request ID reuses that already-committed disclosure,
even though the original Discloser projection was spent, and completes the
Value binding. A different request ID cannot reuse the spent projection.

For the receiving process, the prepared response is persisted before its
generic interaction commit. A crash after that commit but before Praxis resume
can recover the original receipt and continuation without repeating the
provider or specialist work.

There remain other crash windows: an external provider may run before a
prepared reply is durable, and the ModelProcess genesis/checkpoint creation
is not yet one atomic unit. Provider adapters must therefore be deliberately
idempotent if their side effects matter. The supplied `DiscloseCut` helper
uses a generic TM idempotency key for exactly that local source occurrence,
not for arbitrary external network effects.

## Next pressure point

The exchange and handoff protocols work as synchronous, in-process
orchestrations over separately durable authority domains. A natural next
step is to replace the host callback with an addressable, pending relational
session: the provider can suspend, an observer can admit or refuse disclosure,
and the receiving Model can incorporate the result later.

Then an acquired Cut need not be known even by Name when the Model begins;
discovery itself could become another resumable Eidos protocol.

It would also be worth representing *model-side evidential updates* from a
newly acquired Cut as explicit Knowledge Values, rather than only inspecting
its structural Cut Value and asking a specialist to interpret it. That is
separate from—and cannot imply—acquisition of world authority.
