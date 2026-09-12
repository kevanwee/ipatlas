#!/usr/bin/env python3
"""CI entry point for the data quality gate.

    python scripts/lint_data.py [--as-of YYYY-MM-DD] [--max-warnings N]

Exits non-zero on any error finding, so a pack that breaks the rules in CLAUDE.md cannot
merge. Warnings are printed and, by default, tolerated: they mark open research gaps
(`--max-warnings` tightens that once a pack is meant to be complete).
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from ipatlas.core import lint_atlas, load_atlas, summarise  # noqa: E402
from ipatlas.core.lint import errors  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--as-of", type=dt.date.fromisoformat, default=dt.date.today())
    ap.add_argument("--max-warnings", type=int, default=None,
                   help="fail if warnings exceed this count")
    ap.add_argument("--data", type=Path, default=None)
    args = ap.parse_args()

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    findings = lint_atlas(load_atlas(args.data), as_of=args.as_of)
    for f in findings:
        print(f)
    print(summarise(findings))

    n_err = len(errors(findings))
    n_warn = len(findings) - n_err
    if n_err:
        print(f"FAIL: {n_err} error(s). See CLAUDE.md 'Non-negotiables'.", file=sys.stderr)
        return 1
    if args.max_warnings is not None and n_warn > args.max_warnings:
        print(f"FAIL: {n_warn} warning(s) exceeds --max-warnings {args.max_warnings}.",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
