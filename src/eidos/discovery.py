from __future__ import annotations

"""Open epistemic discovery: an inquiry, one source responder, and causal replies.

The Model's Discover is a process-domain occurrence. The observer may later
accept the named inquiry with a live Discloser projection, obtaining a linear
InquiryResponder projection in the *source* authority domain. Defer advances
that source projection; Offer/Refuse terminates it. The recipient's Await is a
separate process-domain occurrence, never a cross-domain atomic commit.

A Name is not authority: providers describe a source domain/observer; replies
must consume the corresponding source-domain responder capability.
"""

from typing import Any

from .authority import ProjectionGrant
from .core import Name, RecordValue, content_id
from .semantic_values import projection_value
from .trusted import TrustedMachinery


class DiscoveryError(ValueError):
    pass


def discovery_provider_value(*, label: str, source_domain: str, observer: str) -> RecordValue:
    if not label or not source_domain or not observer:
        raise ValueError("DiscoveryProvider needs label, source domain, and observer")
    return RecordValue.from_mapping({
        "$kind": "DiscoveryProvider",
        "label": label,
        "source_domain": Name(source_domain),
        "observer": observer,
    })


def discover_request(provider: Name | str, question: str) -> RecordValue:
    if not isinstance(question, str) or not question.strip():
        raise ValueError("discovery requires a nonempty question")
    return RecordValue.from_mapping({
        "$kind": "DiscoverRequest",
        "provider": provider if isinstance(provider, Name) else Name(provider),
        "question": question,
    })


def await_discovery(inquiry: Name | str) -> RecordValue:
    return RecordValue.from_mapping({
        "$kind": "AwaitDiscoveryRequest",
        "inquiry": inquiry if isinstance(inquiry, Name) else Name(inquiry),
    })


def open_inquiry(
    trusted: TrustedMachinery,
    *,
    run: str,
    model: str,
    context: str,
    checkpoint: str,
    provider: str,
    question: str,
    request_id: str,
) -> str:
    """Durably name a question before its process-domain Discover occurrence."""

    _provider(trusted, provider)
    inquiry = RecordValue.from_mapping({
        "$kind": "DiscoveryInquiry",
        "run": Name(run),
        "model": Name(model),
        "context": Name(context),
        "checkpoint": Name(checkpoint),
        "provider": Name(provider),
        "question": question,
    })
    name = trusted.reserve_name(kind="inquiry", request_id=f"{request_id}:reserve")
    trusted.bind_eidos_value(
        name=name, value=inquiry, request_id=f"{request_id}:bind"
    )
    return name


def accept_inquiry(
    trusted: TrustedMachinery,
    *,
    inquiry: str,
    discloser_projection: str,
    request_id: str,
) -> dict[str, str]:
    """Observer admits one source-domain response authority for an open inquiry."""

    value, provider = _inquiry(trusted, inquiry)
    _require_opened(trusted, inquiry, value)
    if _accepted(trusted, inquiry):
        raise DiscoveryError("inquiry already has a source responder")
    authority = trusted.projection(discloser_projection)
    _check_source_projection(authority, provider, role="Discloser")
    grants = (
        ProjectionGrant(
            key="next:discloser",
            holder=authority["holder"],
            description=trusted.named_eidos_value(discloser_projection)["value"],
        ),
        ProjectionGrant(
            key="responder",
            holder=authority["holder"],
            description=projection_value(
                key=f"discovery:responder:{inquiry}",
                role="InquiryResponder",
                state=f"inquiry:{inquiry}",
            ),
        ),
    )
    fact = {
        "inquiry": inquiry,
        "provider": value.get("provider").value,
        "observer": provider.get("observer"),
        "recipient_run": value.get("run").value,
        "recipient_model": value.get("model").value,
    }
    committed = trusted.commit_projection_occurrence(
        kind="DiscoveryAccept",
        consumes=(discloser_projection,),
        establishes=grants,
        fact=fact,
        request_id=f"{request_id}:commit",
    )
    result_value = RecordValue.from_mapping({
        "$kind": "DiscoveryAcceptance",
        "inquiry": Name(inquiry),
        "provider": value.get("provider"),
        "responder": Name(committed["established"]["responder"]),
        "next_discloser": Name(committed["established"]["next:discloser"]),
        "observer": provider.get("observer"),
    })
    trusted.bind_eidos_value(
        name=committed["occurrence"],
        value=result_value,
        request_id=f"{request_id}:bind",
    )
    return {
        "acceptance": committed["occurrence"],
        "responder": committed["established"]["responder"],
        "next_discloser": committed["established"]["next:discloser"],
    }


