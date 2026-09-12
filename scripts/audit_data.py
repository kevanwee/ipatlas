"""Internal-consistency audit of the ipatlas data that does not need an external source.

Three classes of check:
  A. US federal holidays are defined by deterministic rules (5 U.S.C. s 6103) plus in-lieu
     observance (E.O. 11582), so the USPTO list can be derived and compared.
  B. Claims made in prose inside the packs ("observed, 4 July falls on a Saturday") are
     checkable against the calendar.
  C. Structural invariants: observed days must be working days, holiday dates must be unique,
     history periods must abut, every cite-bearing fact must parse.
"""
from __future__ import annotations

import calendar
import datetime as dt
import re
import sys
from pathlib import Path

import yaml

ROOT = Path("data")
problems: list[str] = []
notes: list[str] = []


def fail(msg):
    problems.append(msg)


def note(msg):
    notes.append(msg)


# ---------------------------------------------------------------- A. US federal holidays

def nth_weekday(year, month, weekday, n):
    """n-th weekday of a month (n=1 first). weekday: Monday=0."""
    c = calendar.Calendar()
    days = [d for d in c.itermonthdates(year, month)
            if d.month == month and d.weekday() == weekday]
    return days[n - 1]


def last_weekday(year, month, weekday):
    c = calendar.Calendar()
    days = [d for d in c.itermonthdates(year, month)
            if d.month == month and d.weekday() == weekday]
    return days[-1]


def observed(d: dt.date) -> dt.date:
    """E.O. 11582 in-lieu: Saturday -> preceding Friday, Sunday -> following Monday."""
    if d.weekday() == 5:
        return d - dt.timedelta(days=1)
    if d.weekday() == 6:
        return d + dt.timedelta(days=1)
    return d


MON = 0
THU = 3


def us_federal(year: int) -> dict[dt.date, str]:
    fixed = {
        dt.date(year, 1, 1): "New Year's Day",
        dt.date(year, 6, 19): "Juneteenth National Independence Day",
        dt.date(year, 7, 4): "Independence Day",
        dt.date(year, 11, 11): "Veterans Day",
        dt.date(year, 12, 25): "Christmas Day",
    }
    out = {observed(d): n for d, n in fixed.items()}
    out[nth_weekday(year, 1, MON, 3)] = "Birthday of Martin Luther King, Jr."
    out[nth_weekday(year, 2, MON, 3)] = "Washington's Birthday"
    out[last_weekday(year, 5, MON)] = "Memorial Day"
    out[nth_weekday(year, 9, MON, 1)] = "Labor Day"
    out[nth_weekday(year, 10, MON, 2)] = "Columbus Day"
    out[nth_weekday(year, 11, THU, 4)] = "Thanksgiving Day"
    return out


# ------------------------------------------------------------------------ load the packs

def load(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def as_date(v) -> dt.date:
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    return dt.date.fromisoformat(str(v))


offices = {p.stem: load(p) for p in sorted((ROOT / "offices").glob("*.yaml"))}
jurisdictions = {p.stem: load(p) for p in sorted((ROOT / "jurisdictions").glob("*.yaml"))}

print("=" * 78)
print("A. USPTO vs the statutory federal-holiday rules")
print("=" * 78)
uspto = offices["USPTO"]["holidays"]
for year, block in sorted(uspto.items()):
    year = int(year)
    recorded = {as_date(e["date"]): e.get("name", "") for e in block["days"]}
    expected = us_federal(year)
    missing = sorted(set(expected) - set(recorded))
    extra = sorted(set(recorded) - set(expected))
    print(f"\n{year}: {len(recorded)} recorded, {len(expected)} derived from the rules")
    for d in missing:
        fail(f"USPTO {year}: MISSING {d} ({d:%a}) {expected[d]}")
    for d in extra:
        fail(f"USPTO {year}: EXTRA {d} ({d:%a}) {recorded[d]!r} is not a federal holiday")
    if not missing and not extra:
        print("  every date matches the statutory rules")
    # Every federal holiday observance must itself be a working day.
    for d in recorded:
        if d.weekday() >= 5:
            fail(f"USPTO {year}: {d} ({d:%a}) is a weekend; an observance cannot fall there")

print()
print("=" * 78)
print("B. Prose claims about weekdays, checked against the calendar")
print("=" * 78)
# e.g. "(observed, 4 July falls on a Saturday)" or "Vesak Day (observed)"
claim = re.compile(
    r"(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|"
    r"November|December)\s+falls on a\s+(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)",
    re.I)
MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], start=1)}
checked = 0
for code, pack in offices.items():
    for year, block in (pack.get("holidays") or {}).items():
        for e in block.get("days") or []:
            for m in claim.finditer(str(e.get("name", ""))):
                day, month_name, weekday_name = m.group(1), m.group(2), m.group(3)
                d = dt.date(int(year), MONTHS[month_name.lower()], int(day))
                actual = d.strftime("%A")
                checked += 1
                if actual.lower() != weekday_name.lower():
                    fail(f"{code} {year}: claims {day} {month_name} falls on a "
                         f"{weekday_name}, but {d} is a {actual}")
print(f"checked {checked} weekday claims in office packs")

