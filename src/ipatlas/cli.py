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

    li = sub.add_parser("lint", help="data quality gate; exit 1 on errors")
    li.add_argument("--errors-only", action="store_true")
    li.set_defaults(fn=cmd_lint)

    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
