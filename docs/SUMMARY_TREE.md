# Semantic hierarchy / summary tree

This is now the implemented v0 shape for Eidos's derived semantic layer, plus
the constraints for how it should evolve incrementally.

## Principle

Higher levels are not the same summary repeated at a larger scale.

> **Importance should sharpen upward.**

A low-level episode may retain implementation mechanics. A parent arc should
retain only what later proved durable. A thread-level node may omit entire
branches that were locally busy but globally irrelevant.

The raw trace remains immutable evidence. Every semantic layer is replaceable,
versioned interpretation.

## Implemented levels

```text
raw native evidence
        ↓ deterministic projection
weighted story beats
        ↓ low-effort leaf interpreters
episode / recurrence nodes
        ↓ medium-effort synthesis
durable arcs
        ↓ medium-effort synthesis
thread-level map
        ↓ later / optional
cross-thread structures
```

Each derived node retains support into the layer below. Support may be
non-contiguous. Ultimately every path can descend to raw trace sequence ranges.


## Global hindsight before local enrichment

Before any leaf worker runs, one medium-effort retrospective pass produces a
compact global prior: durable arcs, dead ends, surprises, and attention guidance.
Every parallel leaf receives that ex-post wisdom plus only its local weighted
evidence. The brief is explicitly defeasible: a local worker can rescue a small
moment that the global pass underestimated.

## Reasoning-effort budget

Routine summarization should not inherit a "more is better" policy.

| level | default effort | rationale |
| --- | --- | --- |
| deterministic story reducer | none | structural plumbing, not authorship |
| leaf / window interpretation | `low` | numerous, constrained, structured output |
| arc / tree merge | `medium` | reconciliation and abstraction deserve more thought |
| disagreement adjudication | `high` | rare, only when instability matters |
| routine summary | never `xhigh/max/ultra` | unjustified cost for this task |

A user may override the policy. The default should remain cheap.

Model choice follows the same principle. Eidos may use a catalog model only
when the model itself clearly advertises a cheap/fast/small role and supports
the required effort. Otherwise it inherits the parent model rather than guessing.
`EIDOS_SUMMARY_MODEL` can explicitly pin a model.

## Subagents

The useful form of multi-agent summarization is map/reduce, not three personas
all re-reading the same history.

### Leaf stage

Several Eidos-managed ephemeral workers independently process overlapping
semantic-mass windows in parallel:

```text
history
 ├─ fork A → leaf nodes
 ├─ fork B → leaf nodes
 ├─ fork C → leaf nodes
 └─ fork D → leaf nodes
```

These are cheap, low-effort, read-only semantic workers. They should not call
tools or mutate the source world. Parallelism is bounded.

### Merge stage

One stronger narrator consumes the leaf Values plus the high-priority
conversational spine and writes the next semantic level:

```text
leaf A ─┐
leaf B ─┼─ medium-effort synthesis → durable arcs
leaf C ─┤
leaf D ─┘
```

The merge can reject low-value leaves entirely. This is where importance
sharpens.

### Adjudication

Only meaningful disagreement should trigger another model pass. Confidence
numbers alone are not sufficient reason to spend more inference. Useful
triggers include:

- two candidate structures disagree about a major boundary;
- later evidence reverses the interpretation of an important branch;
- a supposedly low-value execution episode becomes causally central;
- a merge is unstable across repeated low/medium passes.

## Hindsight

Every semantic artifact is horizon-relative.

A node produced at horizon 800 can be superseded by a node at horizon 1400
without changing the evidence it cites. The system should preserve both when
useful:

```text
episode@800  → "investigating clipboard behavior"
episode@1400 → "automatic detection was the dead end that motivated explicit OSC 52"
```

This is not inconsistency. It is retrospective interpretation.

## Incremental operation

Once Eidos is the live substrate, the tree should not be repeatedly rebuilt
from scratch.

- new trace records update the local story-beat frontier;
- completed activity schedules affected leaf workers;
- only ancestors of changed leaves become eligible for re-synthesis;
- stable branches remain structurally shared;
- occasional retrospective passes may revisit older branches with new evidence.

This should eventually look more like incremental compilation than periodic
"SUMMARIZE THE WHOLE CHAT" prompts.

## Current v0 relation

The current `SemanticTreeBuilder` performs:

1. one medium-effort global hindsight pass over the source history;
2. deterministic semantic-mass window planning;
3. bounded parallel low-effort leaf enrichment over every region;
4. recursive medium-effort reducers whose groups are packed by semantic mass;
5. one final medium-effort thread synthesis;
6. persistence of the surviving recursive tree with raw trace support.

A leaf may produce no episode. Reducers may discard low-value children. This is
intentional: coverage is exhaustive at the evidence-reading layer, while
narrative bandwidth becomes increasingly selective upward.

The older sequential-horizon observer remains in the codebase as an experiment
and primitive, but it is no longer the default `codex-observe` path.

The next major step is incremental reuse: preserve stable leaf/subtree Values
across new live evidence instead of rebuilding the whole tree.
