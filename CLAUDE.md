# CLAUDE.md — ipatlas

Engineering conventions for this repository. They bind AI assistants and humans equally.
Read `PLAN.md` first if you have not.

## What this is

A structured, cited, versioned dataset of intellectual property law across jurisdictions,
with deterministic engines (comparison, term, deadlines, routes, exhaustion, takedown
checks, dockets) on top, exposed as a library, CLI, MCP server and skills.

**The data is the product.** The code exists to make the data useful and to keep it honest.

## Non-negotiables

1. **Every fact carries provenance.** A fact is a value plus `cite` plus `checked` plus
   `verified`. `scripts/lint_data.py` fails on a fact with no cite. Do not add a bypass.
   Do not "fill in the obvious ones later".
2. **`verified: true` requires evidence in the file.** The commit that flips it quotes what
   was checked and the date, in `notes`. A reviewer who cannot see the evidence rejects.
3. **Unverified renders as unverified.** Every output surface (table cell, brief, MCP
   response, docket line) shows the flag and the cite. Storing the flag and hiding it in
   output is the same as not having it.
4. **No model calls in `src/`.** Engines are pure functions over loaded data. If a feature
   needs judgement, it is a skill, and the skill's `SKILL.md` says what the assistant may
   not do.
5. **Never approximate.** Missing jurisdiction, missing attribute, missing office holiday
   file, unsupported term base: the answer is an explicit "not recorded" / "cannot compute"
   with a reason. There is no default value for a legal fact.
6. **Temporal validity is real.** Facts have `in_force_from`; superseded facts move to the
   file's `history` block with `superseded_by`; every query has an `as_of`. Never overwrite
   a fact when the law changes. Never delete history.
7. **One jurisdiction, one file.** `data/jurisdictions/<CC>.yaml` is the unit of ownership
   and review. A pack PR touches one pack plus its golden tests. Engine PRs touch no packs.
8. **No fees, ever.** Official fee amounts are out of scope. A user-supplied fee table may
   be joined by the caller; the repo does not ship one.
9. **Deadlines are computed against the office, not the country.** Office packs carry
   computation-of-time rules and holiday calendars. An act at WIPO under Madrid is a WIPO
   deadline even when the designated country is Singapore.

## Layout

```
data/jurisdictions/<CC>.yaml   the asset; see SG.yaml as the reference shape
data/treaties/*.yaml           membership, PCT, Madrid, Hague
data/offices/<OFFICE>.yaml     computation-of-time rules + holidays per office
data/schema/*.schema.json      generated: `ipatlas schema`
src/ipatlas/core/              models, loader (short-form expansion, temporal resolve), lint
src/ipatlas/<module>/          one module per engine; see PLAN.md §8
src/ipatlas/cli.py             argparse; no logic
src/ipatlas/server.py          MCP; no logic
skills/<name>/SKILL.md         orchestration only
tests/golden/<CC>/             hand-computed cases per jurisdiction
scripts/                       human-run maintenance (lint, refresh)
```

Front-ends contain no logic. Modules do not import each other except through `core`
(`deadlines` may use `core.calendar`; `portfolio` may call `lifecycle` and `deadlines`).

## Data conventions

- **Jurisdiction codes**: ISO 3166-1 alpha-2, upper-case. Supranational: `EU` (EUIPO/EPO
  plus directives) with `member_state_notes`; regional offices get office packs (`EPO`,
  `EUIPO`, `ARIPO`, `OAPI`, `EAPO`), not jurisdiction packs.
- **Citations** use the form a practitioner in that jurisdiction would write:
  `Trade Marks Act 1998, s 22(1)(a)` · `15 U.S.C. § 1064(3)` · `EUTMR Art 58(1)(a)` ·
  `商标法 第49条 (Trademark Law, Art 49)`. Include a URL in `url` when the official
  consolidated text is online (SSO, USC via LII/govinfo, EUR-Lex, NPC).
