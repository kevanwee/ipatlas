"""The deadline engine.

Pure functions. No I/O. Every step is recorded in `Deadline.trace`, which is the product:
a lawyer does not trust a date, they trust a derivation they can check against the rule.

Two layers:
  `_compute`          months/days arithmetic + office roll, with a trace
  the named helpers   find the period in the packs, then call `_compute`

The named helpers are where the legal knowledge lives about WHICH period applies and WHICH
office's calendar governs, and they say so in the trace.
"""

from __future__ import annotations

import calendar as _calmod
import datetime as dt
from dataclasses import dataclass, field

from ..core import Atlas, Cite, NotRecordedError
from ..offices import Office, Offices


@dataclass
class PeriodSource:
    """Where a period came from, so the answer can be checked."""

    months: int | None = None
    days: int | None = None
    cite: Cite | None = None
    origin: str = ""  # "pack SG:trade_mark.priority" / "treaty paris:trade_mark"
    verified: bool = False

    def describe(self) -> str:
        unit = f"{self.months} months" if self.months else f"{self.days} days"
        flag = "" if self.verified else " [unverified]"
        return f"{unit} ({self.origin}: {self.cite or 'no citation'}){flag}"


@dataclass
class Deadline:
    label: str
    trigger: dt.date
    date: dt.date
    office: str
    source: PeriodSource
    trace: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def days_remaining_from(self) -> dt.date:
        return self.date

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "trigger": self.trigger.isoformat(),
            "deadline": self.date.isoformat(),
            "weekday": self.date.strftime("%A"),
            "office": self.office,
            "period": self.source.describe(),
            "cite": self.source.cite.text if self.source.cite else None,
            "verified": self.source.verified,
            "trace": list(self.trace),
            "warnings": list(self.warnings),
        }

    def render(self) -> str:
        lines = [*self.trace]
        for w in self.warnings:
            lines.append(f"WARNING: {w}")
        return "\n".join(lines)


def _fmt(d: dt.date) -> str:
    return f"{d.isoformat()} ({d.strftime('%a')})"


def _add_months(d: dt.date, months: int) -> tuple[dt.date, bool]:
    """Corresponding-date arithmetic. Returns (date, clamped_to_month_end)."""
    total = d.month - 1 + months
    year = d.year + total // 12
    month = total % 12 + 1
    last = _calmod.monthrange(year, month)[1]
    if d.day > last:
        return dt.date(year, month, last), True
    return dt.date(year, month, d.day), False


def _compute(label: str, trigger: dt.date, source: PeriodSource, office: Office) -> Deadline:
    """Apply a period to a trigger date under an office's computation rules."""
    trace = [
        f"{label}",
        f"period: {source.describe()}",
        f"trigger: {_fmt(trigger)}",
        f"office: {office.code} ({office.name})",
    ]
    warnings: list[str] = []
    if not source.verified:
        warnings.append(
            f"the period was read from {source.origin}, which is marked unverified; "
            "check it against the cited provision before relying on this date"
        )

    if source.months:
        raw, clamped = _add_months(trigger, source.months)
        rule = office.month_arithmetic
        trace.append(f"month arithmetic ({rule.value}"
                     + (f", {rule.cite}" if rule.cite else "") + "): "
                     f"{_fmt(trigger)} + {source.months} months = {_fmt(raw)}")
        if clamped:
            trace.append("  no corresponding date in the target month; used its last day")
    else:
        days = source.days or 0
        raw = trigger + dt.timedelta(days=days)
        excl = office.exclude_first_day
        trace.append("day count (first day excluded"
                     + (f", {excl.cite}" if excl.cite else "") + "): "
                     f"{_fmt(trigger)} + {days} days = {_fmt(raw)}")

    deadline = raw
    closed = office.why_closed(raw)
    roll = office.roll_non_working_forward
    if closed and roll.value:
        deadline = office.next_open(raw)
        trace.append(f"{_fmt(raw)}: {closed}. Rolled forward to the next day the office is "
                     f"open, {_fmt(deadline)}"
                     + (f" ({roll.cite})" if roll.cite else ""))
    elif closed:
        trace.append(f"{_fmt(raw)}: {closed}. This office's rules do not extend the period; "
                     "date unchanged")
    else:
        trace.append(f"{_fmt(raw)}: office open; no extension needed")

    trace.append(f"DEADLINE: {_fmt(deadline)}")
    # Provenance covers only the years actually consulted. The computation tests whether the
    # office is open on and after the raw expiry date, never on the trigger date, so
    # requiring closure data for the trigger year would refuse valid historical questions.
    trace.extend(office.provenance(raw, deadline))
    return Deadline(label=label, trigger=trigger, date=deadline, office=office.code,
                    source=source, trace=trace, warnings=warnings)


