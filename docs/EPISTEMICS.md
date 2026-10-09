# Situated knowledge, models, and attention

> **Understanding can change the adjacent possible without changing the causal authority of the world being understood.**

The first implementation of this idea lives in
[`src/eidos/epistemics.py`](../src/eidos/epistemics.py). It is a small
pure interpreter over ordinary, named Eidos Values, not a new subsystem inside
Trusted Machinery.

## An observer's context is a Value

An epistemic context has an identity (its Name), a set of observer-relative
causal Cuts, an optional parent Context, and first-class situated Bindings.

Three ordinary Roles select the ingredients of one elaboration:

- `elaboration/knowledge` binds Names of Knowledge Values (claims plus addressable grounds);
- `elaboration/models` binds Names of Model Values (interpretable inference rules and sources);
- `elaboration/attention` binds a Name of an Attention Value (inference budget and optional model focus).

These bindings are ordinary Core `Bindings` inside an ordinary
`RecordValue`. None is an authority-bearing projection, and none adds
permissions to an observer.

A new context may reference a parent and extend its knowledge or models, or
rebind attention. The old Context remains immutable and inspectable.

## Progressive understanding, executable

Suppose A and B are still watching the same sky. The same Cut(s) and
participant capabilities are available throughout:

```text
Context C0:
    Knowledge:  observed sky pattern
    Models:     none
    Attention:  0 inferential steps
         |
         v
    Possible: SimplyLook

Context C1 extends C0:
    Model:      astronomy
    Attention:  1 inferential step
         |
         v
    Inferred:   triangulated pattern
    Possible:   SimplyLook

Context C2 extends C1:
    Attention:  2 inferential steps
         |
         v
    Inferred:   triangulated pattern
                recognizable pattern
    Possible:   SimplyLook, RecognizePattern
```

The protocol already describes `RecognizePattern` as a possible Reaction
whose preconditions include the epistemic fact `sky:recognized`.

The Model does **not** add a new Reaction to the protocol. It only lets an
Elaborator derive a fact satisfying a pre-existing epistemic precondition.
The required A/B projections still have to be present, and Trusted Machinery
still requires them to be live before Actualization succeeds.

For this first pressure test, Models contain ordinary positive implications:

```text
observed pattern       -> triangulated pattern
triangulated pattern   -> recognizable pattern
```

Inference has a deterministic, finite, attention-bounded execution and
records each step's source Model, rule index, conclusion, and premises.

## Joint understanding

Knowledge Values may cite different Cuts as their grounds. A Model can relate
facts that the original observers separately acquired.

A specialist may receive the ordinary Elaborator projections for C1 and C2
through delegation, combine those Cuts, and apply a named Model:

```text
Observer O1: Cut C1 -> Knowledge K1  ---\
                                        +--> Model M --> Joint Possibility R
Observer O2: Cut C2 -> Knowledge K2  ---/
```

The specialist does not acquire the world merely by learning about it.
Delegation transfers only the explicitly designated Elaborator authority.

The joint meta-protocol operation remains an ordinary Eidos perform over an
ordinary Socket. Its committed Elaboration Value names the epistemic Context;
that Context names its parent, Knowledge, Models, and Attention. A semantic lens
can therefore navigate the complete provenance graph later.

## Observation, inference, and authority are distinct

Knowledge is a claim with grounds. A Model is a set of inference rules. A
derived fact is an inference consequence **conditional on those claims and rules**.
None of these is asserted to be infallible or to constitute a physical-world
event.

An Elaborator's recorded result says what it inferred under its own situated
Context. A protocol may then admit that result as a possible Reaction under
whatever Elaborator authority was delegated to it.

An Actualizer must still participate in a separate authority transaction.
Trusted Machinery's ordinary commit path consumes live projection
capabilities; it does not derive astronomical truths, execute Models, or
accept knowledge Names as substitute authority.

## Historical reinterpretation

An old Cut remains accessible after its projection capabilities are spent.
A later, more capable Context can therefore re-elaborate the same past Cut and
derive additional **counterfactual possibilities**.

Such retrospective understanding cannot admit another authoritative
occurrence with spent Elaborator / participant projections. This is tested:

> **Later understanding may improve the model of an old world; it does not resurrect the authority that world once contained.**

## Executable Models

The limited implication interpreter remains available, but it is no longer the
only inhabitant of the Model Role.

See [`MODEL_EXECUTION.md`](MODEL_EXECUTION.md) for the common
`ModelInput -> ModelProposal -> ModelDerivation` contract. Its current
implementations are:

- declarative implications;
- a first-class serializable Eidos Closure realized under situated Model Roles;
- an explicitly registered delegated executor, including a subprocess adapter;
- a resumable process Closure that can `Inspect`, `Consult`, `Acquire` a newly
  disclosed Cut, or `Handoff` its live continuation to another holder.

They can derive the same epistemic fact from the same Context without creating
or transferring any world projection authority. An Elaboration commits their
derivation Values as separately named, inspectable provenance.

The [`CUT_EXCHANGE.md`](CUT_EXCHANGE.md) protocol shows how an observer
can explicitly disclose a Cut to a running Model. Its new Context is immutable,
parent-linked, and retains the authoritative source disclosure Name. Merely
knowing a Cut Name—even if it appears inside an Eidos Closure—does not confer
inspection rights in the scoped Model runner or authority over the Cut's live
participant projections.

The generic semantic lens now traverses first-class Role Bindings, closures,
and other Eidos dataclasses as well as RecordValues, so the input context,
selected Model, actual inference steps, and executor receipts are addressable
after the fact.

## Current limits

The declarative interpreter remains a small positive propositional calculus.
The Closure/external execution bridge is deliberately not a full proof checker:
proposed conclusions require *recognized premises*, but those premises alone
do not mechanically establish entailment for arbitrary executable Models.
Such results are attributable assertions by an admitted Elaborator, not
infallible descriptions of external reality.

Delegated execution is selected by an explicit host-side registration. A Model
Executor Value is a description, **not** automatic permission to run remote
code. The subprocess transport is not sandboxed; external execution can be
nondeterministic or side-effecting, and exactly-once execution is not promised
across retries.

There is also not yet a full attention/cost scheduler: accepted inference
steps are bounded, but remote cost and cancellation need explicit placement
policies. The Actualizer remains a distinct live capability path through
Trusted Machinery.