# "observed" entries must sit next to the actual holiday they stand in for.
for code, pack in offices.items():
    for year, block in (pack.get("holidays") or {}).items():
        days = {as_date(e["date"]): str(e.get("name", "")) for e in block.get("days") or []}
        for d, name in days.items():
            if "observed" not in name.lower():
                continue
            base = name.lower().split("(observed")[0].strip()
            neighbours = [x for x in days
                          if x != d and abs((x - d).days) <= 3
                          and days[x].lower().startswith(base[:12])]
            # Two legitimate conventions. SG and CN list the holiday AND the observed weekday
            # (both are closure days). The USPTO lists only the observance, which REPLACES the
            # holiday. So an absent base entry is not an error; a base entry that is itself a
            # weekday is, because a weekday needs no observance.
            for actual in neighbours:
                if actual.weekday() < 5:
                    fail(f"{code} {year}: {d} is recorded as observed for {actual}, but "
                         f"{actual} ({actual:%a}) is a weekday and needs no observance")

print()
print("=" * 78)
print("D. Computable movable feasts")
print("=" * 78)
# Many European office closures are Easter-derived and therefore deterministic, as is
# Geneva's Jeune genevois. Verifying them removes a whole class of error from closure lists
# that are otherwise reconstructions. It does NOT prove the office actually closes that day,
# only that the date given for the named feast is arithmetically right.


def easter(year: int) -> dt.date:
    """Anonymous Gregorian computus."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    ll = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ll) // 451
    month, day = divmod(h + ll - 7 * m + 114, 31)
    return dt.date(year, month, day + 1)


def jeune_genevois(year: int) -> dt.date:
    """Thursday following the first Sunday in September (Geneva)."""
    d = dt.date(year, 9, 1)
    while d.weekday() != 6:  # first Sunday
        d += dt.timedelta(days=1)
    return d + dt.timedelta(days=4)


EASTER_OFFSETS = {
    "good friday": -2, "easter monday": 1, "ascension": 39,
    "whit monday": 50, "pentecost monday": 50, "corpus christi": 60,
}
movable = 0
for code, pack in offices.items():
    for year, block in (pack.get("holidays") or {}).items():
        year = int(year)
        e = easter(year)
        for entry in block.get("days") or []:
            name = str(entry.get("name", "")).lower()
            d = as_date(entry["date"])
            for key, offset in EASTER_OFFSETS.items():
                if key in name:
                    expected = e + dt.timedelta(days=offset)
                    movable += 1
                    if d != expected:
                        fail(f"{code} {year}: {name!r} recorded {d}, but Easter {year} is "
                             f"{e} so it falls on {expected}")
                    break
            if "jeune genevois" in name or "jeûne genevois" in name:
                expected = jeune_genevois(year)
                movable += 1
                if d != expected:
                    fail(f"{code} {year}: Jeune genevois recorded {d}, computed {expected}")
print(f"checked {movable} movable-feast dates against the computus")

print()
print("=" * 78)
print("C. Structural invariants")
print("=" * 78)

for code, pack in offices.items():
    for year, block in (pack.get("holidays") or {}).items():
        dates = [as_date(e["date"]) for e in block.get("days") or []]
        dupes = {d for d in dates if dates.count(d) > 1}
        for d in dupes:
            fail(f"{code} {year}: duplicate closure date {d}")
        for d in dates:
            if d.year != int(year):
                fail(f"{code} {year}: {d} is listed under the wrong year")
    ww = pack.get("working_weekends") or {}
    for year, lst in ww.items():
        for v in lst or []:
            d = as_date(v)
            if d.weekday() < 5:
                fail(f"{code} {year}: working_weekends lists {d} ({d:%a}), a weekday")

# History periods must not overlap and must abut the current fact.
for code, pack in jurisdictions.items():
    hist = pack.get("history") or {}
    for path, versions in hist.items():
        spans = []
        for v in versions:
            if "in_force_from" not in v or "in_force_until" not in v:
                fail(f"{code}: history.{path} entry lacks a validity bound")
                continue
            spans.append((as_date(v["in_force_from"]), as_date(v["in_force_until"])))
        spans.sort()
        for (a1, a2), (b1, _) in zip(spans, spans[1:]):
            if a2 >= b1:
                fail(f"{code}: history.{path} periods overlap ({a2} >= {b1})")
        # Find the current fact's in_force_from by walking the dotted path.
        node = pack
        for step in path.split("."):
            node = (node or {}).get(step) if isinstance(node, dict) else None
        if isinstance(node, dict) and "in_force_from" in node and spans:
            cur = as_date(node["in_force_from"])
            last_end = spans[-1][1]
            gap = (cur - last_end).days
            if gap != 1:
                fail(f"{code}: history.{path} ends {last_end} but the current fact starts "
                     f"{cur} - a {gap}-day gap leaves dates in that window unresolvable")

# Every `verified: true` fact must carry a cite and a note (mirrors the linter, belt and braces).
def walk(node, prefix, code):
    if not isinstance(node, dict):
        return
    if node.get("verified") is True:
        if not node.get("cite"):
            fail(f"{code}:{prefix} verified with no cite")
        if not node.get("notes"):
            fail(f"{code}:{prefix} verified with no evidence note")
    for k, v in node.items():
        if k in ("notes", "value", "cite", "url", "checked", "verified"):
            continue
        walk(v, f"{prefix}.{k}" if prefix else k, code)


for code, pack in jurisdictions.items():
    walk(pack, "", code)

print()
print("=" * 78)
if problems:
    print(f"{len(problems)} PROBLEM(S)")
    for x in problems:
        print("  [X]", x)
else:
    print("no problems found in checks A-C")
if notes:
    print(f"\n{len(notes)} note(s) to look at")
    for x in notes:
        print("  [?]", x)
sys.exit(1 if problems else 0)
