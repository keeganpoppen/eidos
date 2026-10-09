"""Meta-protocol role vocabulary.

Elaborator and Actualizer are ordinary semantic roles. The Trusted Machinery
experiments materialize authority to occupy these roles as ordinary live
projection capabilities rather than bespoke authority tokens.
"""

ELABORATOR_ROLE = "Elaborator"
ACTUALIZER_ROLE = "Actualizer"


def elaborator_state(cut: str) -> str:
    return f"cut:{cut}"


def actualizer_state(possibility: str) -> str:
    return f"possibility:{possibility}"
