"""Term and renewal computation.

The `term` fact records the period and the event it runs from. The caller supplies the dates
it knows; if the pack says the term runs from registration and the caller has only a filing
date, the answer is a refusal, not a guess. That asymmetry is the whole point: SG trade mark
terms run from filing and US/CN terms run from registration, so the same mark expires on
different dates and the engine must not paper over which date it needs.
"""

from __future__ import annotations

import calendar as _calmod
import datetime as dt
from dataclasses import dataclass, field

from ..core import Atlas, Cite, NotRecordedError

# The closed set of events a term may run from. Extending this is an engine change with a
# test, never a pack change (CLAUDE.md, Data conventions).
BASES = frozenset({
    "filing_date", "registration_date", "grant_date", "priority_date",
    "publication", "creation", "fixation", "author_death", "first_sale",
    "international_registration_date",
})


class MissingDateError(LookupError):
    """The pack's term runs from an event the caller did not supply a date for."""


def _add_years(d: dt.date, years: int) -> dt.date:
    try:
        return d.replace(year=d.year + years)
    except ValueError:  # 29 February into a non-leap year
        return d.replace(year=d.year + years, day=_calmod.monthrange(d.year + years, d.month)[1])


@dataclass
class RenewalWindow:
    number: int  # 1 = first renewal
    due: dt.date
    grace_until: dt.date | None = None
    restoration_until: dt.date | None = None
    window_opens: dt.date | None = None


@dataclass
class TermResult:
    right: str
    jurisdiction: str
    base: str
    base_date: dt.date
    expiry: dt.date
    renewable: bool
    max_expiry: dt.date | None = None
    renewals: list[RenewalWindow] = field(default_factory=list)
    cite: Cite | None = None
    verified: bool = False
    trace: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "right": self.right,
            "jurisdiction": self.jurisdiction,
            "base": self.base,
            "base_date": self.base_date.isoformat(),
            "first_expiry": self.expiry.isoformat(),
            "renewable": self.renewable,
            "max_expiry": self.max_expiry.isoformat() if self.max_expiry else None,
            "renewals": [
                {"number": r.number, "due": r.due.isoformat(),
                 "window_opens": r.window_opens.isoformat() if r.window_opens else None,
                 "grace_until": r.grace_until.isoformat() if r.grace_until else None,
                 "restoration_until": (r.restoration_until.isoformat()
                                       if r.restoration_until else None)}
                for r in self.renewals
            ],
            "cite": self.cite.text if self.cite else None,
            "verified": self.verified,
            "trace": list(self.trace),
            "warnings": list(self.warnings),
        }

    def render(self) -> str:
        return "\n".join([*self.trace, *(f"WARNING: {w}" for w in self.warnings)])


def _fmt(d: dt.date) -> str:
    return f"{d.isoformat()} ({d.strftime('%a')})"