# -- finding the period ----------------------------------------------------------------


def _from_pack(atlas: Atlas, jurisdiction: str, path: str, key: str,
               as_of: dt.date | None = None) -> PeriodSource | None:
    """Read a period out of a jurisdiction pack fact, e.g. trade_mark.priority -> months."""
    fact = atlas[jurisdiction].try_get(path, as_of=as_of)
    if fact is None or not isinstance(fact.value, dict):
        return None
    value = fact.value.get(key)
    if not isinstance(value, int):
        return None
    unit = "months" if key.endswith("months") or key == "months" else "days"
    return PeriodSource(
        months=value if unit == "months" else None,
        days=value if unit == "days" else None,
        cite=fact.cite,
        origin=f"pack {jurisdiction}:{path}",
        verified=fact.verified,
    )


def _from_treaty(pack: dict, path: list[str], key: str, origin: str) -> PeriodSource | None:
    node = pack
    for step in path:
        node = (node or {}).get(step) if isinstance(node, dict) else None
    if not isinstance(node, dict):
        return None
    value = node.get(key)
    if not isinstance(value, int):
        return None
    unit = "months" if key.endswith("months") or key == "months" else "days"
    return PeriodSource(
        months=value if unit == "months" else None,
        days=value if unit == "days" else None,
        cite=Cite(str(node["cite"])) if node.get("cite") else None,
        origin=origin,
        verified=bool(pack.get("verified", False)),
    )


# -- public API ------------------------------------------------------------------------


def deadline_from_fact(atlas: Atlas, offices: Offices, jurisdiction: str, path: str,
                       key: str, trigger: dt.date, *, label: str | None = None,
                       office: str | None = None,
                       as_of: dt.date | None = None) -> Deadline:
    """Generic: apply a period recorded in a pack fact to a trigger date."""
    source = _from_pack(atlas, jurisdiction, path, key, as_of)
    if source is None:
        raise NotRecordedError(
            f"{jurisdiction}: {path}.{key} is not recorded as an integer period, so no "
            "deadline can be computed. Record it in the pack rather than assuming a default."
        )
    o = offices[office] if office else offices.for_jurisdiction(jurisdiction)
    return _compute(label or f"{jurisdiction} {path}.{key}", trigger, source, o)


def priority_deadline(atlas: Atlas, offices: Offices, right: str, first_filing: dt.date,
                      *, target: str | None = None, treaty: dict | None = None,
                      as_of: dt.date | None = None) -> Deadline:
    """Paris Convention priority window. Runs against the office where priority is claimed.

    With `target`, the target jurisdiction's own implementing provision is preferred, because
    that is what a local practitioner cites and what the local office applies.
    """
    source = None
    if target:
        source = _from_pack(atlas, target, f"{right}.priority", "months", as_of)
    if source is None and treaty:
        source = _from_treaty(treaty, ["priority_windows", right], "months",
                              "treaty paris")
    if source is None:
        raise NotRecordedError(
            f"no priority period recorded for {right}"
            + (f" in {target}" if target else "")
            + "; record it in the pack or pass the Paris treaty pack"
        )
    o = offices.for_jurisdiction(target) if target else offices["WIPO"]
    label = (f"Paris priority deadline for {right.replace('_', ' ')}"
             + (f" filing in {target}" if target else ""))
    d = _compute(label, first_filing, source, o)
    d.trace.insert(1, "the day of first filing is excluded from the priority period "
                      "(Paris Convention, Art 4C(2))")
    return d


