"""Deadline computation over office calendars.

Periods come from the jurisdiction and treaty packs, so the citation travels with the
answer. Arithmetic happens here and is deterministic. Every result carries a trace.
"""

from .engine import (
    Deadline,
    PeriodSource,
    deadline_from_fact,
    madrid_refusal_deadline,
    opposition_deadline,
    pct_national_phase,
    priority_deadline,
)

__all__ = [
    "Deadline",
    "PeriodSource",
    "deadline_from_fact",
    "priority_deadline",
    "pct_national_phase",
    "opposition_deadline",
    "madrid_refusal_deadline",
]
