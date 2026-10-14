"""Transient sign-in is an exact live control read, never durable work content."""
from copy import deepcopy
import math
import time

import pytest

from eidos.native_managed_contract import DEVICE_VERIFICATION_URL, ManagedAttemptIdentity, ManagedPolicy
from test_owned_attempt_api import owned, start, control_path
from test_investigation_continuations_api import call, successful


def test_sign_in_is_returned_only_by_current_owned_control_without_persisting(owned, monkeypatch):
    api, trace, owner, value = owned
    dispatched = start(api, value)
    assert owner.entered.wait(1)
    challenge = {"verificationUrl": DEVICE_VERIFICATION_URL, "userCode": "PRIVATE_SIGNIN_CODE_CANARY",
                 "expiresAtMs": int(time.time() * 1000) + 60000, "token": "PRIVATE_TOKEN_CANARY"}
    original = owner.inspect_owned
    monkeypatch.setattr(owner, "inspect_owned", lambda ident: {**original(ident), "signIn": deepcopy(challenge)})
    before = list(trace.db.iterdump())
    control = successful(call(api, control_path(dispatched), method="GET"))
    assert control["signIn"] == {key: challenge[key] for key in ("verificationUrl", "userCode", "expiresAtMs")}
    assert list(trace.db.iterdump()) == before
    assert "PRIVATE_SIGNIN" not in str(api.investigations.get(value["id"]))
    assert "PRIVATE_TOKEN" not in str(control)
    stopped = successful(call(api, control_path(dispatched), {"action": "cancel"}))
    assert "signIn" not in stopped["control"]
    api._investigation_threads[value["id"]].join(1)
    assert "PRIVATE_SIGNIN" not in "\n".join(trace.db.iterdump())


@pytest.mark.parametrize("change", [
    {"verificationUrl": "https://auth.openai.com.attacker.invalid/codex/device"},
    {"verificationUrl": "javascript:alert(1)"}, {"userCode": "a\nprivate"},
    {"userCode": "x" * 129}, {"expiresAtMs": 1}, {"expiresAtMs": True},
])
def test_invalid_or_expired_sign_in_cannot_disable_existing_stop(owned, monkeypatch, change):
    api, _, owner, value = owned
    dispatched = start(api, value)
    assert owner.entered.wait(1)
    challenge = {"verificationUrl": DEVICE_VERIFICATION_URL, "userCode": "NEMA-FIXTURE",
                 "expiresAtMs": int(time.time() * 1000) + 60000, **change}
    monkeypatch.setattr(owner, "inspect_owned", lambda ident: {"owned": True, "canCancel": True, "signIn": challenge})
    assert successful(call(api, control_path(dispatched), method="GET")) == {
        "attemptId": dispatched["attempt"]["id"], "owned": True, "canCancel": True}


def test_http_payload_cannot_enable_managed_execution(owned):
    api, _, owner, value = owned
    status, _ = call(api, f"/{value['id']}/dispatch", {"contextId": value["currentContextId"], "managed_native": True})
    assert status == 400 and owner.calls == []


@pytest.mark.parametrize("value", [math.inf, math.nan, 0, -1, True])
def test_managed_policy_rejects_unbounded_or_non_numeric_time(value):
    with pytest.raises(ValueError):
        ManagedPolicy(preparation_seconds=value)


def test_identity_pins_full_context_unknown_fields_and_exact_source():
    context = {"id": "C0", "projectedPrompt": "Exact C0", "future": {"v": 1}}
    attempt = {"id": "A0", "contextId": "C0"}
    identity = ManagedAttemptIdentity.from_attempt(attempt, context, "owned/one")
    assert identity != ManagedAttemptIdentity.from_attempt(attempt, context, "owned/two")
    changed = ManagedAttemptIdentity.from_attempt(attempt, {**context, "future": {"v": 2}}, "owned/one")
    assert changed.context_sha256 != identity.context_sha256
    assert changed.projected_prompt_sha256 == identity.projected_prompt_sha256
    with pytest.raises(ValueError):
        ManagedAttemptIdentity.from_attempt({**attempt, "contextId": "C1"}, context, "owned/one")


def test_cli_requires_explicit_managed_switch_without_starting_any_process(monkeypatch):
    from eidos import cli
    calls = []
    monkeypatch.setattr(cli, "serve", lambda *args, **kwargs: calls.append((args, kwargs)))
    cli.main(["serve", "work.db"])
    cli.main(["serve", "work.db", "--managed-native", "--codex", "/reviewed/codex"])
    assert calls[0][1]["managed_native"] is False
    assert calls[1][1]["managed_native"] is True
    assert calls[1][1]["codex"] == "/reviewed/codex"
