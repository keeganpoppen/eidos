# Native admission frontier and subscription prerequisite

**2026-10-13 · implementation base `ad73408a591484728b3080a7500d2f88cf3d951e`.**
This read-only native/source investigation and synthetic worker repair serve V1-05
and V1-12. They do not open live native admission. The inspected executable remains
Codex **0.154.0**, Linux/aarch64, SHA-256
`9b7c1c7abdc26fc3c4f47c77656a8e9121def5483dbae830ef1ee561758448a9`.

Observed in this lane: executable help/version/hash, repository code and retained
sanitized evidence. No app-server startup, credential inspection, model request,
owner-config edit or cloud-policy lookup occurred. Tagged upstream source is source
evidence, not a reproduced build or a new native probe.

## What blocks the existing worker

`NativeLaunch.live_admitted` in [codex.py](../../src/eidos/codex.py) is unconditionally
false. The guard refuses before process creation. Its local source fingerprints
and per-server disabling arguments do not cover remotely supplied configuration.
The earlier [profile probe](NATIVE_PROFILE_0_154_0.json) established that an inherited
MCP subprocess can act before the inventory check, that `-c mcp_servers={}` leaves
inherited entries, and that an explicit named disable suppresses the fixture.
Those remain historical no-model observations.

The missing prerequisite repaired here is separate: the worker had an account
validator but never invoked it. After initialization, a profiled worker now sends
`account/read` with `refreshToken:false`, validates the returned account, and only
then may create a thread. Missing, malformed, unsupported and errored responses
fail before `thread/start` or `turn/start`. Raw responses, including unknown fields,
remain trace evidence. Explicit trusted-host fixture commands retain their prior
behavior. The actual launch guard still refuses before this new code is reachable
with the native executable.

