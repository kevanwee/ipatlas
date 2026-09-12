"""Core: the data model, the loader, and the quality gate. No legal logic lives here."""

from .fact import UNKNOWN, Cite, Fact, parse_fact
from .lint import Finding, lint_atlas, lint_pack, summarise
from .pack import (
    RIGHTS,
    Atlas,
    NotRecordedError,
    Pack,
    PackError,
    load_atlas,
    load_pack,
    load_treaty,
)

__all__ = [
    "Fact", "Cite", "parse_fact", "UNKNOWN",
    "Pack", "Atlas", "load_pack", "load_atlas", "load_treaty",
    "NotRecordedError", "PackError", "RIGHTS",
    "Finding", "lint_pack", "lint_atlas", "summarise",
]
