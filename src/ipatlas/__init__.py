"""ipatlas: cross-border intellectual property as structured, cited data.

    load_atlas()                     every jurisdiction pack
    load_offices()                   office computation rules + closure calendars
    compare(atlas, right, ...)       cited comparison table across jurisdictions
    brief(pack, right)               one-page country note, with gaps shown as gaps
    priority_deadline(...)           Paris / PCT / Madrid / opposition deadlines, with traces
    term_expiry(...)                 registered-right expiry and renewal schedule
    copyright_term(...)              copyright term expressions
    routes(atlas, right, targets)    filing-route matrix from treaty membership
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
from .deadlines import (
    Deadline,
    deadline_from_fact,
    madrid_refusal_deadline,
    opposition_deadline,
    pct_national_phase,
    priority_deadline,
)
from .lifecycle import (
    CopyrightTerm,
    TermResult,
    copyright_term,
    renewal_schedule,
    term_expiry,
)
from .offices import (
    CalendarDataMissingError,
    Office,
    Offices,
    load_office,
    load_offices,
    load_treaty_pack,
)
from .routes import RouteMatrix, routes

__all__ = [
    # data
    "load_atlas", "load_pack", "load_treaty", "Atlas", "Pack", "Fact", "Cite",
    "NotRecordedError", "PackError",
    "load_offices", "load_office", "load_treaty_pack", "Office", "Offices",
    "CalendarDataMissingError",
    # engines
    "compare", "brief", "Table", "DEFAULT_ATTRIBUTES",
    "Deadline", "priority_deadline", "pct_national_phase", "opposition_deadline",
    "madrid_refusal_deadline", "deadline_from_fact",
    "term_expiry", "renewal_schedule", "copyright_term", "TermResult", "CopyrightTerm",
    "routes", "RouteMatrix",
    # quality gate
    "lint_atlas", "lint_pack", "Finding", "summarise",
]

__version__ = "0.2.0"
