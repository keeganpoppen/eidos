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

## 2026-10-13 independent follow-up: exact personal-plan lifecycle

**Source inference only; the production gate remains closed.** This follow-up read
the public `rust-v0.154.0` source cache and retrieved the exact tagged AgentIdentity
and session source files. It made no native, login, credential or upstream-provider
calls. Exact native-confirmed `authMode=chatgpt`,
`account.type=chatgpt`, `requiresOpenaiAuth=true`, and `planType` equal to `plus` or
`pro` define a narrower candidate than admission of all authenticated accounts.
They do not establish entitlement, successful freshness, or permanent plan binding.

The tagged [cloud eligibility predicate](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/cloud-config/src/service.rs#L50)
excludes Plus and Pro under the exact
[plan-family predicates](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/protocol/src/account.rs#L59).
Startup checks eligibility before either cache or network access; refresh checks
it again. The reviewed storage-loader variants still use that service. No bypass
of this bundle eligibility check was identified in those entrypoints. This is not
a proof that every authenticated startup request is a cloud-bundle request or that
the entire application has no other HTTP path.

Three concrete lifecycle limitations qualify a single account acknowledgement:

1. [Managed request auth](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/model-provider/src/auth.rs#L126)
   reads current credentials and checks account ID, user ID and workspace class,
   not exact plan. Plus to Free/Go retains that class. Plus to Business changes it
   and fails this particular provider check; do not claim that provider guard is
   absent. Separately, `auth()` can proactively refresh near-expiry credentials,
   and 401 recovery can reload and refresh immediately. A short turn lifetime
   alone does not rule either out.
2. [`account/read`](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/app-server/src/request_processors/account_processor.rs#L1105)
   discards `refresh_token_if_requested`'s outcome. A transient refresh failure can
   leave a cached Plus account reportable; `refreshToken=true` is not itself proof
   of a successful refresh. See the
   [transient outcome](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/app-server/src/request_processors/account_processor.rs#L1017)
   and [cached account projection](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/model-provider/src/provider.rs#L401).
3. [`login/completed` is sent first](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/app-server/src/request_processors/account_processor.rs#L907),
   before auth reload, cloud-loader replacement, config synchronization and
   conditional plugin-cache refresh. `account/updated` follows those operations.
   Login completion alone therefore cannot acknowledge the completed post-login
   configuration lifecycle. Conditional
   [curated/remote plugin refresh](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/app-server/src/request_processors/account_processor.rs#L227)
   also prevents inferring "no other post-login HTTP" solely from bundle eligibility.

The [loader task](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/cloud-config/src/bundle_loader.rs#L62)
calls `get_latest` and then starts its refresh loop even if the first Plus lookup
returned `None`. At the first ordinary 15-minute refresh, changed eligible auth can
permit a bundle fetch. A still-ineligible account ends that loop.
[Successful refresh](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/cloud-config/src/service.rs#L472)
updates the cache and the loader's `latest_bundle`; subsequent config loads can
observe it. This is **not** evidence that every existing thread's effective policy
is immediately replaced. Explicit loader replacement after login is a separate
operation, and actual application depends on later config loading/consumption.

### Narrower proposal: close the issuer before admitting a turn

The proposal now under review is a fresh, native-owned managed device-code login
in one process using a unique ephemeral `CODEX_HOME`; then close `auth.openai.com`
egress **and all existing issuer tunnels**, deny subsequent login/import/auth
mutation RPCs, and permit only `chatgpt.com` during the admitted turn. This has a
stronger source basis than merely limiting elapsed time:

- Device-code login
  [polls and exchanges through its issuer](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/login/src/device_code_auth.rs#L162),
  then persists tokens through the selected native storage mode. Explicit
  [ephemeral storage](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/login/src/auth/storage.rs#L459)
  is an in-process map keyed by the home; its
  [reload path](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/login/src/auth/manager.rs#L1466)
  has no persistent fallback when ephemeral mode is selected. A cached reload
  does not itself acquire new token claims if no other writer changes that map.
- Managed OAuth refresh uses
  [`https://auth.openai.com/oauth/token`](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/login/src/auth/manager.rs#L199)
  by default. Only a successfully decoded response reaches
  [token persistence and reload](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/login/src/auth/manager.rs#L3031).
  With that destination unavailable and no admitted override, immediate 401
  recovery has no successful refresh path in the reviewed code. It may fail or
  retain/retry old credentials; neither outcome proves account entitlement.
- No reviewed `chatgpt.com` response path writes managed OAuth token/plan fields.
  The account rate-limit path returns its response without updating those fields.
  This is a bounded source finding, not an exhaustive native runtime observation.

**Conditional conclusion:** closing the issuer can preserve the admitted managed
token claims if the native process has no remaining successful token response
waiting to commit and no other admitted writer. Closing a tunnel alone does not
discard a response already buffered/decoded inside native code; a delayed
successful response could persist after the phase transition. The admission
sequence must establish that earlier issuer work is complete before its final
account/config acknowledgement. Neither reviewed account nor config RPC was
established as a global barrier over auth writers. That ordering remains a blocker
to admission; elapsed quiet time is not a substitute for testing it.

Another native-owned storage writer exists outside the login RPC path:
[managed AgentIdentity bootstrap](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/login/src/auth/manager.rs#L734)
can run during [request auth resolution](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/model-provider/src/auth.rs#L240)
when `AgentIdentityAuthPolicy::ChatGptAuth` is selected. Its
[persistence operation](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/login/src/auth/manager.rs#L894)
adds an agent identity record and leaves the managed OAuth token/plan fields
unchanged. Consequently token-claim stability must not be inflated into a claim
that all effective request credentials or all native auth storage are immutable.
AgentIdentity derivation could be a separately scoped and acknowledged native
credential lifecycle; its presence is not automatically disallowed.

For this tag, [the feature registry](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/features/src/lib.rs#L1751)
defines `use_agent_identity` as under development and disabled by default. The
[session constructor](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/core/src/session/session.rs#L1463)
maps that disabled feature to `JwtOnly`, which prevents managed-ChatGPT bootstrap.
`features.use_agent_identity=false` is a recognized version-specific configuration
pin, not a newly verified native acknowledgement or universal managed-policy
override. The production
[registration endpoint base](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/agent-identity/src/lib.rs#L40)
is `https://auth.openai.com/api/accounts`, with `/v1/agent/register` and
`/v1/agent/{id}/task/register` appended. Issuer closure blocks those new default
registrations too. The `chatgpt.com` JWKS path verifies an already supplied identity
JWT; it does not mint replacement managed OAuth tokens. Endpoint overrides
`CODEX_AGENT_IDENTITY_AUTHAPI_BASE_URL` and `CODEX_AGENT_IDENTITY_JWKS_BASE_URL`
exist in [the native implementation](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/login/src/auth/agent_identity.rs#L26)
and must be absent from this narrowed proposal. No alternate remaining-host
credential writer was found for the resulting fresh managed flow.

The source accepts `CODEX_APP_SERVER_LOGIN_ISSUER` during
[login option construction](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/app-server/src/request_processors/account_processor.rs#L577)
and `CODEX_REFRESH_TOKEN_URL_OVERRIDE` in the
[refresh endpoint selector](https://github.com/openai/codex/blob/rust-v0.154.0/codex-rs/login/src/auth/manager.rs#L1719).
An override redirecting refresh to the remaining allowed host would defeat the
issuer-closure argument. These version-specific source hooks can support a later
wholly synthetic issuer experiment; they are not established documented live
admission controls and must not enter the eventual live environment accidentally.

Next discriminators, without opening production admission: synthetic device-code
completion/config ordering; transient refresh failure; a delayed successful token
response spanning phase closure; immediate 401 after issuer closure; Plus→Go and
Plus→Business counterfactual refresh responses; denied late login/import attempts;
and conditional AgentIdentity/plugin startup. Observe both rejected new CONNECTs
and termination of existing issuer tunnels. Opaque `chatgpt.com` TLS still does not
distinguish a provider request from another request to that host. Source inference,
local fixture evidence and eventual separately authorized real-account evidence
must remain distinct.

Documentation verification for this follow-up: `tests/test_seed_context.py` **5
passed** and `git diff --check` passed. These checks validate repository continuity
and formatting, not the lifecycle inference. No new dynamic admission test ran.
