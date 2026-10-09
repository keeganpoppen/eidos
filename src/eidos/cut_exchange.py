from __future__ import annotations

"""Causal disclosure of a Cut between authority-local domains.

The source observer actualizes DiscloseCut against its own live Discloser
projection. The receiving Model process separately actualizes Acquire against
its private process projection. No fictional cross-domain atomic transaction is
assumed: the resulting two occurrences are linked by the disclosed occurrence
Name and the receiving process checkpoint.

Knowing a Cut or CutDisclosure Name grants neither disclosure authority nor
access to the Cut's contents. Each disclosure is addressed to one ModelProcess
run and its Model identity. A historical Cut may be disclosed as knowledge
without reviving its spent world projections.
"""

from typing import Any

from .authority import ProjectionGrant
from .core import Name, RecordValue
from .semantic_values import projection_value
from .trusted import TrustedMachinery


class CutExchangeError(ValueError):
    pass


def cut_request(
    provider: Name | str,
    cut: Name | str,
) -> RecordValue:
    return RecordValue.from_mapping({
        "$kind": "CutRequest",
        "provider": provider if isinstance(provider, Name) else Name(provider),
        "cut": cut if isinstance(cut, Name) else Name(cut),
    })


def disclose_cut(
    trusted: TrustedMachinery,
    *,
    cut: str,
    discloser_projection: str,
    recipient_run: str,
    recipient_model: str,
    request_id: str,
) -> dict[str, str]:
    """Publish one source-domain causal disclosure, never a world capability."""

    observer = trusted.causal_cut(cut)
    discloser = trusted.projection(discloser_projection)
    if (
        discloser.get("role") != "Discloser"
        or discloser["domain_name"] != observer["instance_name"]
        or discloser["holder"] != observer["observer"]
    ):
        raise CutExchangeError("Cut disclosure requires the observer's Discloser authority")

    run = trusted.named_eidos_value(recipient_run)["value"]
    if (
        not isinstance(run, RecordValue)
        or run.get("$kind") != "ModelProcess"
        or run.get("model") != Name(recipient_model)
    ):
        raise CutExchangeError("disclosure recipient must name a matching ModelProcess")

    desc = trusted.named_eidos_value(discloser_projection)["value"]
    # Allow the same request_id to replay its already-committed occurrence
    # after a crash. For a new request, the generic commit still refuses to
    # consume a spent Discloser projection.
    committed = trusted.commit_projection_occurrence(
        kind="DiscloseCut",
        consumes=(discloser_projection,),
        establishes=(
            ProjectionGrant(
                key="next:discloser",
                holder=discloser["holder"],
                description=desc,
            ),
        ),
        fact={
            "cut": cut,
            "recipient_run": recipient_run,
            "recipient_model": recipient_model,
            "observer": observer["observer"],
        },
        request_id=f"{request_id}:commit",
    )
    disclosed = committed["occurrence"]
    evidence = RecordValue.from_mapping({
        "$kind": "CutDisclosure",
        "cut": Name(cut),
        "recipient_run": Name(recipient_run),
        "recipient_model": Name(recipient_model),
        "observer": observer["observer"],
        "discloser": Name(discloser_projection),
        "next_discloser": Name(committed["established"]["next:discloser"]),
    })
    trusted.bind_eidos_value(
        name=disclosed,
        value=evidence,
        request_id=f"{request_id}:bind",
    )
    return {
        "disclosure": disclosed,
        "successor_discloser": committed["established"]["next:discloser"],
        "cut": cut,
    }


def validate_disclosure(
    trusted: TrustedMachinery,
    *,
    disclosure: str,
    cut: str,
    recipient_run: str,
    recipient_model: str,
) -> RecordValue:
    """Require the named Value to match an actual source-domain occurrence."""

    committed = trusted.authority_occurrence(disclosure)
    if committed["kind"] != "DiscloseCut":
        raise CutExchangeError("CutDisclosure lacks a DiscloseCut causal occurrence")
    fact = committed["fact"]
    expected = {
        "cut": cut,
        "recipient_run": recipient_run,
        "recipient_model": recipient_model,
    }
    if any(fact.get(key) != value for key, value in expected.items()):
        raise CutExchangeError("CutDisclosure is not addressed to this process and Cut")

    value = trusted.named_eidos_value(disclosure)["value"]
    if not isinstance(value, RecordValue) or value.get("$kind") != "CutDisclosure":
        raise CutExchangeError("disclosure Name does not denote a CutDisclosure")
    if (
        value.get("cut") != Name(cut)
        or value.get("recipient_run") != Name(recipient_run)
        or value.get("recipient_model") != Name(recipient_model)
        or value.get("observer") != fact.get("observer")
    ):
        raise CutExchangeError("disclosure Value contradicts its causal occurrence")

    row = trusted.causal_cut(cut)
    if (
        row["observer"] != fact["observer"]
        or row["instance_name"] != committed["domain_name"]
    ):
        raise CutExchangeError("disclosure did not originate in the Cut's authority domain")

    consumed = value.get("discloser")
    if (
        not isinstance(consumed, Name)
        or consumed.value not in committed["inputs"]
    ):
        raise CutExchangeError("disclosure's source capability is not a causal input")
    desc = trusted.projection(consumed.value)
    if desc.get("role") != "Discloser" or desc["holder"] != fact["observer"]:
        raise CutExchangeError("disclosure did not consume observer Discloser authority")
    return value
