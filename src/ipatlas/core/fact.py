"""The Fact: a legal value plus the provenance that makes it checkable.

Every leaf in a jurisdiction pack becomes a Fact. A Fact without a citation is a rumour;
the linter treats it as an error. A Fact that has not been checked against the source
carries `verified: false` and every output surface must show that.

Packs are written in short form for readability. This module defines the expansion:

    term: { years: 10, from: filing_date, cite: "TMA ss 18-19" }

        -> Fact(value={"years": 10, "from": "filing_date"}, cite="TMA ss 18-19")

    exhaustion: { value: international, exceptions: [...], cite: "TMA s 29" }

        -> Fact(value="international", extra={"exceptions": [...]}, cite="TMA s 29")
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

# Keys that describe a fact rather than form part of its value.
PROVENANCE_KEYS = frozenset({
    "value", "cite", "url", "checked", "verified", "notes", "in_force_from", "in_force_until",
    "adopted",
})

UNKNOWN = "not recorded"


@dataclass(frozen=True)
class Cite:
    """A citation, as a practitioner in the jurisdiction would write it."""

    text: str
    url: str | None = None

    def __str__(self) -> str:
        return self.text


@dataclass
class Fact:
    """A legal value with provenance and temporal validity."""

    path: str  # dotted address within the pack, e.g. "trade_mark.term"
    jurisdiction: str
    value: Any
    extra: dict[str, Any] = field(default_factory=dict)
    cite: Cite | None = None
    checked: dt.date | None = None
    verified: bool = False
    notes: list[str] = field(default_factory=list)
    in_force_from: dt.date | None = None
    in_force_until: dt.date | None = None
    # When the instrument was ADOPTED, which is not when it comes into force. The gap is
    # load-bearing for advice: an applicant filing in December 2026 is already deciding
    # against rules that take effect on 1 January 2027.
    adopted: dt.date | None = None
    # True when this entry only carries commentary attached to a group of facts (e.g. a note
    # on `copyright.term` covering all its branches). Such an entry has no value by design.
    is_group_note: bool = False

    @property
    def is_negative(self) -> bool:
        """A fact asserting the absence of a right or requirement.

        You can rarely cite the absence of a provision, so the linter holds these to a
        warning rather than an error on missing provenance.
        """
        if self.value is False:
            return True
        if isinstance(self.value, str) and self.value in {"none", "not_available", "false"}:
            return True
        if isinstance(self.value, dict) and self.value:
            return all(v is False for v in self.value.values())
        return False

    # -- temporal ---------------------------------------------------------------------

    def in_force_on(self, when: dt.date) -> bool:
        if self.in_force_from and when < self.in_force_from:
            return False
        return not (self.in_force_until and when > self.in_force_until)

    # -- presentation -----------------------------------------------------------------

    @property
    def flag(self) -> str:
        """Marker shown next to the value wherever it is rendered. Never suppress this."""
        return "" if self.verified else " [unverified]"

    def render_value(self) -> str:
        return _render(self.value, self.extra)

    def render(self) -> str:
        return self.render_value() + self.flag

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "jurisdiction": self.jurisdiction,
            "value": self.value,
            "extra": self.extra or None,
            "cite": self.cite.text if self.cite else None,
            "url": self.cite.url if self.cite else None,
            "checked": self.checked.isoformat() if self.checked else None,
            "verified": self.verified,
            "notes": self.notes or None,
            "in_force_from": self.in_force_from.isoformat() if self.in_force_from else None,
            "in_force_until": self.in_force_until.isoformat() if self.in_force_until else None,
            "adopted": self.adopted.isoformat() if self.adopted else None,
        }


# -- value rendering -------------------------------------------------------------------

_HUMAN = {
    "renewable": "renewable", "renewal_years": "renewal term (years)",
    "max_years": "maximum (years)", "non_use_years": "non-use period (years)",
    "window_months": "window (months)", "window_days": "window (days)",
    "national_phase_months": "national phase (months)",
    "refusal_window_months": "refusal window (months)",
    "grace_months": "grace (months)", "plus_years": "plus years",
}

# Shapes that recur across packs and deserve to read as a lawyer would say them, because
# these are the cells a comparison table is actually read for.
_DURATION_KEYS = ("years", "months", "days")


def _duration(d: dict) -> str | None:
    for k in _DURATION_KEYS:
        if isinstance(d.get(k), int | float):
            unit = k[:-1] if d[k] == 1 else k
            return f"{d[k]} {unit}"
    return None


def _phrase(value: dict) -> tuple[str, set[str]] | None:
    """Render a recognised shape, returning the phrase and the keys it consumed."""
    used: set[str] = set()

    # "10 years from the filing date, renewable for 10 years"
    dur = _duration(value)
    if dur and "from" in value:
        used |= {*_DURATION_KEYS, "from"}
        text = f"{dur} from {_scalar(value['from'])}"
        if value.get("renewable"):
            used.add("renewable")
            if "renewal_years" in value:
                used.add("renewal_years")
                text += f", renewable for {value['renewal_years']} years"
            else:
                text += ", renewable"
        elif value.get("renewable") is False:
            used.add("renewable")
            text += ", not renewable"
        if "max_years" in value:
            used.add("max_years")
            text += f" (maximum {value['max_years']} years)"
        return text, used

    # "author death plus 70 years", or with an alternative limb:
    # "publication plus 95 years, or creation plus 120 years, whichever is earlier"
    if "base" in value and "plus_years" in value:
        used |= {"base", "plus_years"}
        text = f"{_scalar(value['base'])} plus {value['plus_years']} years"
        alt = value.get("alt")
        if isinstance(alt, dict) and "base" in alt and "plus_years" in alt:
            used.add("alt")
            text += f", or {_scalar(alt['base'])} plus {alt['plus_years']} years"
            if "rule" in value:
                used.add("rule")
                text += f", whichever is {_scalar(value['rule'])}"
        return text, used

    # "3 years -> cancellation on application"
    if "non_use_years" in value and "consequence" in value:
        used |= {"non_use_years", "consequence"}
        text = f"{value['non_use_years']} years of non-use, then {_scalar(value['consequence'])}"
        if "from" in value:
            used.add("from")
            text += f" (from {_scalar(value['from'])})"
        return text, used

    # "2 months from publication, extendable to 6"
    window = next((k for k in ("window_months", "window_days") if k in value), None)
    if window and "from" in value:
        used |= {window, "from"}
        unit = "months" if window.endswith("months") else "days"
        text = f"{value[window]} {unit} from {_scalar(value['from'])}"
        if value.get("extendable") is True:
            used.add("extendable")
            text += " (extendable"
            if "max_extension_months" in value:
                used.add("max_extension_months")
                text += f" by up to {value['max_extension_months']} months"
            text += ")"
        elif value.get("extendable") is False:
            used.add("extendable")
            text += " (not extendable)"
        return text, used

    return None


def _scalar(v: Any) -> str:
    if v is None:
        return UNKNOWN
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, dt.date):
        return v.isoformat()
    if isinstance(v, list):
        return ", ".join(_scalar(x) for x in v) if v else UNKNOWN
    return str(v).replace("_", " ")


def _render(value: Any, extra: dict[str, Any] | None = None) -> str:
    if isinstance(value, dict):
        parts: list[str] = []
        consumed: set[str] = set()
        shaped = _phrase(value)
        if shaped:
            phrase, consumed = shaped
            parts.append(phrase)
        for k, v in value.items():
            if k in consumed:
                continue
            label = _HUMAN.get(k, k.replace("_", " "))
            if isinstance(v, bool):
                parts.append(label if v else f"not {label}")
            else:
                parts.append(f"{label} {_scalar(v)}" if k in _HUMAN else f"{label}: {_scalar(v)}")
        body = "; ".join(parts)
    else:
        body = _scalar(value)
    if extra:
        quals = "; ".join(f"{k.replace('_', ' ')}: {_scalar(v)}" for k, v in extra.items())
        body = f"{body} ({quals})" if body != UNKNOWN else quals
    return body


# -- parsing ---------------------------------------------------------------------------


def is_fact_mapping(node: Any) -> bool:
    """A mapping is a Fact if it declares provenance, or if it is a flat leaf mapping.

    A mapping with nested mappings and no `value`/`cite` of its own is a *group* whose
    children are facts (e.g. `trade_mark:`, or `copyright.term:`).
    """
    if not isinstance(node, dict):
        return False
    if {"value", "cite", "verified", "in_force_from"} & node.keys():
        return True
    payload = {k: v for k, v in node.items() if k not in PROVENANCE_KEYS}
    if not payload:
        return True  # provenance only, e.g. {notes: [...]} -- a fact with no value
    return not any(isinstance(v, dict) for v in payload.values())


def _date(v: Any, where: str) -> dt.date | None:
    if v is None:
        return None
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    if isinstance(v, str):
        return dt.date.fromisoformat(v)
    raise ValueError(f"{where}: expected a date, got {v!r}")


def parse_fact(node: Any, *, path: str, jurisdiction: str, defaults: dict[str, Any]) -> Fact:
    """Expand a pack node into a Fact. `defaults` supplies file-level checked/verified."""
    if not isinstance(node, dict):
        # A bare scalar or list is a value with no provenance at all; the linter will say so.
        return Fact(path=path, jurisdiction=jurisdiction, value=node,
                    checked=_date(defaults.get("checked"), path),
                    verified=bool(defaults.get("verified", False)))

    payload = {k: v for k, v in node.items() if k not in PROVENANCE_KEYS}
    if "value" in node:
        value, extra = node["value"], payload
    elif payload:
        value, extra = payload, {}
    else:
        value, extra = None, {}

    cite_text = node.get("cite")
    cite = Cite(str(cite_text), node.get("url")) if cite_text else None
    notes = node.get("notes") or []
    if isinstance(notes, str):
        notes = [notes]

    return Fact(
        path=path,
        jurisdiction=jurisdiction,
        value=value,
        extra=extra,
        cite=cite,
        checked=_date(node.get("checked", defaults.get("checked")), path),
        verified=bool(node.get("verified", defaults.get("verified", False))),
        notes=list(notes),
        in_force_from=_date(node.get("in_force_from"), path),
        in_force_until=_date(node.get("in_force_until"), path),
        adopted=_date(node.get("adopted"), path),
    )