def pct_national_phase(atlas: Atlas, offices: Offices, jurisdiction: str,
                       priority_date: dt.date, *, treaty: dict | None = None,
                       as_of: dt.date | None = None) -> Deadline:
    """PCT national/regional phase entry. The designated Office's own period governs where
    it records one longer than the Treaty's 30 months."""
    pack_source = _from_pack(atlas, jurisdiction, "patent.pct", "national_phase_months", as_of)
    treaty_source = (_from_treaty(treaty, ["timeline", "national_phase_chapter_i"], "months",
                                  "treaty pct") if treaty else None)
    source = pack_source or treaty_source
    if source is None:
        raise NotRecordedError(
            f"{jurisdiction}: patent.pct.national_phase_months is not recorded and no PCT "
            "treaty pack was supplied"
        )
    o = offices.for_jurisdiction(jurisdiction)
    d = _compute(f"PCT national phase entry in {jurisdiction}", priority_date, source, o)
    if pack_source and treaty_source and pack_source.months != treaty_source.months:
        d.trace.insert(2, f"the designated Office allows {pack_source.months} months, longer "
                          f"than the Treaty default of {treaty_source.months} "
                          f"({treaty_source.cite}); the Office's period governs")
    return d


def opposition_deadline(atlas: Atlas, offices: Offices, right: str, jurisdiction: str,
                        publication: dt.date, *, as_of: dt.date | None = None) -> Deadline:
    """Opposition window from publication. Handles packs recording days rather than months."""
    path = f"{right}.opposition"
    source = (_from_pack(atlas, jurisdiction, path, "window_months", as_of)
              or _from_pack(atlas, jurisdiction, path, "window_days", as_of))
    if source is None:
        raise NotRecordedError(f"{jurisdiction}: {path} records no window_months/window_days")
    o = offices.for_jurisdiction(jurisdiction)
    d = _compute(f"{jurisdiction} opposition deadline ({right.replace('_', ' ')})",
                 publication, source, o)
    fact = atlas[jurisdiction].try_get(path, as_of=as_of)
    if fact and isinstance(fact.value, dict):
        v = fact.value
        if v.get("extendable") is True:
            # Periods are recorded in whichever unit the rule uses, so read both.
            ext = (f"{v['max_extension_months']} months" if "max_extension_months" in v
                   else f"{v['max_extension_days']} days" if "max_extension_days" in v
                   else None)
            d.trace.append("this window is extendable"
                           + (f" by up to {ext}" if ext else "")
                           + "; the date above is the UNEXTENDED deadline")
            # The total cap is the absolute deadline and is what a diary needs, so compute it.
            total = next(((k, v[k]) for k in ("max_total_months_from_publication",
                                             "max_total_days_from_publication") if k in v), None)
            if total is not None:
                key, amount = total
                # The unit is in the MIDDLE of the key name (max_total_months_from_...),
                # so test for containment; `endswith` silently read months as days.
                months = amount if "months" in key else None
                cap = PeriodSource(months=months, days=None if months else amount,
                                   cite=fact.cite, origin=f"pack {jurisdiction}:{path}",
                                   verified=fact.verified)
                outer = _compute(f"{jurisdiction} opposition ABSOLUTE deadline with every "
                                 "extension granted", publication, cap, o)
                d.trace.append(f"ABSOLUTE deadline if every extension is granted: "
                               f"{_fmt(outer.date)} ({amount} "
                               f"{'months' if months else 'days'} from publication)")
                d.trace.append("  the total cap runs from PUBLICATION, not from the end of "
                               "the first window; do not add the extension to the date above")
        elif v.get("extendable") is False:
            d.trace.append("this window is NOT extendable")
    return d


def madrid_refusal_deadline(atlas: Atlas, offices: Offices, jurisdiction: str,
                            notification: dt.date, *, treaty: dict | None = None,
                            as_of: dt.date | None = None) -> Deadline:
    """Outer date for a designated Contracting Party to notify a provisional refusal."""
    source = _from_pack(atlas, jurisdiction, "trade_mark.madrid",
                        "refusal_window_months", as_of)
    if source is None and treaty:
        source = _from_treaty(treaty, ["refusal_windows", "default"], "months", "treaty madrid")
    if source is None:
        raise NotRecordedError(
            f"{jurisdiction}: trade_mark.madrid.refusal_window_months is not recorded"
        )
    # The refusal is notified BY the designated Office, so its own calendar governs.
    o = offices.for_jurisdiction(jurisdiction)
    d = _compute(f"Madrid refusal window for the {jurisdiction} designation",
                 notification, source, o)
    if treaty and "opposition_based_later_refusal" in (treaty.get("refusal_windows") or {}):
        note = treaty["refusal_windows"]["opposition_based_later_refusal"]
        d.trace.append("caution: where the Contracting Party has so declared, a refusal "
                       "based on an opposition may be notified AFTER this date "
                       f"({note.get('cite', 'Madrid Protocol, Art 5(2)(c)')}); this engine "
                       "does not compute that outer date")
    return d
