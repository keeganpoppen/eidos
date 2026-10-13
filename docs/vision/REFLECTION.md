# Reflection: understanding, alternatives, and recursive improvement

**Status:** design direction. Autonomous change is not the goal; evidence-based improvement of work is.

## R1. Understanding is situated work

Available cuts, knowledge, models, and attention affect what an observer can infer. A specialist may relate two cuts that neither observer could combine alone. The astronomy analogy illustrates this: receiving similar evidence is not having the same understanding. It does not imply that inference alters physical truth or grants power over the observed world.

Knowledge, Model, Attention, Context, input, proposed claims, and derivations should be addressable Values. Models may be rules, closures, native agents, external services, or persistent processes. Preserve actual inputs, inferred conclusions, and unresolved uncertainty across every realization.

## R2. Deepening is not merely adding tokens

Semantic depth, model competence, evidence selection, inference budget, context-window volume, latency, and cost are different axes. A better aperture may use fewer tokens. Hindsight summaries should foreground durable decisions and user intent rather than allocating importance in proportion to tool-log volume.

Support coarse-to-fine traversal, alternative lenses, selective retrieval, noncontiguous context, and role-specific projections. Keep drill-down to raw support. A retrospective synthesis must not be mistaken for what an actor knew at the time.

Eventually Attention needs explicit accounting for scheduled/running/pending/cancelled work, deadlines, cost, concurrency, and diminishing returns. The highest effort or largest agent count is not automatically best. Use substantial effort for judgment and integration; stop expansion when it no longer changes a decision or test.

## R3. Recorded, reinterpreted, and counterfactual worlds

The recorded world is what evidence supports happened, including gaps. The reinterpreted world is a later model of that evidence. The counterfactual world is an alternative proposed or executed under changed context, code, policy, lens, or mocked effects, with its own experiment identity and authority.

Later understanding may improve the model of an old world; it does not resurrect the authority that world once contained. Native historical forks are new work grounded in old history. Mock replay is not a repeat of the original external event. Conversation branching, filesystem isolation, and effect authorization must be explicit and separate.

## R4. The improvement loop

Start with context quality and interruption recovery:

```text
select recorded episodes and failures
    -> identify a recurring missing relation/context/affordance
    -> propose a lens, instruction, context builder, wrapper, or UI change
    -> record rationale, patch, and expected improvement
    -> compare baseline and isolated alternatives
    -> review regressions and tradeoffs
    -> admit a versioned change
    -> observe subsequent work
```

An improvement proposal names source evidence, old version, concrete change, target behavior, counterexamples, evaluation method, resource cost, adoption decision, and rollback. “Better summary” must not silently rewrite future contexts.

Auditors use the same workbench. Their own selection, prompts, calls, conclusions, and adopted patches are visible to a later audit. Seek reusable shared structure and convergence, not a new metaobject framework for every reflective session.

## R5. Evaluate outcomes, not agreeable prose

Measure reorientation time, source precision and sufficiency, recovery of controlling decisions and unresolved questions, quality of the next action, unwanted duplicate effects, latency/cost, and ability to inspect or reverse an adopted change. Use held-out or blind comparisons where practical. Separate protocol correctness tests from product usefulness evaluations.

Avoid hindsight leakage in claimed prospective replay. Name experiments that intentionally use later knowledge. A judge model has its own context and limitations; it is not an oracle. Keep rejected alternatives and failed experiments as evidence. A lower score or a useful counterexample can be more valuable than a flattering report.

## R6. Code and instruction evolution

Rebind resolvers, models, wrappers, compositors, or context builders through versioned Values when contracts allow. Distinguish descriptive re-elaboration from resuming live authority under changed code. Keep old code identity and define migration/admission explicitly.

AGENTS.md and skills participate in this world, but are not self-authorizing. Generated policy changes require reviewable provenance and tests. Untrusted trace content can inform a proposal; it cannot promote itself into repository instructions. Broad self-modification is not V1's default.

## R7. This seed is part of the experiment

Converting a valuable but fragile conversation into durable repository context is an early instance of Nema's purpose. Improve this seed through use. Preserve its commitments, correct mistaken inferences, update stale status with evidence, and keep its entry point small.

Success is not the number of skills, agents, or distinctions accumulated. It is whether a fresh session can recover the destination, find relevant evidence, choose a productive next step, and leave a better continuation for the next session.
