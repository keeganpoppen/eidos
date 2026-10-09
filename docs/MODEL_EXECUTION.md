# Executable Models under one Eidos Role

> **Who understands a Cut, and how they do it, is situated. The authority of the Cut remains separate.**

The same Model role can be occupied by an ordinary declarative rule model,
a pure Eidos Closure, a deliberately registered delegated executor, **or a
resumable Eidos process**. Their common input/output contract is made of
ordinary immutable Eidos Values, not host callables hidden inside Core.

Implementation: [`model_execution.py`](../src/eidos/model_execution.py);
orchestration: [`epistemics.py`](../src/eidos/epistemics.py);
meta-protocol bridge: [`meta_protocol.py`](../src/eidos/meta_protocol.py).

## The shared contract

The Context binds Model Names through the existing `elaboration/models` Role.
Each named `Model` Value has one implementation mode:

- `rules`: positive `Implication` Values, interpreted locally;
- `closure`: an ordinary serializable `Closure` executed through `PraxisCore`;
- `delegated`: the Name of an inspectable `ModelExecutor` descriptor, whose
  host explicitly binds it to an executable adapter.
- `process`: a first-class Eidos Closure realized through an explicitly
  admitted process-local authority domain. It may suspend on ordinary
  informational Socket operations, persist its continuation, and resume after
  receiving reactions.

The request to each implementation is an ordinary `ModelInput` Value:

```text
ModelInput {
    context: Name
    model: Name
    cuts: tuple[Name]
    knowledge: tuple[Name]
    facts: tuple[str]
    remaining_budget: int
}
```

The result is an ordinary `ModelProposal`:

```text
ModelProposal {
    context: Name
    claims: (
        ModelClaim {
            fact: str
            premises: tuple[str]
            witness: Eidos Value | None
        },
        ...
    )
    receipt: Eidos Value | None
}
```

The context Name in the response must match the request. Every proposed claim
must provide distinct, nonempty premises. The Elaborator accepts a claim into
its derived facts **only when all of those premises are already known**, and
only while its situated Attention budget permits another inference.

This is validation of *support references*, not verification of logical
entailment for arbitrary Closures or external models. Such conclusions remain
attributable claims made by their Models.

## Resumable Model processes

A Model whose engine is `process` may `perform model:Inspect` or
`perform model:Consult` on its own process Socket rather than returning its
ModelProposal immediately. Generic TM occurrences consume one local process
capability and mint its next projection per step. Each pending computation is
checkpointed as a serializable Eidos `Suspended` Value; received replies,
interaction receipts, and the final proposal are all named and inspectable.

Consultation is doubly explicit: the host must register the executor adapter
**and** admit a Model-specific right to consult it, captured in the process
genesis description. Knowing an executor Name alone permits neither a call
nor access to the observed world's participant authority.

The eventual ModelDerivation links to its ModelProcessOutcome Name, which in
turn links to each checkpoint and informational occurrence. See
[`MODEL_PROCESSES.md`](MODEL_PROCESSES.md) for the lifecycle, crash-window
pressure tests, joint-Cut use case, and limitations.

## What changes between implementations?

Nothing in the ModelInput/ModelProposal semantics.

An Eidos Closure is applied to the ModelInput Value as one ordinary Eidos
computation. It may also use situated Roles:

```text
elaboration/model        -> Name of its current Model
elaboration/model-input  -> current ModelInput Value
elaboration/context      -> current Context Name
```

Its lexical environment is captured, while its Role bindings are supplied at
realization time. It must terminate locally with a `ModelProposal`: an Open
Role or terminal Socket `perform` is not silently executed as pure inference.
For effects or an outside model, the caller must use a delegated executor.

A delegated Model merely names a `ModelExecutor` descriptor. **A Name does
not invoke a process.** The host must explicitly register an adapter for that
exact executor Name, and the meta-protocol driver only dispatches to such an
adapter.