def decide_inquiry(
    trusted: TrustedMachinery,
    *,
    inquiry: str,
    responder_projection: str,
    decision: str,
    request_id: str,
    cut: str | None = None,
) -> dict[str, str | None]:
    """Defer, refuse, or offer evidence with one live source responder Socket."""

    if decision not in ("defer", "refuse", "offer"):
        raise DiscoveryError("decision must be defer, refuse, or offer")
    value, provider = _inquiry(trusted, inquiry)
    _require_opened(trusted, inquiry, value)
    accepted = _accepted(trusted, inquiry)
    if accepted is None:
        raise DiscoveryError("observer must first accept the inquiry")
    if _terminal_reply(trusted, inquiry) is not None:
        raise DiscoveryError("inquiry already has a terminal response")
    if (decision == "offer") != (cut is not None):
        raise DiscoveryError("only an offer may name a Cut")

    authority = trusted.projection(responder_projection)
    _check_source_projection(authority, provider, role="InquiryResponder")
    if authority.get("protocol_state") != f"inquiry:{inquiry}":
        raise DiscoveryError("responder belongs to a different inquiry")
    if not _responder_in_lineage(trusted, inquiry, responder_projection):
        raise DiscoveryError("responder does not descend from this inquiry acceptance")

    if cut is not None:
        observed = trusted.causal_cut(cut)
        if (
            observed["instance_name"] != provider.get("source_domain").value
            or observed["observer"] != provider.get("observer")
        ):
            raise DiscoveryError("offered Cut is not held in this observer domain")

    grants = (
        (
            ProjectionGrant(
                key="next:responder",
                holder=authority["holder"],
                description=trusted.named_eidos_value(responder_projection)["value"],
            ),
        )
        if decision == "defer" else ()
    )
    committed = trusted.commit_projection_occurrence(
        kind={
            "defer": "DiscoveryDefer",
            "refuse": "DiscoveryRefuse",
            "offer": "DiscoveryOffer",
        }[decision],
        consumes=(responder_projection,),
        establishes=grants,
        fact={
            "inquiry": inquiry,
            "decision": decision,
            "cut": cut,
            "provider": value.get("provider").value,
            "recipient_run": value.get("run").value,
            "recipient_model": value.get("model").value,
        },
        request_id=f"{request_id}:commit",
    )
    successor = committed["established"].get("next:responder")
    if decision == "offer":
        evidence = RecordValue.from_mapping({
            "$kind": "CutDisclosure",
            "inquiry": Name(inquiry),
            "cut": Name(cut),
            "recipient_run": value.get("run"),
            "recipient_model": value.get("model"),
            "provider": value.get("provider"),
            "observer": provider.get("observer"),
            "responder": Name(responder_projection),
        })
    else:
        evidence = RecordValue.from_mapping({
            "$kind": "DiscoveryDecision",
            "inquiry": Name(inquiry),
            "decision": decision,
            "provider": value.get("provider"),
            "responder": Name(responder_projection),
            "next_responder": None if successor is None else Name(successor),
        })
    trusted.bind_eidos_value(
        name=committed["occurrence"],
        value=evidence,
        request_id=f"{request_id}:bind",
    )
    return {
        "decision": decision,
        "occurrence": committed["occurrence"],
        "responder": successor,
        "cut": cut,
    }


def poll_inquiry(trusted: TrustedMachinery, inquiry: str) -> dict[str, str | None]:
    """Inspect source-domain replies without consuming recipient authority."""

    value, provider = _inquiry(trusted, inquiry)
    _require_opened(trusted, inquiry, value)
    events: list[tuple[int, str, str, str | None]] = []
    for index, (name, record) in enumerate(trusted.named_values()):
        if not isinstance(record, RecordValue):
            continue
        try:
            if record.get("inquiry") != Name(inquiry):
                continue
        except KeyError:
            continue
        try:
            event = trusted.authority_occurrence(name)
        except KeyError:
            continue
        if event["kind"] not in ("DiscoveryDefer", "DiscoveryRefuse", "DiscoveryOffer"):
            continue
        if event["domain_name"] != provider.get("source_domain").value:
            raise DiscoveryError("discovery reply came from wrong authority domain")
        if event["fact"].get("recipient_run") != value.get("run").value:
            raise DiscoveryError("discovery reply names wrong recipient")
        if event["fact"].get("provider") != value.get("provider").value:
            raise DiscoveryError("discovery reply names wrong provider")
        consumed = event["inputs"]
        if len(consumed) != 1 or not _responder_in_lineage(trusted, inquiry, consumed[0]):
            raise DiscoveryError("discovery reply lacks inquiry responder authority")
        kind = event["kind"]
        expected_kind = "CutDisclosure" if kind == "DiscoveryOffer" else "DiscoveryDecision"
        if record.get("$kind") != expected_kind:
            raise DiscoveryError("discovery decision Value contradicts its occurrence")
        candidate_cut = event["fact"].get("cut")
        if kind == "DiscoveryOffer":
            if record.get("cut") != Name(candidate_cut):
                raise DiscoveryError("offered Cut contradicts causal fact")
            observed = trusted.causal_cut(candidate_cut)
            if (
                observed["instance_name"] != provider.get("source_domain").value
                or observed["observer"] != provider.get("observer")
            ):
                raise DiscoveryError("discovery offer disclosed a foreign Cut")
        events.append((index, name, kind, candidate_cut))

    final = [event for event in events if event[2] in ("DiscoveryOffer", "DiscoveryRefuse")]
    if len(final) > 1:
        raise DiscoveryError("ambiguous terminal discovery decisions")
    if final:
        _, name, kind, cut = final[0]
        return {
            "status": "offer" if kind == "DiscoveryOffer" else "refuse",
            "decision": name,
            "cut": cut,
        }
    return {
        "status": "deferred" if events else "pending",
        "decision": events[-1][1] if events else None,
        "cut": None,
    }