This check acknowledges ChatGPT authentication and the builtin provider's auth
requirement; it does not prove plan entitlement, a particular model's access,
cloud-policy absence, or a permanent account binding. The supported RPC is documented
in [OpenAI's app-server account methods](https://learn.chatgpt.com/docs/app-server).

## Version-specific source findings

| Finding | Exact source at `rust-v0.154.0` | Consequence |
| --- | --- | --- |
| App-server preloads config, creates its auth manager, installs the cloud loader, then loads config again. | [app-server/src/lib.rs, lines 502–541](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/app-server/src/lib.rs#L502) | A later client-side inventory cannot authorize earlier startup behavior. |
| Cloud loading requires backend auth and a business-like, education-like or Enterprise plan. It returns before cache lookup otherwise. | [cloud-config/src/service.rs, lines 50–57 and 183–206](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/cloud-config/src/service.rs#L50), [plan predicates](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/protocol/src/account.rs#L59) | Authentication alone does not imply cloud loading. Personal plans are a narrower candidate; this owner's plan was not inspected. Preserve exact versioned predicates, including their treatment of Team. |
| The loader memoizes its initial bundle; background refresh updates cache for later use. | [service.rs, lines 115–123](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/cloud-config/src/service.rs#L115), [official managed configuration](https://learn.chatgpt.com/docs/enterprise/managed-configuration#how-local-clients-apply-cloud-managed-requirements) | Do not describe every background refresh as immediate replacement of a running process's requirements. Auth/config lifecycle changes still need separate review. |
| App-server CLI supplies default loader overrides. The native loader supports internal override fields, primarily for tests. | [cli/src/main.rs, lines 1353–1363](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/cli/src/main.rs#L1353), [config/src/state.rs, lines 41–61](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/config/src/state.rs#L41) | No supported app-server flag for suppressing all cloud/managed sources was found. The exec command's `--ignore-user-config` is not such an app-server option. Internal Rust fields are not CLI guarantees. |
| Requirements place cloud above system policy; ordinary tables merge recursively. MCP requirements use that regular merge path. | [loader/mod.rs, lines 94–121](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/config/src/loader/mod.rs#L94), [requirements_layers/stack.rs, lines 1–15 and 153–165](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/config/src/requirements_layers/stack.rs#L1) | An empty system MCP allowlist is not proof against additions from a cloud requirement table. |
| Managed feature pins normalize configured values; enabled plugins can start marketplace work during app-server construction. | [managed_features.rs, lines 152–163](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/core/src/config/managed_features.rs#L152), [message_processor.rs, lines 527–545](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/app-server/src/message_processor.rs#L527), [plugin manager, lines 2752–2788](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/core-plugins/src/manager.rs#L2752) | CLI feature disables are not sufficient against conflicting managed requirements. Initialization itself needs an admitted startup environment. |

## Supported options and their limits

- **Retain existing native authentication with explicit local overrides.** This is
  the current candidate. Named MCP disabling has native fixture evidence; a clean
  working directory alone does not remove user, ancestor, system or cloud sources.
  Ordinary configuration precedence is documented in
  [Config basics](https://learn.chatgpt.com/docs/config-file/config-basic#configuration-precedence).
- **Use a separate `CODEX_HOME` with an owner-performed native sign-in.** This can
  isolate native state without copying existing credentials. It does not suppress
  system policy or account-eligible cloud loading. It also needs authorization for
  the new sign-in/state lifecycle; no such operation occurred here.
- **Apply managed requirements.** An empty effective MCP allowlist disables all
  MCP servers, according to [the managed-configuration reference](https://learn.chatgpt.com/docs/enterprise/managed-configuration).
  On this Linux CLI, system requirements live at `/etc/codex/requirements.toml`.
  Editing host policy would affect other clients, while a namespaced policy mount
  needs its own OS-boundary review. Cloud composition and enforced hooks must still
  be admitted. An empty ordinary config map is a different mechanism.
- **Use an independently contained execution environment.** A VM or reviewed OS
  boundary can constrain startup and descendant effects while preserving native
  authentication behavior. This is a candidate implementation, not a verified
  property of temporary cwd, `read-only`, or the presence of `bwrap` on this host.
- **Consider app-owned ChatGPT-plan OAuth separately.** Current official
  [Sign in with ChatGPT OSS guidance](https://developers.openai.com/siwc/token-sharing-open-source)
  describes dynamic registration and owner consent. Its
  [app-server recipe](https://developers.openai.com/siwc/token-sharing-open-source/codex-app-server)
  uses a Responses provider with an app-owned access token and no separate Codex
  sign-in. Therefore a custom provider is not universally synonymous with paid API
  usage. This is a different authentication lifecycle, not permission to extract
  native credentials or bypass managed workspace policy. Compatibility with the
  installed binary and actual plan access remain unprobed; the
  [preview limits](https://developers.openai.com/siwc/token-sharing-open-source/preview-limitations)
  also differ from ordinary native Codex capabilities. Do not silently substitute
  it for the accepted builtin-provider path.

No supported **universal cloud suppression** control was established. Personal-plan
source behavior and the alternate OAuth recipe narrow future research; neither
justifies changing `live_admitted` to true now.

## Necessary guarantee and concrete counterexample

V1 needs an admitted executor whose actual authority is bounded, an attributable
selected packet, durable native correlation, and explicit uncertainty. It does not
require proof of the provider's hidden prompt or literally zero native state writes.
It does require containment or explicit admission of native startup effects; a
later inventory result cannot retroactively grant that authority. Read-only native
commands do not establish packet-only visibility.

Counterexample for the next admission implementation: after local names have been
disabled, supply a synthetic cloud config containing a previously unseen MCP name,
and managed requirements enabling hooks/plugins contrary to CLI disables. A startup
marker or outside effect before client admission falsifies the claimed boundary.
Also compose an empty system MCP requirement with a higher cloud MCP table: do not
treat the resulting nonempty map as deny-all. These cloud cases are source-derived
counterexamples, not claims that this owner's account contains such policies.

## Verification and continuation

The account tests use a fake app-server and test-only profile. They cover null,
API-key, Bedrock, unknown, malformed and errored responses; exact ordering for a
ChatGPT acknowledgement; unknown-field retention; fixture compatibility; and the
unchanged real launch refusal. This tests the worker's admission sequence, not
native account behavior. No public live-gate override was added.

Verified on this branch:

```text
uv run --no-sync pytest tests/test_native_account_admission.py tests/test_native_profile.py tests/test_investigation_worker.py tests/test_round3_native_review.py -q
154 passed, 1 skipped (explicit no-model native probe not enabled)
uv run --no-sync pytest tests/test_seed_context.py
5 passed
git diff --check
passed
```

These commands used `UV_PROJECT_ENVIRONMENT` pointing at the integrator's existing
environment; pytest's repository configuration loaded this worktree's `src`.

Next implementation contract: first establish a supported startup boundary that
survives the synthetic cloud/managed counterexample, record its exact native and OS
versions, then separately authorize a no-model account/configuration probe. Bind
the acknowledged account/provider and admitted configuration to the same process
incarnation before a separately authorized model turn. Do not reinterpret a prior
no-model authorization, cached report or successful unit test as live authority.
The parent integrator owns canonical STATE/handoff updates and final integration.
