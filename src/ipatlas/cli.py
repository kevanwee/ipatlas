"""CLI. Thin: parse args, call the library, print. No legal logic here."""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import json
import sys
from pathlib import Path

from .compare import DEFAULT_ATTRIBUTES, brief, compare
from .core import NotRecordedError, PackError, lint_atlas, load_atlas, summarise
from .core.lint import errors
from .deadlines import (
    madrid_refusal_deadline,
    opposition_deadline,
    pct_national_phase,
    priority_deadline,
)
from .lifecycle import copyright_term, renewal_schedule
from .lifecycle.term import MissingDateError
from .offices import CalendarDataMissingError, load_offices, load_treaty_pack
from .routes import routes as route_matrix


def _atlas(a):
    try:
        return load_atlas(a.data)
    except PackError as e:
        print(f"pack error: {e}", file=sys.stderr)
        raise SystemExit(2) from None


def cmd_jurisdictions(a) -> int:
    atlas = _atlas(a)
    for code in atlas.codes:
        p = atlas[code]
        print(f"{code}  {p.name:22} {p.office or '-':8} "
              f"{len(p.facts):4} facts  rights: {', '.join(p.rights)}")
    return 0


def cmd_attributes(a) -> int:
    atlas = _atlas(a)
    if a.right and a.right in DEFAULT_ATTRIBUTES:
        print(f"default comparison set for {a.right}:")
        for attr in DEFAULT_ATTRIBUTES[a.right]:
            print(f"  {attr}")
        print()
    for code in atlas.codes:
        pack = atlas[code]
        paths = pack.attributes(f"{a.right}." if a.right else "")
        print(f"{code}: {len(paths)} recorded")
        if a.verbose:
            for p in paths:
                f = pack.facts[p]
                print(f"  {p:52} {f.render()[:60]}")
    return 0


def cmd_compare(a) -> int:
    atlas = _atlas(a)
    try:
        table = compare(atlas, a.right, a.jurisdictions, a.attribute or None, as_of=a.as_of)
    except NotRecordedError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    if a.format == "json":
        print(json.dumps(table.to_dict(), indent=2, default=str))
    elif a.format == "csv":
        print(table.to_csv())
    else:
        print(table.to_markdown())
    return 0


def cmd_brief(a) -> int:
    atlas = _atlas(a)
    try:
        print(brief(atlas[a.jurisdiction], a.right, as_of=a.as_of))
    except NotRecordedError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    return 0


def cmd_fact(a) -> int:
    atlas = _atlas(a)
    try:
        f = atlas[a.jurisdiction].get(a.path, as_of=a.as_of)
    except NotRecordedError as e:
        print(f"not recorded: {e}", file=sys.stderr)
        return 2
    print(json.dumps(f.to_dict(), indent=2, default=str) if a.format == "json" else
          f"{f.render()}\n  source: {f.cite or 'NONE'}"
          + (f"\n  checked: {f.checked}" if f.checked else "")
          + "".join(f"\n  note: {n}" for n in f.notes))
    return 0


def _offices(a):
    return load_offices(a.offices)


def _emit(result, as_json: bool) -> int:
    if as_json:
        print(json.dumps(result.to_dict(), indent=2, default=str))
    else:
        print(result.render())
    return 0


def cmd_deadline(a) -> int:
    atlas, offices = _atlas(a), _offices(a)
    trigger = a.date
    try:
        if a.kind == "priority":
            r = priority_deadline(atlas, offices, a.right, trigger, target=a.jurisdiction,
                                  treaty=load_treaty_pack("paris"), as_of=a.as_of)
        elif a.kind == "pct":
            r = pct_national_phase(atlas, offices, a.jurisdiction, trigger,
                                   treaty=load_treaty_pack("pct"), as_of=a.as_of)
        elif a.kind == "opposition":
            r = opposition_deadline(atlas, offices, a.right, a.jurisdiction, trigger,
                                    as_of=a.as_of)
        else:  # madrid-refusal
            r = madrid_refusal_deadline(atlas, offices, a.jurisdiction, trigger,
                                        treaty=load_treaty_pack("madrid"), as_of=a.as_of)
    except NotRecordedError as e:
        print(f"not recorded: {e}", file=sys.stderr)
        return 2
    except CalendarDataMissingError as e:
        print(f"cannot compute: {e}", file=sys.stderr)
        return 3
    return _emit(r, a.json)


def cmd_term(a) -> int:
    atlas = _atlas(a)
    dates = {}
    for pair in a.date or []:
        if "=" not in pair:
            print(f"--date expects base=YYYY-MM-DD, got {pair!r}", file=sys.stderr)
            return 2
        k, v = pair.split("=", 1)
        dates[k] = dt.date.fromisoformat(v)
    try:
        r = renewal_schedule(atlas, a.right, a.jurisdiction, dates, count=a.renewals,
                             as_of=a.as_of)
    except MissingDateError as e:
        print(f"missing date: {e}", file=sys.stderr)
        return 2
    except NotRecordedError as e:
        print(f"not recorded: {e}", file=sys.stderr)
        return 2
    return _emit(r, a.json)


def cmd_copyright(a) -> int:
    atlas = _atlas(a)
    dates = {}
    for pair in a.date or []:
        k, v = pair.split("=", 1)
        dates[k] = dt.date.fromisoformat(v)
    try:
        r = copyright_term(atlas, a.jurisdiction, a.category, dates, as_of=a.as_of)
    except (MissingDateError, NotRecordedError) as e:
        print(f"cannot compute: {e}", file=sys.stderr)
        return 2
    print(r.render())
    return 0


