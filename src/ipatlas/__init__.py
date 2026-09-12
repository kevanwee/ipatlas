"""ipatlas: cross-border intellectual property as structured, cited data.

    load_atlas()                     every jurisdiction pack
    compare(atlas, right, ...)       cited comparison table across jurisdictions
    brief(pack, right)               one-page country note, with gaps shown as gaps
    lint_atlas(atlas)                the data quality gate

Nothing in this package infers a legal fact. If a pack does not record something, the
answer is "not recorded".
"""

from .compare import DEFAULT_ATTRIBUTES, Table, brief, compare
from .core import (
    Atlas,
    Cite,
    Fact,
    Finding,
    NotRecordedError,
    Pack,
    PackError,
    lint_atlas,
    lint_pack,
    load_atlas,
    load_pack,
    load_treaty,
    summarise,
)

__all__ = [
    "load_atlas", "load_pack", "load_treaty", "Atlas", "Pack", "Fact", "Cite",
    "NotRecordedError", "PackError",
    "compare", "brief", "Table", "DEFAULT_ATTRIBUTES",
    "lint_atlas", "lint_pack", "Finding", "summarise",
]

__version__ = "0.1.0"
