# Paired native startup-catalog policy challenge

**2026-10-13 · integrated from `555a317` · C6, V1-05/12.**

## Question and allowed experiment

The exact public Astra catalog overrides earlier feature flags and registers
code/async/collaboration tools; a safe clock call ran without a native action item.
Can a supported, transparent local startup policy produce an empty tool registry
while retaining the actual model slug and Responses Lite? This challenges the
profile before any subscription-backed specialist admission. It does not establish
account model availability, entitlement or authentication against a compromised
native executable. The ordinary-Responses control remains a simpler candidate.

Run a paired disconnected experiment with the same reviewed native 0.154.0 binary,
namespace, process filter, local fake provider and authored responses. Both cases
use gpt-6-astra, existing allMcpDisabled settings, agents.enabled=false,
features.multi_agent_v2=false, sleep_tool=false and current_time_reminder=false.
The first uses exact committed public catalog bytes. The second changes ONLY the
selected entry's tool_mode from code_mode_only to direct and its
experimental_supported_tools from [send_user_message_async, clock] to []. Preserve
slug, use_responses_lite=true, multi_agent_version and all other metadata. Validate
source hash, target slug, exact semantic diff; record RFC6902 patch, original and
derived hashes. Label the derived input as Nema local policy, never unchanged
upstream metadata or new authority. Startup fixture mounts stay immutable.

Each case gets exactly one turn and at most three accepted provider requests:
fixed read_mcp_resource call, fixed clock.curr_time call, then authored final text.
No exec/code, collaboration or user-interaction call is permitted. No credentials,
existing Codex state, upstream forwarding, real model, subscription or paid API.
No production profile/admission changes. The request/response shape remains a
fixture classifier, not proof of logical caller authentication.

## Limits and acceptance

Retain existing HTTP limits: header 8KiB, body 128KiB, response 16KiB, 24 total
requests/case, parse 2s; relay/helper/watchdog and completion-event limits unchanged.
Use explicit AppServerLimits: stdout frame 1MiB, stderr 64KiB, receipt 4MiB,
retained events 128/2MiB, tail 64KiB/100 lines. Capture actual status and trusted
limit/gap records; a gap fails the candidate. No aggregate CPU/RSS/disk claim.

Original should retain code/async registration and clock success despite the
additional supported controls. Derived target is Lite with empty additional_tools,
both authored calls rejected, zero MCP contact, and exact final text recovered as
synthetic. Record an incompatible/unexpected outcome honestly and reject the
candidate. Empty event lists alone are insufficient; inspect provider-wire tool
schemas and correlated call outputs. Default tests start no native process.

## Ownership

native_frontier: `/tmp/nema-derived-model-catalog`, branch
`codex/derived-model-catalog`; owns NEW scripts/probe_native_derived_catalog.py,
tests/test_native_derived_catalog_probe.py,
docs/evidence/NATIVE_DERIVED_CATALOG_EXPERIMENT.md and
NATIVE_DERIVED_CATALOG_0_154_0.json, with optional derived catalog artifact. Reuse
catalog validation, HTTP/SSE broker and existing synthetic client/process helpers
without editing them. Root approved and owns one narrow shared extension: optional
config and AppServerLimits keyword arguments on catalog run_case, preserving its
existing defaults. The new probe passes those explicitly rather than swapping
module globals. Do not copy the entire harness. Root owns this packet, review,
independent reproduction, integration and docs. Product/acceptance lanes are
separate. Return a frozen commit plus exact commands and raw evidence.

Relevant prior evidence: [catalog discriminator](../evidence/NATIVE_MODEL_CATALOG_EXPERIMENT.md),
[bounded recording](../evidence/NATIVE_CAPTURE_ACCEPTANCE.md). Check exact tagged
primary source for tool selection, supported agent controls and static startup
catalog behavior. Existing upstream license/notice accompanies the catalog.