def _provider(trusted: TrustedMachinery, name: str) -> RecordValue:
    value = trusted.named_eidos_value(name)["value"]
    if not isinstance(value, RecordValue) or value.get("$kind") != "DiscoveryProvider":
        raise DiscoveryError("provider Name must denote a DiscoveryProvider")
    domain = value.get("source_domain")
    if not isinstance(domain, Name):
        raise DiscoveryError("DiscoveryProvider lacks source-domain identity")
    trusted.authority_domain(domain.value)
    return value


def _inquiry(trusted: TrustedMachinery, name: str) -> tuple[RecordValue, RecordValue]:
    value = trusted.named_eidos_value(name)["value"]
    if not isinstance(value, RecordValue) or value.get("$kind") != "DiscoveryInquiry":
        raise DiscoveryError("Name does not denote a DiscoveryInquiry")
    provider = value.get("provider")
    if not isinstance(provider, Name):
        raise DiscoveryError("Inquiry lacks a provider Name")
    return value, _provider(trusted, provider.value)


def _require_opened(trusted: TrustedMachinery, name: str, inquiry: RecordValue) -> None:
    """The receiver must have actually issued this inquiry as a causal step."""

    checkpoint = inquiry.get("checkpoint")
    run = inquiry.get("run")
    if not isinstance(checkpoint, Name) or not isinstance(run, Name):
        raise DiscoveryError("inquiry has invalid source references")
    step = trusted.named_eidos_value(checkpoint.value)["value"]
    if not isinstance(step, RecordValue) or step.get("$kind") != "ModelCheckpoint":
        raise DiscoveryError("inquiry lacks a saved requesting continuation")
    suspended = step.get("suspension")
    if suspended.operation.value != "model:Discover":
        raise DiscoveryError("inquiry did not originate from Discover")
    if step.get("run") != run:
        raise DiscoveryError("inquiry checkpoint is outside recipient process")
    for _, record in trusted.named_values():
        if (
            isinstance(record, RecordValue)
            and _get(record, "$kind") == "ModelInteraction"
            and _get(record, "checkpoint") == checkpoint
            and _get(record, "operation") == suspended.operation
            and _get(record, "run") == run
            and _get(record, "response") is not None
            and _get(_get(record, "response"), "inquiry") == Name(name)
        ):
            return
    raise DiscoveryError("inquiry has not been committed by its requester")


def _accepted(trusted: TrustedMachinery, inquiry: str) -> tuple[str, RecordValue] | None:
    for name, value in trusted.named_values():
        if (
            isinstance(value, RecordValue)
            and _get(value, "$kind") == "DiscoveryAcceptance"
            and _get(value, "inquiry") == Name(inquiry)
        ):
            return name, value
    return None


def _terminal_reply(trusted: TrustedMachinery, inquiry: str) -> str | None:
    for name, record in trusted.named_values():
        if not isinstance(record, RecordValue) or _get(record, "inquiry") != Name(inquiry):
            continue
        if _get(record, "$kind") == "CutDisclosure":
            return name
        if (
            _get(record, "$kind") == "DiscoveryDecision"
            and _get(record, "decision") == "refuse"
        ):
            return name
    return None


def _responder_in_lineage(trusted: TrustedMachinery, inquiry: str, responder: str) -> bool:
    accepted = _accepted(trusted, inquiry)
    if accepted is None:
        return False
    _, admission = accepted
    ref = admission.get("responder")
    if not isinstance(ref, Name):
        return False
    current = ref.value
    for _ in range(128):
        if current == responder:
            return True
        next_ = None
        for name, record in trusted.named_values():
            if (
                isinstance(record, RecordValue)
                and _get(record, "$kind") == "DiscoveryDecision"
                and _get(record, "inquiry") == Name(inquiry)
                and _get(record, "decision") == "defer"
                and _get(record, "responder") == Name(current)
            ):
                next_ref = record.get("next_responder")
                next_ = next_ref.value if isinstance(next_ref, Name) else None
                break
        if next_ is None:
            return False
        current = next_
    raise DiscoveryError("responder deferral chain exceeds supported depth")


def _check_source_projection(projection: dict[str, Any], provider: RecordValue, *, role: str) -> None:
    if (
        projection.get("role") != role
        or projection["domain_name"] != provider.get("source_domain").value
        or projection["holder"] != provider.get("observer")
    ):
        raise DiscoveryError("source responder authority does not match provider")


def _get(value: Any, key: str) -> Any:
    if isinstance(value, RecordValue):
        try:
            return value.get(key)
        except KeyError:
            return None
    return None