def term_expiry(atlas: Atlas, right: str, jurisdiction: str, dates: dict[str, dt.date], *,
                renewals: int = 0, as_of: dt.date | None = None) -> TermResult:
    """First expiry of a registered right, plus optional renewal schedule.

    `dates` maps a base name (see BASES) to a date, e.g. {"filing_date": date(2020, 3, 1)}.
    """
    pack = atlas[jurisdiction]
    fact = pack.try_get(f"{right}.term", as_of=as_of)
    if fact is None or not isinstance(fact.value, dict):
        raise NotRecordedError(f"{jurisdiction}: {right}.term is not recorded")
    spec = fact.value
    years = spec.get("years")
    base = spec.get("from")
    if not isinstance(years, int) or base not in BASES:
        raise NotRecordedError(
            f"{jurisdiction}: {right}.term does not record an integer `years` and a known "
            f"`from` base (got years={years!r}, from={base!r})"
        )
    if base not in dates:
        raise MissingDateError(
            f"{jurisdiction} {right} term runs from {base}, which you did not supply. "
            f"Supplied: {', '.join(sorted(dates)) or 'nothing'}. This matters: a term running "
            "from registration expires later than one running from filing."
        )

    base_date = dates[base]
    expiry = _add_years(base_date, years)
    trace = [
        f"{pack.name} {right.replace('_', ' ')} term",
        f"term: {years} years from {base.replace('_', ' ')}"
        + ("" if fact.verified else " [unverified]"),
        f"source: {fact.cite or 'NONE'}",
        f"{base.replace('_', ' ')}: {_fmt(base_date)}",
        f"+ {years} years = {_fmt(expiry)}",
    ]
    warnings = []
    if not fact.verified:
        warnings.append(f"{jurisdiction}:{right}.term is unverified; check it against "
                        f"{fact.cite or 'the statute'}")
    if base_date.month == 2 and base_date.day == 29:
        trace.append("  base date is 29 February; expiry clamped to the month end where the "
                     "target year is not a leap year")

    renewable = bool(spec.get("renewable"))
    renewal_years = spec.get("renewal_years", years)
    max_years = spec.get("max_years")
    max_expiry = _add_years(base_date, max_years) if isinstance(max_years, int) else None
    if max_expiry:
        trace.append(f"maximum duration {max_years} years from {base.replace('_', ' ')} "
                     f"= {_fmt(max_expiry)}")

    schedule: list[RenewalWindow] = []
    if renewals and not renewable:
        warnings.append(f"{renewals} renewal(s) requested but the pack records this right as "
                        "not renewable; no schedule produced")
    elif renewals:
        grace = pack.try_get(f"{right}.renewal_grace", as_of=as_of)
        g = grace.value if grace and isinstance(grace.value, dict) else {}
        grace_months = g.get("months")
        window_before = g.get("window_before_expiry_months")
        restore_after = g.get("restoration_after_grace_months")
        if grace:
            trace.append(f"renewal grace: {grace.render_value()} ({grace.cite or 'no cite'})")
        cur = expiry
        for n in range(1, renewals + 1):
            if max_expiry and cur >= max_expiry:
                trace.append(f"renewal {n} would run past the maximum duration; stopped")
                break
            w = RenewalWindow(number=n, due=cur)
            if isinstance(window_before, int):
                w.window_opens = _add_months(cur, -window_before)
            if isinstance(grace_months, int):
                w.grace_until = _add_months(cur, grace_months)
                if isinstance(restore_after, int):
                    w.restoration_until = _add_months(w.grace_until, restore_after)
            schedule.append(w)
            nxt = _add_years(cur, renewal_years)
            cur = min(nxt, max_expiry) if max_expiry else nxt
        for w in schedule:
            bits = [f"renewal {w.number} due {_fmt(w.due)}"]
            if w.window_opens:
                bits.append(f"window opens {w.window_opens.isoformat()}")
            if w.grace_until:
                bits.append(f"grace to {w.grace_until.isoformat()}")
            if w.restoration_until:
                bits.append(f"restoration to {w.restoration_until.isoformat()}")
            trace.append("  " + "; ".join(bits))

    trace.append("note: renewal and grace dates are computed from the recorded periods and "
                 "are not adjusted for office closures; run them through the deadline engine "
                 "for a filing date.")
    return TermResult(right=right, jurisdiction=jurisdiction, base=base, base_date=base_date,
                      expiry=expiry, renewable=renewable, max_expiry=max_expiry,
                      renewals=schedule, cite=fact.cite, verified=fact.verified,
                      trace=trace, warnings=warnings)


def _add_months(d: dt.date, months: int) -> dt.date:
    total = d.month - 1 + months
    year = d.year + total // 12
    month = total % 12 + 1
    last = _calmod.monthrange(year, month)[1]
    return dt.date(year, month, min(d.day, last))


