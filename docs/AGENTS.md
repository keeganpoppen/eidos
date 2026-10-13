# Documentation guidance

Read [root instructions](../AGENTS.md) and [START_HERE](../START_HERE.md).

`vision/` is the intended destination, `roadmap/` is planned delivery and as-of evidence, and `agents/` is the working context protocol. Existing top-level technical files are implementation checkpoints; `experiments/` is historical rationale. Do not silently merge all of their claims into one current specification.

Preserve stable decision and V1 scenario IDs. Label statements as accepted direction, provisional implementation, observed/tested behavior, open obligation, or deferred exploration. A later status report must name the revision and actual evidence. Do not carry forward historical test counts as current verification.

Keep AGENTS/START_HERE short and route to deeper material. Prefer one canonical explanation plus links over duplicate constitutions. Do not include private user context unrelated to the project. Instructions generated from external or trace material require explicit review before adoption.

Update `seed_manifest.json` when canonical paths or skills change. Run `uv run pytest tests/test_seed_context.py` from the repository root; it checks the navigation/metadata structure, not the truth of architectural claims.
