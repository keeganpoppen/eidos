# Eidos v0 semantics checkpoint

This is deliberately a small executable hypothesis, not a final ontology.

## Vocabulary

- **Value** — immutable structural data.
- **Name** — permanent opaque identity. Names contain no routing semantics.
- **Frame** — immutable local causal cut: bindings plus residual computations.
- **Socket** — named, authority-bearing local projection of a session continuation.
- **Protocol** — immutable description of legal socket transitions.
- **Match** — durable causal fact consuming compatible socket occurrences and producing successor occurrences.

A socket occurrence is **single-spend, not single-Frame**. A live socket may be referenced unchanged across many Frames. Once a rendezvous advances it, the old occurrence is spent and successor occurrence(s) are freshly named.

## Trusted Machinery

Trusted Machinery alone guarantees:

1. successfully reserved Names never collide or get reused;
2. candidate Frame publication is atomic with its published offers and successor meta socket;
3. a socket occurrence has one authoritative disposition at a time;
4. a socket occurrence can be spent at most once;
5. Matches consume actually compatible offered sockets and immutably record the causal rendezvous;
6. receipts survive crashes independently of whether either participant has incorporated them;
7. copying historical Values/Frames never duplicates live authority.

`live` does **not** mean running, resident, reachable, or recently pinged. It means Trusted Machinery still recognizes that socket occurrence as current unspent authority. `offered` is a committed suspended perform: still unspent, but no longer freely usable by its holder while the offer is outstanding.

## Eidos / Praxis

Bindings remain ordinary Eidos data. Rebinding constructs another immutable Frame; it is not a Trusted-Machinery mutation primitive.

Praxis performs local reduction until it encounters `perform`. The remainder is represented explicitly as a serializable continuation (`Await`). Trusted Machinery determines whether the named socket can legally participate in an external transition.

The v0 implementation intentionally keeps `reserve_name`, `open_session`, `publish_frame`, `match`, and `transfer_socket` explicit. A later calculus may desugar them through the meta protocol once we have proved the collapse rather than merely admired it.

## Causal durability

A Match becoming durable establishes that the rendezvous happened. It does **not** establish that either participant has already incorporated the resulting receipt into its next Frame. Those are separate local causal facts.

This is intentionally log-structured / write-ahead in spirit:

1. local intent becomes durable as an offered socket operation;
2. a compatible pair is durably matched;
3. durable receipts become available to both holders;
4. each holder independently incorporates its receipt and publishes a later Frame.

No simultaneous remote observation is assumed.
