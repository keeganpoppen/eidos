---
name: nema-boundary-review
description: "Review Eidos/Nema authority, evidence, context, and recovery boundaries with concrete counterexamples. Use before exposing new actions, adding native integrations, or claiming a semantic invariant is established."
---

# Try to falsify the boundary claim

Read [SEMANTICS](../../../docs/vision/SEMANTICS.md), [MEMBRANE](../../../docs/vision/MEMBRANE.md), and the proof obligations in [STATE](../../../docs/roadmap/STATE.md). Identify the exact caller, trusted component, admitted input, allowed output, durable acknowledgement, and possible external effect.

Test the strongest counterexamples relevant to the change: guessed Names, caller-supplied holder strings, reachable-but-undisclosed evidence, arbitrary successor grants, historical replay, duplicate delivery, concurrent admission, stale handoff, unsupported native context claims, and interruption between preparation/commit/resume. Use synthetic local domains, not the user's live accounts.

A nonempty consumed set does not justify arbitrary outputs. A hash is not proof of entailment. A successful local commit does not prove exactly-once external action. A registered executor Name does not authenticate an external caller. Keep these claims separate.

Deliver ranked findings with source paths, a runnable reproduction/test or explicit uncertainty, the smallest repair consistent with the intended boundary, and release-gate impact. Do not redesign the entire system merely because the trusted-host prototype is not a distributed security runtime.