def renewal_schedule(atlas: Atlas, right: str, jurisdiction: str, dates: dict[str, dt.date],
                     *, count: int = 3, as_of: dt.date | None = None) -> TermResult:
    """Convenience wrapper: term plus `count` renewal windows."""
    return term_expiry(atlas, right, jurisdiction, dates, renewals=count, as_of=as_of)


# -- copyright -------------------------------------------------------------------------


@dataclass
class CopyrightTerm:
    jurisdiction: str
    category: str
    expiry: dt.date
    cite: Cite | None = None
    verified: bool = False
    trace: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def render(self) -> str:
        return "\n".join([*self.trace, *(f"WARNING: {w}" for w in self.warnings)])


def copyright_term(atlas: Atlas, jurisdiction: str, category: str,
                   dates: dict[str, dt.date], *, calendar_year_end: bool | None = None,
                   as_of: dt.date | None = None) -> CopyrightTerm:
    """Apply a copyright term expression.

    Expressions take the form {base, plus_years} with an optional {alt, rule} pair for
    "whichever is earlier/later" (US works made for hire, anonymous works).
    """
    pack = atlas[jurisdiction]
    path = f"copyright.term.{category}"
    fact = pack.try_get(path, as_of=as_of)
    if fact is None or not isinstance(fact.value, dict):
        available = [p.rsplit(".", 1)[-1] for p in pack.attributes("copyright.term.")]
        raise NotRecordedError(
            f"{jurisdiction}: {path} is not recorded. Categories recorded: "
            f"{', '.join(available) or 'none'}"
        )
    spec = fact.value
    trace = [f"{pack.name} copyright term, category {category!r}",
             f"source: {fact.cite or 'NONE'}"
             + ("" if fact.verified else " [unverified]")]
    warnings = []
    if not fact.verified:
        warnings.append(f"{jurisdiction}:{path} is unverified")

    def limb(sp: dict, which: str) -> dt.date:
        base, plus = sp.get("base"), sp.get("plus_years")
        if base not in BASES or not isinstance(plus, int):
            raise NotRecordedError(f"{jurisdiction}: {path} {which} limb is malformed "
                                   f"(base={base!r}, plus_years={plus!r})")
        if base not in dates:
            raise MissingDateError(
                f"{jurisdiction} {category} term runs from {base}, which you did not supply. "
                f"Supplied: {', '.join(sorted(dates)) or 'nothing'}."
            )
        out = _add_years(dates[base], plus)
        trace.append(f"  {which}: {base.replace('_', ' ')} {dates[base].isoformat()} "
                     f"+ {plus} years = {out.isoformat()}")
        return out

    expiry = limb(spec, "primary")
    alt = spec.get("alt")
    if isinstance(alt, dict):
        alt_date = limb(alt, "alternative")
        rule = spec.get("rule", "earlier")
        expiry = min(expiry, alt_date) if rule == "earlier" else max(expiry, alt_date)
        trace.append(f"  rule: whichever is {rule} -> {expiry.isoformat()}")

    # Several jurisdictions run copyright terms to the end of the calendar year.
    group = pack.try_get("copyright.term", as_of=as_of)
    notes = list(fact.notes) + (list(group.notes) if group else [])
    to_year_end = calendar_year_end
    if to_year_end is None:
        to_year_end = any("31 december" in n.lower() for n in notes)
    if to_year_end:
        expiry = dt.date(expiry.year, 12, 31)
        trace.append(f"  term runs to the end of the calendar year -> {expiry.isoformat()}")
    else:
        trace.append("  note: this engine has NOT applied a calendar-year-end rule. If the "
                     "jurisdiction runs terms to 31 December, pass calendar_year_end=True "
                     "and record it in the pack.")

    trace.append(f"COPYRIGHT EXPIRES: {expiry.isoformat()}")
    for n in notes:
        trace.append(f"note: {n}")
    return CopyrightTerm(jurisdiction=jurisdiction, category=category, expiry=expiry,
                         cite=fact.cite, verified=fact.verified, trace=trace,
                         warnings=warnings)
