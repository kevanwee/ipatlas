"""Offices: computation-of-time rules and closure calendars.

Deadlines are computed against the office that receives the act, not the jurisdiction. A
Madrid designation of Singapore is examined by IPOS but the response is filed at WIPO, and
the two have different closure calendars.

Design rule carried over from the deadline engine in `sg-deadline`: the calendar refuses to
answer for a year it has no data for. An engine that silently treats a closure day as a
working day is worse than one that declines.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml

from .core.fact import Cite
from .core.pack import DATA_DIR

OFFICES_DIR = DATA_DIR / "offices"
TREATIES_DIR = DATA_DIR / "treaties"

_WEEKDAYS = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4,
             "saturday": 5, "sunday": 6}


class MonthArithmetic(StrEnum):
    CORRESPONDING_DATE = "corresponding_date"


class CalendarDataMissingError(LookupError):
    """A computation touched a year with no vendored closure data for the office."""


@dataclass(frozen=True)
class Rule:
    """One computation-of-time rule, with the provision it comes from."""

    value: Any
    cite: Cite | None = None
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class ClosureYear:
    year: int
    days: dict[dt.date, str]
    source: str
    checked: dt.date | None
    verified: bool
    notes: tuple[str, ...] = ()
    working_weekends: frozenset[dt.date] = frozenset()


@dataclass
class Office:
    code: str
    name: str
    jurisdiction: str | None
    timezone: str | None
    exclude_first_day: Rule
    roll_non_working_forward: Rule
    month_arithmetic: Rule
    weekend: tuple[int, ...]
    years: dict[int, ClosureYear] = field(default_factory=dict)

    # -- coverage ---------------------------------------------------------------------

    def ensure_year(self, year: int) -> ClosureYear:
        try:
            return self.years[year]
        except KeyError:
            raise CalendarDataMissingError(
                f"{self.code} has no closure data for {year}. Add it to "
                f"data/offices/{self.code}.yaml rather than assuming the office was open."
            ) from None

    def provenance(self, *dates: dt.date) -> list[str]:
        out = []
        for year in sorted({d.year for d in dates}):
            cy = self.ensure_year(year)
            status = "verified" if cy.verified else "UNVERIFIED"
            out.append(f"{self.code} closure data {year}: {status}, source={cy.source}")
            out.extend(f"  caution: {n}" for n in cy.notes)
        return out

    # -- predicates -------------------------------------------------------------------

    def closure_name(self, d: dt.date) -> str | None:
        return self.ensure_year(d.year).days.get(d)

    def is_weekend(self, d: dt.date) -> bool:
        if d in self.ensure_year(d.year).working_weekends:
            return False  # designated a working day to compensate for a holiday block
        return d.weekday() in self.weekend

    def is_open(self, d: dt.date) -> bool:
        self.ensure_year(d.year)
        return not self.is_weekend(d) and self.closure_name(d) is None

    def why_closed(self, d: dt.date) -> str | None:
        """Human-readable reason the office is closed, or None if it is open."""
        self.ensure_year(d.year)
        if self.is_weekend(d):
            return d.strftime("%A")
        name = self.closure_name(d)
        return f"office closed ({name})" if name else None

    # -- arithmetic -------------------------------------------------------------------

    def next_open(self, d: dt.date, *, inclusive: bool = True) -> dt.date:
        cur = d if inclusive else d + dt.timedelta(days=1)
        while not self.is_open(cur):
            cur += dt.timedelta(days=1)
        return cur

    def prev_open(self, d: dt.date, *, inclusive: bool = True) -> dt.date:
        cur = d if inclusive else d - dt.timedelta(days=1)
        while not self.is_open(cur):
            cur -= dt.timedelta(days=1)
        return cur

    def add_open_days(self, d: dt.date, n: int) -> dt.date:
        step = 1 if n >= 0 else -1
        left = abs(n)
        cur = d
        while left:
            cur += dt.timedelta(days=step)
            if self.is_open(cur):
                left -= 1
        return cur


# -- loading ---------------------------------------------------------------------------


def _rule(raw: Any, name: str, office: str) -> Rule:
    if raw is None:
        raise ValueError(f"{office}: computation.{name} is required")
    if not isinstance(raw, dict):
        return Rule(value=raw)
    notes = raw.get("notes") or []
    cite = Cite(str(raw["cite"])) if raw.get("cite") else None
    return Rule(value=raw.get("value"), cite=cite, notes=tuple(notes))


def _date(v: Any) -> dt.date | None:
    if v is None:
        return None
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    return dt.date.fromisoformat(str(v))


def load_office(path: str | Path) -> Office:
    path = Path(path)
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    code = str(raw["office"])
    if path.stem != code:
        raise ValueError(f"{path}: filename must match the office code ({code}.yaml)")
    comp = raw.get("computation") or {}
    weekend = tuple(_WEEKDAYS[w] for w in (comp.get("weekend") or ["saturday", "sunday"]))

    ww_raw = raw.get("working_weekends") or {}
    years: dict[int, ClosureYear] = {}
    for year, block in (raw.get("holidays") or {}).items():
        days = {}
        for entry in block.get("days") or []:
            # Reject unknown keys. An unquoted YAML flow scalar containing a comma is split
            # by the parser, silently truncating the value and inventing a key from the rest
            # ("Martin Luther King, Jr." -> name "Martin Luther King" plus key "Jr."). That
            # corrupted four USPTO closure names before this check existed.
            unknown = set(entry) - {"date", "name", "observance"}
            if unknown:
                raise ValueError(
                    f"{path}: holidays.{year} entry for {entry.get('date')} has unknown "
                    f"key(s) {sorted(unknown)}. This is usually an unquoted name containing "
                    "a comma: quote the value."
                )
            d = _date(entry["date"])
            if d.year != int(year):
                raise ValueError(f"{path}: {d} listed under holidays.{year}")
            if d in days:
                raise ValueError(f"{path}: duplicate closure date {d} in holidays.{year}")
            if d.weekday() >= 5:
                # Harmless for SG/CN, which list a holiday and its observed weekday, but for
                # an office whose observance REPLACES the holiday it signals a mistake.
                pass
            days[d] = str(entry.get("name", "closed"))
        years[int(year)] = ClosureYear(
            year=int(year),
            days=days,
            source=str(block.get("source", "unknown")),
            checked=_date(block.get("checked")),
            verified=bool(block.get("verified", False)),
            notes=tuple(block.get("notes") or []),
            working_weekends=frozenset(_date(x) for x in (ww_raw.get(int(year)) or [])),
        )

    return Office(
        code=code,
        name=str(raw.get("name", code)),
        jurisdiction=raw.get("jurisdiction"),
        timezone=raw.get("timezone"),
        exclude_first_day=_rule(comp.get("exclude_first_day"), "exclude_first_day", code),
        roll_non_working_forward=_rule(comp.get("roll_non_working_forward"),
                                      "roll_non_working_forward", code),
        month_arithmetic=_rule(comp.get("month_arithmetic"), "month_arithmetic", code),
        weekend=weekend,
        years=years,
    )


@dataclass
class Offices:
    offices: dict[str, Office] = field(default_factory=dict)

    def __getitem__(self, code: str) -> Office:
        try:
            return self.offices[code.upper()]
        except KeyError:
            known = ", ".join(sorted(self.offices)) or "none"
            raise LookupError(f"no office pack for {code!r}; loaded: {known}") from None

    def __contains__(self, code: str) -> bool:
        return code.upper() in self.offices

    @property
    def codes(self) -> list[str]:
        return sorted(self.offices)

    def for_jurisdiction(self, code: str) -> Office:
        for o in self.offices.values():
            if o.jurisdiction and o.jurisdiction.upper() == code.upper():
                return o
        raise LookupError(f"no office pack records jurisdiction {code!r}")


def load_offices(directory: str | Path | None = None) -> Offices:
    directory = Path(directory or OFFICES_DIR)
    out = {}
    for p in sorted(directory.glob("*.yaml")):
        office = load_office(p)
        out[office.code] = office
    return Offices(out)


def load_treaty_pack(name: str, directory: str | Path | None = None) -> dict:
    directory = Path(directory or TREATIES_DIR)
    path = directory / f"{name}.yaml"
    if not path.exists():
        raise LookupError(f"no treaty pack {name!r} in {directory}")
    return yaml.safe_load(path.read_text(encoding="utf-8"))
