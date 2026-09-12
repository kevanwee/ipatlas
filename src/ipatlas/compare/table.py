"""Build and render comparisons.

Citations are rendered as numbered footnotes rather than inline: a table with a statute
reference in every cell is unreadable, and an unreadable table gets skimmed, which defeats
the point of having citations at all. Every cell still carries its cite in the JSON form.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
from dataclasses import dataclass, field

from ..core import UNKNOWN, Atlas, Fact, Pack
from ..core.pack import NotRecordedError

# What a practitioner compares first, per right. Order is deliberate: the attributes that
# most often decide a filing or enforcement decision come first.
DEFAULT_ATTRIBUTES: dict[str, list[str]] = {
    "trade_mark": [
        "filing_system", "examination", "priority", "term", "renewal_grace",
        # `maintenance` is separate from renewal on purpose: the US § 8 declaration of use
        # is an independent obligation and the most commonly missed US trade mark deadline.
        "maintenance", "opposition", "use_requirement", "well_known_marks", "exhaustion",
        "border_measures", "criminal_sanctions", "madrid",
    ],
    "patent": [
        "filing_system", "examination", "priority", "term", "term_extension",
        "maintenance", "grace_period", "pct", "exhaustion", "border_measures",
    ],
    "utility_model": ["available", "term", "examination"],
    "registered_design": [
        "examination", "priority", "term", "grace_period", "hague",
        "unregistered_design_right",
    ],
    "copyright": [
        "registration", "term.literary_dramatic_musical_artistic", "term.sound_recording",
        "shorter_term_rule", "moral_rights", "fair_dealing", "safe_harbour",
    ],
    "trade_secret": ["statute", "basis", "elements", "criminal_sanctions"],
    "geographical_indication": ["registration", "protection_without_registration"],
    "plant_variety": ["term"],
}


@dataclass
class Cell:
    jurisdiction: str
    fact: Fact | None
    missing_reason: str | None = None

    @property
    def recorded(self) -> bool:
        return self.fact is not None

    def render(self, footnote: int | None = None) -> str:
        if self.fact is None:
            return UNKNOWN
        text = self.fact.render()
        return f"{text} [^{footnote}]" if footnote else text


@dataclass
class Table:
    right: str
    jurisdictions: list[str]
    attributes: list[str]
    as_of: dt.date
    cells: dict[tuple[str, str], Cell] = field(default_factory=dict)  # (attr, jur) -> Cell

    # -- access -----------------------------------------------------------------------

    def cell(self, attribute: str, jurisdiction: str) -> Cell:
        return self.cells[(attribute, jurisdiction)]

    @property
    def coverage(self) -> tuple[int, int]:
        """(recorded cells, total cells)."""
        total = len(self.attributes) * len(self.jurisdictions)
        return sum(1 for c in self.cells.values() if c.recorded), total

    @property
    def unverified(self) -> int:
        return sum(1 for c in self.cells.values()
                   if c.fact is not None and not c.fact.verified)

    def divergences(self) -> list[str]:
        """Attributes where the jurisdictions do not agree. The reason to build a table."""
        out = []
        for attr in self.attributes:
            seen = {
                self.cell(attr, j).fact.render_value()
                for j in self.jurisdictions
                if self.cell(attr, j).recorded
            }
            if len(seen) > 1:
                out.append(attr)
        return out

    # -- rendering --------------------------------------------------------------------

    def to_markdown(self, *, footnotes: bool = True) -> str:
        recorded, total = self.coverage
        head = [
            f"# {_label(self.right)} — {', '.join(self.jurisdictions)}",
            "",
            f"As at {self.as_of.isoformat()}. {recorded} of {total} cells recorded; "
            f"{self.unverified} unverified.",
            "",
        ]
        notes: list[tuple[int, Cell]] = []
        counter = 0

        cols = ["Attribute", *self.jurisdictions]
        rows = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
        for attr in self.attributes:
            cells = []
            for j in self.jurisdictions:
                c = self.cell(attr, j)
                n = None
                if footnotes and c.recorded and c.fact.cite:
                    counter += 1
                    n = counter
                    notes.append((n, c))
                cells.append(c.render(n).replace("|", "\\|"))
            rows.append(f"| **{_label(attr)}** | " + " | ".join(cells) + " |")

        out = head + rows
        div = self.divergences()
        if div:
            out += ["", "## Where they differ", ""]
            out += [f"- {_label(a)}" for a in div]
        gaps = [(a, j) for a in self.attributes for j in self.jurisdictions
                if not self.cell(a, j).recorded]
        if gaps:
            out += ["", "## Not recorded", ""]
            for attr, j in gaps:
                out.append(f"- {j} — {_label(attr)}: {self.cell(attr, j).missing_reason}")
        if notes:
            out += ["", "## Sources", ""]
            for n, c in notes:
                cite = c.fact.cite
                ref = f"[{cite.text}]({cite.url})" if cite.url else cite.text
                checked = c.fact.checked.isoformat() if c.fact.checked else "unchecked"
                status = "verified" if c.fact.verified else "UNVERIFIED"
                out.append(f"[^{n}]: {c.jurisdiction} — {ref} ({status}, checked {checked})")
        return "\n".join(out)

    def to_csv(self) -> str:
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        w.writerow(["attribute", "jurisdiction", "value", "verified", "cite", "url",
                    "checked", "notes"])
        for attr in self.attributes:
            for j in self.jurisdictions:
                c = self.cell(attr, j)
                if not c.recorded:
                    w.writerow([attr, j, UNKNOWN, "", "", "", "", c.missing_reason or ""])
                    continue
                f = c.fact
                w.writerow([attr, j, f.render_value(), "yes" if f.verified else "no",
                            f.cite.text if f.cite else "", f.cite.url if f.cite else "",
                            f.checked.isoformat() if f.checked else "", "; ".join(f.notes)])
        return buf.getvalue()

    def to_dict(self) -> dict:
        recorded, total = self.coverage
        return {
            "right": self.right,
            "as_of": self.as_of.isoformat(),
            "jurisdictions": self.jurisdictions,
            "attributes": self.attributes,
            "coverage": {"recorded": recorded, "total": total, "unverified": self.unverified},
            "divergences": self.divergences(),
            "cells": [
                {"attribute": a, "jurisdiction": j,
                 **({"fact": self.cell(a, j).fact.to_dict()} if self.cell(a, j).recorded
                    else {"fact": None, "reason": self.cell(a, j).missing_reason})}
                for a in self.attributes for j in self.jurisdictions
            ],
        }


def _label(s: str) -> str:
    return s.rsplit(".", 1)[-1].replace("_", " ").capitalize() if "." in s \
        else s.replace("_", " ").capitalize()


# -- builders ---------------------------------------------------------------------------


def compare(atlas: Atlas, right: str, jurisdictions: list[str],
            attributes: list[str] | None = None, *,
            as_of: dt.date | None = None) -> Table:
    """Compare one right across jurisdictions. Unknown attributes are reported, not guessed."""
    when = as_of or dt.date.today()
    if right not in DEFAULT_ATTRIBUTES:
        raise NotRecordedError(
            f"unknown right {right!r}; known: {', '.join(sorted(DEFAULT_ATTRIBUTES))}"
        )
    attrs = attributes or DEFAULT_ATTRIBUTES[right]
    codes = [j.upper() for j in jurisdictions]
    table = Table(right=right, jurisdictions=codes, attributes=attrs, as_of=when)
    for code in codes:
        pack = atlas[code]  # raises NotRecordedError with the loaded list if absent
        available = pack.has_right(right)
        for attr in attrs:
            path = attr if attr.startswith(f"{right}.") else f"{right}.{attr}"
            if not available:
                table.cells[(attr, code)] = Cell(
                    code, None, f"{pack.name} does not provide this right")
                continue
            try:
                table.cells[(attr, code)] = Cell(code, pack.get(path, as_of=when))
            except NotRecordedError as e:
                table.cells[(attr, code)] = Cell(code, None, str(e).split(": ", 1)[-1])
    return table


def brief(pack: Pack, right: str, *, as_of: dt.date | None = None) -> str:
    """One-page country note for a right, assembled from the pack. Gaps are shown as gaps."""
    when = as_of or dt.date.today()
    if not pack.has_right(right):
        f = pack.try_get(right) or pack.try_get(f"{right}.available")
        reason = "; ".join(f.notes) if f and f.notes else "not available in this jurisdiction"
        return (f"# {pack.name} — {_label(right)}\n\n**Not available.** {reason}\n")

    prefix = f"{right}."
    paths = [p for p in pack.attributes(prefix)]
    ordered = [f"{right}.{a}" if not a.startswith(prefix) else a
               for a in DEFAULT_ATTRIBUTES.get(right, [])]
    rest = [p for p in paths if p not in ordered]
    shown = [p for p in ordered if p in paths] + rest

    out = [f"# {pack.name} — {_label(right)}", ""]
    office = f"{pack.office_name} ({pack.office})" if pack.office_name else pack.office
    if office:
        out += [f"Office: {office}. As at {when.isoformat()}.", ""]
    unverified = sum(1 for p in shown if (f := pack.try_get(p, as_of=when)) and not f.verified)
    if unverified:
        out += [f"> {unverified} of {len(shown)} recorded facts below are **unverified**. "
                "Check each against the cited source before relying on it.", ""]

    for path in shown:
        f = pack.try_get(path, as_of=when)
        if f is None:
            continue
        label = _label(path)
        if f.value is None and not f.extra:
            if f.notes:
                out += [f"**{label}** — not recorded.", *[f"  - {n}" for n in f.notes], ""]
            continue
        line = f"**{label}**: {f.render()}"
        if f.cite:
            src = f"[{f.cite.text}]({f.cite.url})" if f.cite.url else f.cite.text
            line += f"  \n  Source: {src}"
            if f.checked:
                line += f" (checked {f.checked.isoformat()})"
        out.append(line)
        out += [f"  - {n}" for n in f.notes]
        out.append("")

    missing = [a for a in DEFAULT_ATTRIBUTES.get(right, [])
               if pack.try_get(f"{right}.{a}" if not a.startswith(prefix) else a,
                               as_of=when) is None]
    if missing:
        out += ["## Not recorded", "",
                "These attributes are in the comparison set but absent from this pack:", ""]
        out += [f"- {_label(a)}" for a in missing]
        out += ["", "They are gaps in the data, not statements that the law is silent.", ""]
    return "\n".join(out)
