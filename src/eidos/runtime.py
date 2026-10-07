from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable, Mapping

from .model import Await, Done, Frame, JSON, OfferSpec, content_id
from .praxis import Praxis, Term
from .trusted import TrustedMachinery

_RUNTIME_BINDING = "$eidos"


def await_to_data(await_: Await) -> JSON:
    return {"kind": "await", **asdict(await_)}


def await_from_data(value: JSON) -> Await:
    if not isinstance(value, dict) or value.get("kind") != "await":
        raise ValueError("frame residual is not an Eidos Await")
    return Await(
        socket=str(value["socket"]),
        operation=str(value["operation"]),
        payload=value.get("payload"),
        continuation=value.get("continuation"),
    )


def _replace_name(value: JSON, old: str, new: str | None) -> JSON:
    """Rebind an exact socket-name occurrence inside a captured environment.

    This is intentionally conservative: only an exact string atom equal to the
    spent socket is replaced. It is a v0 stand-in for explicit role bindings.
    """

    if isinstance(value, str):
        return new if value == old else value
    if isinstance(value, list):
        return [_replace_name(v, old, new) for v in value]
    if isinstance(value, dict):
        return {k: _replace_name(v, old, new) for k, v in value.items()}
    return value


@dataclass(frozen=True)
class RunState:
    nema: str
    frame: str
    meta_socket: str
    status: str
    offers: tuple[str, ...] = ()
    result: JSON = None


class Runtime:
    """Connects local Praxis reduction to durable Trusted-Machinery cuts.

    The runtime is deliberately reconstructible. There is no authoritative
    in-memory scheduler state: the current Frame, open offers, durable Matches,
    and unincorporated receipts are enough to continue after restart.
    """

    def __init__(self, trusted: TrustedMachinery, praxis: Praxis | None = None) -> None:
        self.trusted = trusted
        self.praxis = praxis or Praxis()

    def start(self, *, nema: str, term: Term, env: Mapping[str, JSON] | None = None) -> RunState:
        head = self.trusted.head(nema)
        base = self.trusted.frame(head["frame_cid"])
        result = self.praxis.eval(term, env)
        return self._publish_result(
            nema=nema,
            expected_meta=head["meta_socket"],
            base=base,
            result=result,
            consume_receipts=[],
        )

    def resume_one(self, *, nema: str, receipt_name: str | None = None) -> RunState | None:
        head = self.trusted.head(nema)
        base = self.trusted.frame(head["frame_cid"])
        await_ = self._frame_await(base)
        if await_ is None:
            return None

        receipts = self.trusted.receipts(nema)
        if receipt_name is None:
            receipt = next((r for r in receipts if r["old_socket"] == await_.socket), None)
        else:
            receipt = self.trusted.receipt(receipt_name)
            if receipt["holder"] != nema or receipt["incorporated"]:
                return None
            if receipt["old_socket"] != await_.socket:
                raise ValueError("receipt does not discharge the Frame's suspended continuation")
        if receipt is None:
            return None

        receipt = self.trusted.receipt(receipt["name"])
        receipt_name = receipt["name"]
        transition = self.trusted.expected_transition(receipt["old_socket"])
        resume_value: JSON = None if transition.direction == "send" else receipt["payload"]

        continuation = await_.continuation
        if not isinstance(continuation, dict):
            raise ValueError("Await continuation is not a serialized Praxis continuation")
        continuation = _replace_name(continuation, receipt["old_socket"], receipt["successor_socket"])
        rebound = Await(
            socket=await_.socket,
            operation=await_.operation,
            payload=await_.payload,
            continuation=continuation,
        )
        result = self.praxis.resume(rebound, resume_value)
        return self._publish_result(
            nema=nema,
            expected_meta=head["meta_socket"],
            base=base,
            result=result,
            consume_receipts=[receipt_name],
        )

    def match_one(self) -> dict[str, JSON] | None:
        offers = self.trusted.open_offers()
        for i, left in enumerate(offers):
            for right in offers[i + 1 :]:
                if left["session_name"] != right["session_name"]:
                    continue
                if left["label"] != right["label"]:
                    continue
                if left["direction"] == right["direction"]:
                    continue
                request_id = f"match:{left['name']}:{right['name']}"
                return self.trusted.match(
                    left_offer=left["name"],
                    right_offer=right["name"],
                    request_id=request_id,
                )
        return None

    def drive(self, nemata: Iterable[str], *, max_cycles: int = 100) -> list[RunState]:
        """Advance all immediately available work until quiescent."""

        names = tuple(nemata)
        states: list[RunState] = []
        for _ in range(max_cycles):
            progressed = False
            while self.match_one() is not None:
                progressed = True
            for nema in names:
                while True:
                    state = self.resume_one(nema=nema)
                    if state is None:
                        break
                    states.append(state)
                    progressed = True
            if not progressed:
                return states
        raise RuntimeError("runtime did not reach quiescence within max_cycles")

    def state(self, nema: str) -> RunState:
        head = self.trusted.head(nema)
        frame = self.trusted.frame(head["frame_cid"])
        marker = frame.bindings.get(_RUNTIME_BINDING, {})
        if not isinstance(marker, dict):
            marker = {}
        return RunState(
            nema=nema,
            frame=head["frame_cid"],
            meta_socket=head["meta_socket"],
            status=str(marker.get("status", "unknown")),
            result=marker.get("result"),
        )

    def _publish_result(
        self,
        *,
        nema: str,
        expected_meta: str,
        base: Frame,
        result: Done | Await,
        consume_receipts: list[str],
    ) -> RunState:
        bindings = dict(base.bindings)
        if isinstance(result, Done):
            bindings[_RUNTIME_BINDING] = {"status": "done", "result": result.value}
            frame = Frame(bindings=bindings, residuals=())
            offers: list[OfferSpec] = []
            status = "done"
            final = result.value
        else:
            transition = self.trusted.expected_transition(result.socket)
            if transition.label != result.operation:
                raise ValueError(
                    f"perform {result.operation!r} does not match current protocol label {transition.label!r}"
                )
            bindings[_RUNTIME_BINDING] = {
                "status": "awaiting",
                "socket": result.socket,
                "operation": result.operation,
            }
            frame = Frame(bindings=bindings, residuals=(await_to_data(result),))
            offers = [
                OfferSpec(
                    socket=result.socket,
                    direction=transition.direction,
                    label=result.operation,
                    payload=result.payload,
                    continuation=result.continuation,
                )
            ]
            status = "awaiting"
            final = None

        request_id = "publish:" + content_id(
            {
                "nema": nema,
                "expected_meta": expected_meta,
                "frame": frame.cid,
                "consume_receipts": consume_receipts,
            }
        )
        published = self.trusted.publish_frame(
            nema=nema,
            expected_meta_socket=expected_meta,
            frame=frame,
            offers=offers,
            consume_receipts=consume_receipts,
            request_id=request_id,
        )
        return RunState(
            nema=nema,
            frame=published["frame"],
            meta_socket=published["meta_socket"],
            status=status,
            offers=tuple(published["offers"]),
            result=final,
        )

    @staticmethod
    def _frame_await(frame: Frame) -> Await | None:
        if not frame.residuals:
            return None
        if len(frame.residuals) != 1:
            raise ValueError("v0 Runtime supports exactly one active residual per nema")
        return await_from_data(frame.residuals[0])
