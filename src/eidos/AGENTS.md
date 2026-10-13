# Eidos implementation guidance

Read [root instructions](../../AGENTS.md) and the relevant [semantic contract](../../docs/vision/SEMANTICS.md) or [native membrane](../../docs/vision/MEMBRANE.md).

There are two paths to integrate deliberately: native trace/UI work and the semantic process/authority experiments. Do not replace one with the other by assertion. Preserve stable evidence references, native IDs, and explicit source/coverage distinctions.

Keep protocol/role semantics above the narrow authority mechanism where feasible. The generic commit API is privileged: callers must not invent output authority merely by supplying any live input. Local holder strings and registry entries are not authenticated remote principals.

Use ordinary Values and explicit continuation state where they support a real workflow. Keep lexical closures, situated Bindings, serialized checkpoints, native thread handles, and live authority distinct. Validate failure/terminal/pending states and versioned serialization. Do not make every helper a reflective object solely for symmetry.

`trusted.py`, `api.py`, and shared reference envelopes are contention points. Assign one owner per integration cycle. Preserve legacy behavior until a tested migration replaces it. Do not remove archived tests from history simply to claim progress; new live paths need their own acceptance evidence.

Use uv and the existing test conventions. Native execution is resource-consuming and may affect files; use synthetic/mock fixtures by default and explicit isolated real-native probes for integration claims. No private traces, tokens, or auth state in commits.
