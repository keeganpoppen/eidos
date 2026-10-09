# Historical experiments

These files preserve pressure tests that materially shaped the current Eidos model but are no longer part of the live architecture or active test suite.

In particular:

- Facets and structural dispatch established that local wrapper/handler behavior can collapse into ordinary Values, closures, and Core `perform`.
- The one-frontier and recursive-frontier occurrence experiments established the possibility -> occurrence -> elaboration cycle, then exposed the false-global-frontier assumption later replaced by observer-relative cuts.

Current semantics live in the top-level `src/eidos` modules and current docs. These archived experiments are retained for archaeology, counterexamples, and regression of ideas—not as normative APIs.
