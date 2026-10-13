# Test guidance

Read [root instructions](../AGENTS.md), [V1](../docs/roadmap/V1.md), and [STATE](../docs/roadmap/STATE.md).

Separate pure unit/serialization tests, local protocol simulations, native integration probes, rendered UI checks, and product evaluations. Name the scope of evidence; a local fake process does not establish distributed security or complete native recovery.

Add counterexamples for authority inflation, guessed identifiers, stale history, duplicate delivery, concurrent admission, and interruptions at external-effect boundaries. Keep fixtures synthetic or sanitized. Never require private credentials or spend the owner's native subscription in the default unit suite.

Seed-context tests should validate links, metadata, and discoverability without freezing prose or claiming documentation proves semantics. Archived experiments stay outside the active test tree unless deliberately reinstated with a migration rationale.