def cmd_routes(a) -> int:
    atlas = _atlas(a)
    try:
        m = route_matrix(atlas, a.right, a.jurisdictions, as_of=a.as_of)
    except NotRecordedError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(json.dumps(m.to_dict(), indent=2) if a.json else m.to_markdown())
    return 0


def cmd_offices(a) -> int:
    offices = _offices(a)
    for code in offices.codes:
        o = offices[code]
        years = ", ".join(str(y) for y in sorted(o.years))
        unverified = sum(1 for y in o.years.values() if not y.verified)
        print(f"{code:7} {o.name[:48]:50} jur={o.jurisdiction or '-':4} "
              f"closure years: {years or 'NONE'}"
              + (f" ({unverified} unverified)" if unverified else ""))
    return 0


def cmd_lint(a) -> int:
    atlas = _atlas(a)
    findings = lint_atlas(atlas, as_of=a.as_of)
    for f in findings:
        if a.errors_only and f.severity != "error":
            continue
        print(f)
    print(summarise(findings), file=sys.stderr)
    return 1 if errors(findings) else 0


def _force_utf8_output() -> None:
    """Citations are in the language of the jurisdiction, so output is inherently CJK-bearing.

    A Windows console defaults to a legacy codepage and raises UnicodeEncodeError on the
    first Chinese article reference. Reconfigure rather than degrade the citation.
    """
    for stream in (sys.stdout, sys.stderr):
        # Already wrapped, or not a real stream (pytest's capture, a pipe in some shells).
        with contextlib.suppress(AttributeError, ValueError):
            stream.reconfigure(encoding="utf-8", errors="replace")


def main(argv=None) -> int:
    _force_utf8_output()
    p = argparse.ArgumentParser(
        prog="ipatlas", description="Cross-border intellectual property as structured data.")
    p.add_argument("--data", type=Path, help="jurisdictions directory (default: bundled data/)")
    p.add_argument("--offices", type=Path, help="offices directory (default: bundled data/)")
    # Global, for the commands that emit a single structured result. `compare` and `fact`
    # predate it and take --format, which also accepts json.
    p.add_argument("--json", action="store_true", help="emit JSON instead of a trace")
    p.add_argument("--as-of", type=dt.date.fromisoformat, default=None,
                   help="resolve facts as in force on this date (default: today)")
    sub = p.add_subparsers(dest="cmd", required=True)

    j = sub.add_parser("jurisdictions", help="list loaded packs")
    j.set_defaults(fn=cmd_jurisdictions)

    at = sub.add_parser("attributes", help="list recorded attribute paths")
    at.add_argument("right", nargs="?")
    at.add_argument("-v", "--verbose", action="store_true")
    at.set_defaults(fn=cmd_attributes)

    c = sub.add_parser("compare", help="compare a right across jurisdictions")
    c.add_argument("right")
    c.add_argument("jurisdictions", nargs="+")
    c.add_argument("-a", "--attribute", action="append",
                   help="attribute path (repeatable; default: the comparison set for the right)")
    c.add_argument("--format", choices=["md", "csv", "json"], default="md")
    c.set_defaults(fn=cmd_compare)

    b = sub.add_parser("brief", help="one-page country note for a right")
    b.add_argument("jurisdiction")
    b.add_argument("right")
    b.set_defaults(fn=cmd_brief)

    f = sub.add_parser("fact", help="one fact with its provenance")
    f.add_argument("jurisdiction")
    f.add_argument("path", help="dotted path, e.g. trade_mark.term")
    f.add_argument("--format", choices=["text", "json"], default="text")
    f.set_defaults(fn=cmd_fact)

    dl = sub.add_parser("deadline", help="compute a deadline with a full derivation")
    dl.add_argument("kind", choices=["priority", "pct", "opposition", "madrid-refusal"])
    dl.add_argument("jurisdiction")
    dl.add_argument("date", type=dt.date.fromisoformat, help="trigger date, ISO")
    dl.add_argument("--right", default="trade_mark")
    dl.set_defaults(fn=cmd_deadline)

    tm = sub.add_parser("term", help="registered-right expiry and renewal schedule")
    tm.add_argument("jurisdiction")
    tm.add_argument("right")
    tm.add_argument("--date", action="append", metavar="BASE=YYYY-MM-DD",
                    help="e.g. --date filing_date=2020-03-01 (repeatable)")
    tm.add_argument("--renewals", type=int, default=2)
    tm.set_defaults(fn=cmd_term)

    cp = sub.add_parser("copyright-term", help="apply a copyright term expression")
    cp.add_argument("jurisdiction")
    cp.add_argument("category")
    cp.add_argument("--date", action="append", metavar="BASE=YYYY-MM-DD")
    cp.set_defaults(fn=cmd_copyright)

    rt = sub.add_parser("routes", help="filing-route matrix from treaty membership")
    rt.add_argument("right")
    rt.add_argument("jurisdictions", nargs="+")
    rt.set_defaults(fn=cmd_routes)

    of = sub.add_parser("offices", help="list office packs and their closure-data coverage")
    of.set_defaults(fn=cmd_offices)

    li = sub.add_parser("lint", help="data quality gate; exit 1 on errors")
    li.add_argument("--errors-only", action="store_true")
    li.set_defaults(fn=cmd_lint)

    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