- **Dates** ISO 8601. `checked` is the date a human compared the fact to the source.
- **Term bases** are the closed set in PLAN.md §7.4. Extending the set is an engine change
  with a test, not a pack change.
- **Enumerations** are closed (`filing_system: first_to_file | first_to_use`,
  `exhaustion: national | regional | international | unsettled`). `unsettled` is a legitimate
  value and must carry a note. Do not invent a new enum member in a pack; propose it in an
  engine PR.
- **Absence is explicit.** A right the jurisdiction does not have (utility models in SG) is
  `utility_model: { available: false, cite: ... }`, not an omitted key. An attribute not yet
  researched is omitted and renders as "not recorded".
- **Short form** (`term: { years: 10, from: filing_date, cite: "..." }`) is expanded by the
  loader into the full `Fact`; file-level `defaults` supply `checked` / `verified`. Packs
  should use short form; it keeps them readable.
- **History** lives in the same file under `history:` keyed by the fact path, so a reviewer
  diffing a pack sees the old and new rule together.

## Engine conventions

- Every engine returns a `Result` with `trace: list[str]` and `citations: list[Cite]`.
  The trace is the product. Add lines freely; never remove them.
- Engines take `as_of: date` and pass it to the loader. No engine reads a fact without a
  date context.
- Calendar arithmetic follows the `sg-deadline` design: exclusive first day, office
  short-period rule if the office pack declares one, roll per office rule, refuse on
  missing holiday year. Do not reinvent; port.
- Decision tables (`exhaustion`, `transfer`) are data (`rows: [{when: {...}, then: {...},
  cite}]`) evaluated by a small matcher. The matcher is tested; the rows are reviewed by a
  lawyer.

## Testing discipline

- Every pack has `tests/golden/<CC>/` with hand-derived expectations: at least one term
  computation, one deadline, one comparison cell, one exhaustion row. The derivation is a
  comment beside the assertion.
- `lint_data.py` runs in CI: schema, cite presence, `checked` presence, staleness (warn >
  12 months, error > 24), enum validity, history integrity.
- Golden notice fixtures for `takedown`: one valid and one invalid notice per regime, with
  the expected findings.
- `python -m pytest`, `ruff check`, and `python scripts/lint_data.py` before every commit.

## Style

- Python 3.11+, type hints, `from __future__ import annotations`; pydantic v2 for data,
  dataclasses for results; line length 100; ruff `E,F,I,B,UP,N,SIM`.
- YAML: two-space indent; flow style for short facts, block style for anything with notes;
  one blank line between rights; comments explain *why a value is what it is* when
  non-obvious (e.g. "Singapore moved to life+70 in 2004 under the US-Singapore FTA").
- Comments in Python explain the legal rule or the convention adopted, not the code.

## Skill conventions

Each `SKILL.md` has a **Rules** section that includes, verbatim or in substance:

- Answer only from tool results. If the tool says "not recorded", say "not recorded".
- Repeat citations and verification flags. Do not summarise them away.
- Never draft, send, file, or record anything on the user's behalf without confirmation.
- Never fill a gap in the data from memory, even when confident. Propose a pack PR instead.

## Commit hygiene

- Imperative subject, scoped by pack or module: `pack(SG): record TM non-use period`,
  `deadlines: add PCT Rule 80.5 roll`, `lint: error on stale facts > 24 months`.
- One pack per commit. Engine changes and pack changes never share a commit.
- No AI attribution lines or co-author trailers.

## What not to build here

- Fee tables or cost estimates.
- Case-law or statute retrieval; a search box. Use the retrieval MCPs that exist.
- Prior-art / clearance / freedom-to-operate anything.
- Platform-policy rules (marketplace programmes); statutory regimes only.
- A web UI before the MCP and CLI are complete and the data is trusted.
- Any feature whose correctness depends on the model rather than the data.