The adapter receives the same ModelInput and returns the same ModelProposal.
It could internally call a local model, subagent, remote process, theorem
prover, virtual subagent, or human workflow. Eidos does not conflate placement
with Model semantics.

A concrete `SubprocessModelAdapter` is included as a pressure test. It takes
an explicit argv (never a shell command interpolated from a Model Value), sends
one canonical Eidos Core serialized input on stdin, and expects one serialized
Eidos Value on stdout. Execution has a timeout and an output-size check.

**It is not a sandbox**. The host authorizing an executable is responsible
for process isolation, filesystem/network permissions, budget, and any external
side effects. TM receives no external process handles and does not know that
a subprocess existed.

## Persistent inspectable derivations

Every invoked Model produces a `ModelDerivation` Value:

```text
ModelDerivation {
    model: Name
    executor: Name | None
    engine: "rules" | "closure" | "delegated"
    input: ModelInput
    proposal: ModelProposal
}
```

A committed Elaboration immutably binds each derivation to a fresh Name in
the **same SQLite transaction** as the ordinary Elaborator authority
occurrence. The Elaboration Value holds those Names. Inference Values also
retain the content identity of the supporting ModelDerivation, their premises,
engine, and witness.

So the graph can be inspected later:

```text
Elaboration E
   +-- Context C -> Cut(s), Knowledge, Models, Attention
   +-- ModelDerivation D
         +-- Model M
         +-- Executor X (when delegated)
         +-- ModelInput (what was actually supplied)
         +-- ModelProposal (claims, premises, receipt)
   +-- Possibility R -> Actualizer projection
```

All graph edges are ordinary Eidos Names and Values. A generic semantic lens
can traverse them without knowing about ModelDerivation as a privileged type.

## Bounded attention and external work

A Model is evaluated **at most once per interpretation**, lazily as needed.
An Attention budget bounds accepted inference steps. For example, if an
earlier rule uses the entire budget, a later delegated Model is not invoked.

This is not yet a general cost scheduler. Real external executors may require
separate token/time/currency budgets and cancellation policies. The local
subprocess adapter has a timeout but doesn't provide resource isolation.

External work occurs **before** the authority commit, and may be
nondeterministic or side-effecting. A retry may invoke an executor again even
when the eventual TM command is idempotent. Its returned receipt and actual
ModelInput are therefore preserved; the current implementation does not
promise exactly-once external execution.

## What the tests establish

- Rules, an Eidos Closure, and a delegated adapter derive the same
  `sky:recognized` from the same grounded observation and Cuts.
- The Closure reads the situated Model/Context Roles under ordinary Praxis.
- A real subprocess uses the same value wire protocol.
- An external Model is never executed solely because its Name is discoverable.
- Wrong-Context proposals, ungrounded premises, and non-local Closure
  suspensions cannot silently become accepted inferences.
- Deeper epistemic elaboration does not touch projection holder or
  live/spent disposition.
- The committed Elaboration links to separately named executable derivations,
  including their inputs, receipts, executor Names, and provenance.
- The Actualizer remains a separate ordinary Socket operation requiring live
  projection authority.
- A resumable process can inspect two observer-relative Cuts, consult a
  separately authorized specialist, and return one ModelProposal after
  multiple durable informational Reactions.
- The process survives a runner restart between interactions; a test also
  injects a crash after TM commit but before continuation resume, and verifies
  that the prepared response is reused.
- A process cannot inspect an arbitrary Name outside its Context or consult
  an executor merely because that executor is registered.


## Next pressure point

The shared interface works, but this is still a *claim calculus*, not a proof
checker or a distributed authorization protocol.

A sensible next step is to allow an executor to return a richer proposed
derivation graph (confidence, alternative interpretations, support for/against,
and tentative claims) without losing the small stable ModelInput/ModelProposal
boundary. Richer derivation should still not imply richer authority.

The more fundamental long-term test is to let a Model be itself an addressable
process with inspectable, resumable intermediate states—not merely a function
from one request to one response—and preserve the same contract across local
closures, subagents, and remote placements.
