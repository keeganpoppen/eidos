# Semantic hierarchy / summary tree

This is the intended next shape for Eidos's derived semantic layer. It is a
design constraint, not yet the complete implementation.

## Principle

Higher levels are not the same summary repeated at a larger scale.

> **Importance should sharpen upward.**

A low-level episode may retain implementation mechanics. A parent arc should
retain only what later proved durable. A thread-level node may omit entire
branches that were locally busy but globally irrelevant.

The raw trace remains immutable evidence. Every semantic layer is replaceable,
versioned interpretation.

## Proposed levels

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

Several Eidos-managed ephemeral forks can independently process disjoint or
overlapping candidate windows:

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

The current `retrospective` observer is still sequential across candidate
windows because each horizon explicitly revises its previous map. It uses
`low` effort.

The next tree implementation should split that mechanism:

1. parallel low-effort leaf interpreters;
2. one medium-effort retrospective merge;
3. preserve the sequential horizon revision mechanism at the merge level, where
   hindsight is semantically useful and much cheaper.
