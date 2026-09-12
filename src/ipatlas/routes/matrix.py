"""Which filing routes reach which targets.

Built from the `memberships` fact in each jurisdiction pack plus the right-specific
acceptance flags (`trade_mark.madrid.designation_accepted`,
`registered_design.hague.designation_accepted`). Where a pack does not record membership the
answer is "not recorded", never "assume national only".

This module reports routes and the traps the packs record. It does not recommend a route:
that depends on cost, timing and commercial factors the dataset deliberately excludes.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from ..core import Atlas, NotRecordedError

# Which treaty gives a centralised route for which right.
ROUTE_TREATIES: dict[str, list[tuple[str, str]]] = {
    "patent": [("pct", "PCT international application")],
    "utility_model": [("pct", "PCT international application")],
    "trade_mark": [("madrid", "Madrid international registration")],
    "registered_design": [("hague", "Hague international registration")],
}

# Paris gives a priority route for every industrial-property right, not a filing route.
PRIORITY_TREATY = "paris"


@dataclass
class TargetRoutes:
    jurisdiction: str
    name: str
    right_available: bool
    treaty_routes: list[str] = field(default_factory=list)
    national_only: bool = False
    priority_available: bool = False
    traps: list[str] = field(default_factory=list)
    not_recorded: list[str] = field(default_factory=list)

    @property
    def summary(self) -> str:
        if not self.right_available:
            return "right not available"
        if self.treaty_routes:
            return ", ".join(self.treaty_routes) + ", or national filing"
        return "national filing only"


@dataclass
class RouteMatrix:
    right: str
    targets: list[TargetRoutes]
    as_of: dt.date

    def to_markdown(self) -> str:
        out = [f"# Filing routes — {self.right.replace('_', ' ')}", "",
               f"As at {self.as_of.isoformat()}.", "",
               "| Target | Route | Paris priority | Notes |", "|---|---|---|---|"]
        for t in self.targets:
            note_count = len(t.traps) + len(t.not_recorded)
            out.append(f"| {t.jurisdiction} ({t.name}) | {t.summary} | "
                       f"{'yes' if t.priority_available else 'not recorded'} | "
                       f"{note_count or ''} |")
        flagged = [t for t in self.targets if t.traps]
        if flagged:
            out += ["", "## Traps", ""]
            for t in flagged:
                out.append(f"**{t.jurisdiction}**")
                out += [f"- {x}" for x in t.traps]
                out.append("")
        gaps = [t for t in self.targets if t.not_recorded]
        if gaps:
            out += ["", "## Not recorded", ""]
            for t in gaps:
                out += [f"- {t.jurisdiction}: {x}" for x in t.not_recorded]
        out += ["", "This matrix reports available routes and recorded traps. It does not "
                    "recommend a route: cost, timing and commercial factors are out of scope.",
                ""]
        return "\n".join(out)

    def to_dict(self) -> dict:
        return {
            "right": self.right,
            "as_of": self.as_of.isoformat(),
            "targets": [
                {"jurisdiction": t.jurisdiction, "name": t.name,
                 "right_available": t.right_available, "treaty_routes": t.treaty_routes,
                 "national_only": t.national_only,
                 "priority_available": t.priority_available,
                 "traps": t.traps, "not_recorded": t.not_recorded}
                for t in self.targets
            ],
        }


def routes(atlas: Atlas, right: str, targets: list[str], *,
           as_of: dt.date | None = None) -> RouteMatrix:
    when = as_of or dt.date.today()
    if right not in ROUTE_TREATIES:
        raise NotRecordedError(
            f"no route treaty mapping for {right!r}; known: {', '.join(ROUTE_TREATIES)}"
        )
    out: list[TargetRoutes] = []
    for code in [t.upper() for t in targets]:
        pack = atlas[code]
        tr = TargetRoutes(jurisdiction=code, name=pack.name,
                          right_available=pack.has_right(right))
        memberships_fact = pack.try_get("memberships", as_of=when)
        memberships = set(memberships_fact.value or []) if memberships_fact else set()
        if memberships_fact is None:
            tr.not_recorded.append("treaty memberships are not recorded, so routes cannot be "
                                   "determined")
            out.append(tr)
            continue
        tr.priority_available = PRIORITY_TREATY in memberships

        if tr.right_available:
            for treaty, label in ROUTE_TREATIES[right]:
                if treaty not in memberships:
                    continue
                # Madrid and Hague need the designation to be accepted for that right.
                if treaty in ("madrid", "hague"):
                    path = f"{right}.{treaty}"
                    accepted, _ = pack.subvalue(path, "designation_accepted", as_of=when)
                    if accepted is None:
                        tr.not_recorded.append(
                            f"member of {treaty} but {path}.designation_accepted is "
                            "not recorded")
                        continue
                    if accepted is False:
                        continue
                tr.treaty_routes.append(label)
            tr.national_only = not tr.treaty_routes
            _collect_traps(pack, right, tr, when)
        out.append(tr)
    return RouteMatrix(right=right, targets=out, as_of=when)


def _collect_traps(pack, right: str, tr: TargetRoutes, when: dt.date) -> None:
    """Surface the route-relevant facts a practitioner would want flagged."""
    # Individual-fee Madrid members change the cost model of the route.
    fee, _ = pack.subvalue(f"{right}.madrid", "individual_fee", as_of=when)
    if fee is True:
        tr.traps.append("charges an individual fee for a Madrid designation, so the route's "
                        "cost advantage is reduced")

    # A use requirement at filing defeats the main convenience of a centralised route.
    fs = pack.try_get(f"{right}.filing_system", as_of=when)
    if fs is not None and fs.value == "first_to_use":
        tr.traps.append("first-to-use jurisdiction: rights turn on use, and an unregistered "
                        "senior user can defeat a registration")

    # Notes on the treaty facts themselves are usually the practitioner warnings.
    for path in (f"{right}.madrid", f"{right}.hague", f"{right}.pct", f"{right}.classification"):
        f = pack.try_get(path, as_of=when)
        if f is not None:
            tr.traps.extend(f.notes)

    # Short non-use periods matter when choosing between defensive and used filings.
    use = pack.try_get(f"{right}.use_requirement", as_of=when)
    if use is not None and isinstance(use.value, dict):
        yrs = use.value.get("non_use_years")
        if isinstance(yrs, int) and yrs <= 3:
            tr.traps.append(f"non-use vulnerability after only {yrs} years")

    # An unsettled exhaustion position affects enforcement planning against parallel imports.
    ex = pack.try_get(f"{right}.exhaustion", as_of=when)
    if ex is not None and ex.value == "unsettled":
        tr.traps.append("exhaustion position is unsettled; parallel-import outcomes are "
                        "fact-dependent")
