"""Data quality gate. Runs in CI; a pack that fails does not ship.

The rules here are the mechanism behind CLAUDE.md's non-negotiables: a fact without a
citation is an error, and a fact nobody has re-checked in two years is an error too,
because silently stale data is the failure mode this whole project exists to avoid.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from .fact import Fact
from .pack import Atlas, Pack

STALE_WARN_MONTHS = 12
STALE_ERROR_MONTHS = 24

# Closed enumerations. A pack may not invent a member; widening is an engine PR.
ENUMS: dict[str, frozenset[str]] = {
    # first_to_invent is historical (pre-AIA US) but must be expressible, because history
    # entries are linted exactly as current facts are.
    "filing_system": frozenset({"first_to_file", "first_to_use", "first_to_invent", "mixed"}),
    "examination": frozenset({"none", "formal", "substantive", "deferred", "registration_only"}),
    "exhaustion": frozenset({"national", "regional", "international", "unsettled", "mixed"}),
    "registration": frozenset({"none", "available", "required", "not_available"}),
    "recordal": frozenset({"mandatory", "optional", "not_available"}),
    "government_approval": frozenset({"true", "false", "conditional"}),
}

# Paths where a missing citation is acceptable: `available` is structural, and a `statute`
# entry is itself the citation (its `name` is what a practitioner would cite).
CITE_EXEMPT_SUFFIXES = ("available", "statute")


@dataclass
class Finding:
    severity: str  # "error" | "warn"
    jurisdiction: str
    path: str
    message: str

    def __str__(self) -> str:
        return f"[{self.severity.upper():5}] {self.jurisdiction}:{self.path} -- {self.message}"


def _months_between(a: dt.date, b: dt.date) -> int:
    return (b.year - a.year) * 12 + (b.month - a.month)


def _enum_for(path: str) -> frozenset[str] | None:
    leaf = path.rsplit(".", 1)[-1]
    return ENUMS.get(leaf)


def lint_fact(f: Fact, *, as_of: dt.date) -> list[Finding]:
    out: list[Finding] = []
    has_value = f.value is not None or bool(f.extra)
    informational = not has_value and bool(f.notes) and not f.is_group_note

    if has_value and f.cite is None and not f.path.endswith(CITE_EXEMPT_SUFFIXES):
        # A negative fact asserts that no provision exists, which is often uncitable.
        severity = "warn" if f.is_negative else "error"
        detail = ("asserts an absence with no citation; cite the provision that would "
                  "have granted the right, or a source confirming the gap"
                  if f.is_negative else
                  "fact has a value but no `cite`; an uncited value is not a fact")
        out.append(Finding(severity, f.jurisdiction, f.path, detail))
    if has_value and f.checked is None:
        out.append(Finding("error", f.jurisdiction, f.path,
                           "no `checked` date; set it here or in the file `defaults`"))
    elif f.checked is not None:
        if f.checked > as_of:
            out.append(Finding("error", f.jurisdiction, f.path,
                               f"`checked` is in the future ({f.checked.isoformat()})"))
        else:
            age = _months_between(f.checked, as_of)
            if age >= STALE_ERROR_MONTHS:
                out.append(Finding("error", f.jurisdiction, f.path,
                                   f"last checked {age} months ago; re-check or remove"))
            elif age >= STALE_WARN_MONTHS:
                out.append(Finding("warn", f.jurisdiction, f.path,
                                   f"last checked {age} months ago"))
    if f.verified and f.cite is None:
        out.append(Finding("error", f.jurisdiction, f.path,
                           "`verified: true` without a citation"))
    if f.verified and not f.notes:
        out.append(Finding("warn", f.jurisdiction, f.path,
                           "`verified: true` with no note recording what was checked"))
    if informational and not has_value:
        out.append(Finding("warn", f.jurisdiction, f.path,
                           "note with no value; record the fact or delete the placeholder"))

    enum = _enum_for(f.path)
    if enum is not None and isinstance(f.value, str) and f.value not in enum:
        out.append(Finding("error", f.jurisdiction, f.path,
                           f"value {f.value!r} is not in the closed set for this attribute "
                           f"({', '.join(sorted(enum))})"))
    if enum is not None and f.value == "unsettled" and not f.notes:
        out.append(Finding("error", f.jurisdiction, f.path,
                           "`unsettled` must carry a note explaining the uncertainty"))
    if f.in_force_until and f.in_force_from and f.in_force_until < f.in_force_from:
        out.append(Finding("error", f.jurisdiction, f.path,
                           "in_force_until precedes in_force_from"))
    return out


def lint_pack(pack: Pack, *, as_of: dt.date | None = None) -> list[Finding]:
    when = as_of or dt.date.today()
    out: list[Finding] = []
    for f in pack.facts.values():
        out.extend(lint_fact(f, as_of=when))
    for path, versions in pack.history.items():
        for f in versions:
            out.extend(lint_fact(f, as_of=when))
        # History must not overlap, and must not extend past a current fact's start.
        for a, b in zip(versions, versions[1:], strict=False):
            if a.in_force_until and b.in_force_from and a.in_force_until >= b.in_force_from:
                out.append(Finding("error", pack.jurisdiction, f"history.{path}",
                                   "overlapping validity periods"))
        current = pack.facts.get(path)
        if current is None:
            out.append(Finding("error", pack.jurisdiction, f"history.{path}",
                               "history for a path with no current fact"))
        elif current.in_force_from is None:
            out.append(Finding("error", pack.jurisdiction, path,
                               "has history but no `in_force_from` of its own, so a dated "
                               "query cannot tell which version applies"))
    for path, versions in pack.pending.items():
        for f in versions:
            out.extend(lint_fact(f, as_of=when))
            if f.adopted and f.in_force_from and f.adopted > f.in_force_from:
                out.append(Finding("error", pack.jurisdiction, f"pending.{path}",
                                   "adopted after in_force_from: an instrument cannot "
                                   "commence before it is adopted"))
        for a, b in zip(versions, versions[1:], strict=False):
            if a.in_force_until and b.in_force_from and a.in_force_until >= b.in_force_from:
                out.append(Finding("error", pack.jurisdiction, f"pending.{path}",
                                   "overlapping validity periods"))
        current = pack.facts.get(path)
        if current is None:
            out.append(Finding("error", pack.jurisdiction, f"pending.{path}",
                               "pending version for a path with no current fact"))
        elif current.in_force_until is None and versions:
            # Resolution is still correct, because `pending` is searched first. But an
            # unbounded current fact reads as though it applies indefinitely.
            out.append(Finding("warn", pack.jurisdiction, path,
                               f"has a pending version from "
                               f"{versions[0].in_force_from.isoformat()} but no "
                               "`in_force_until` of its own; resolution is unaffected but the "
                               "current entry reads as if it applied indefinitely"))
    if not pack.office:
        out.append(Finding("warn", pack.jurisdiction, "office",
                           "no office recorded; deadline computation needs one"))
    return out


def lint_atlas(atlas: Atlas, *, as_of: dt.date | None = None) -> list[Finding]:
    out = []
    for code in atlas.codes:
        out.extend(lint_pack(atlas[code], as_of=as_of))
    return out


def errors(findings: list[Finding]) -> list[Finding]:
    return [f for f in findings if f.severity == "error"]


def summarise(findings: list[Finding]) -> str:
    n_err = len(errors(findings))
    return f"{len(findings)} finding(s): {n_err} error(s), {len(findings) - n_err} warning(s)"
