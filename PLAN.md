# ipatlas — plan

Cross-border IP as structured data, with deterministic engines on top.

Status: **planning**. Nothing in this folder is built yet. This document is the design;
`CLAUDE.md` is the engineering contract; `data/jurisdictions/SG.yaml` is the schema made
concrete for one jurisdiction.

---

## 1. The problem

Every cross-border IP question decomposes into the same shape:

> For right type *R* in jurisdiction *J*, what is the rule on *X*, what is the date, and
> what is the source?

"Can we still file in Vietnam?" is a Paris priority arithmetic question. "Is the parallel
import from Malaysia infringing in Singapore?" is a lookup in an exhaustion table. "What
does our Chinese trade mark registration actually give us?" is a comparison of ten
attributes against the Singapore one the client already understands. "Is this takedown
notice valid under the DSA?" is a checklist.

Today the answers live in paywalled country guides (INTA, Lexology GTDT, Kluwer), in the
heads of foreign associates, and in docketing systems that cost six figures (Anaqua, CPA
Global, Clarivate). None of it is open, structured, or callable by an assistant. So when an
AI assistant is asked any of these questions it answers from training memory, which is
where the errors come from.

## 2. The thesis

**Put the facts in versioned, cited, per-jurisdiction data files. Put the arithmetic in
deterministic engines. Make the assistant a reader of both, never a source.**

This is the same thesis as `sg-deadline`, scaled to a domain where the number of
jurisdictions is the point. It works because IP law is unusually *tabular*: treaties
harmonise the categories (Paris, TRIPS, Berne, PCT, Madrid, Hague) so the same attributes
exist everywhere and only the values differ. That is exactly the shape a comparator wants.

## 3. Who it is for

| User | What they get |
|---|---|
| In-house counsel with a portfolio in 8 countries | A docket generated from a portfolio file, and a one-page brief per country that is *cited* |
| Platform IP-enforcement team (marketplace, social) | Takedown notice validation per regime; counter-notice clocks; exhaustion answers for parallel-import listings |
| Practitioner advising on foreign filing | Route matrix (Paris / PCT / Madrid / Hague / national) for a target list, with the traps flagged |
| AI assistant (via MCP) | A place to look things up instead of guessing, with a citation to hand back |
| Contributor who knows one jurisdiction | A single YAML file to own |

## 4. Design principles

1. **Data first, engines second, skills last.** The jurisdiction packs are the asset. If
   the code were deleted the YAML would still be worth having.
2. **Provenance on every fact.** A number without a citation and a check date is not a
   fact, it is a rumour. The linter enforces this; unverified facts render with a visible
   flag.
3. **Temporal validity.** Laws change. Facts carry `in_force_from` and optional
   `superseded_by`; queries take an `as_of` date. A question about a 2019 registration is
   answered under 2019 law.
4. **Deterministic engines only.** Term, deadline, route, exhaustion and takedown-check are
   pure functions over data. No model calls in the library. Ever.
5. **Never approximate.** Missing holiday data, missing jurisdiction, missing field: the
   answer is "unknown" with a reason, never a best guess.
6. **One jurisdiction, one file, one owner.** The contribution model is a country pack.
   Contributors should not need to understand the engines to add or correct a fact.
7. **No fees.** Official fees change quarterly and vary by entity size and route; they are
   a maintenance sink that would drag the whole dataset into staleness. Provide a hook for
   a user-supplied fee table and nothing more.

## 5. Scope

### In scope (rights)

trade marks · patents · registered designs · copyright · trade secrets · geographical
indications · plant varieties (later)

### In scope (attributes per right, where applicable)

statute and office · filing system (first-to-file / first-to-use) · examination type
(formal / substantive / absolute-only) · term and renewal, with grace and restoration ·
maintenance fees schedule shape · priority window and treaty · novelty grace period and
scope · opposition window and trigger · use requirement and non-use vulnerability ·
well-known / famous mark protection · exhaustion regime · border measures / customs
recordal · criminal sanctions · specification and classification practice · PCT national
phase month · Madrid refusal window and dependency · Hague refusal window · assignment
and licence formalities and recordal effect · government approvals on transfer ·
platform safe-harbour regime and notice requirements · moral rights · copyright term rule
(including corporate works, anonymous works, rule of the shorter term)

### In scope (jurisdictions, in order)

**Phase 0:** SG, US, EU (EUIPO/EPO/EU directives as a layer, with member-state notes), CN
**Phase 1:** JP, KR, AU, GB
**Phase 2:** MY, ID, TH, VN, PH (the ASEAN slice this project is unusually placed to do well)
**Phase 3:** IN, TW, HK, CA, BR, MX; then by contribution

### Out of scope

Fees. Case-law retrieval (use the existing retrieval MCPs). Prior-art search. Freedom-to-
operate. Tax on royalties. Anything that requires reading a specific document rather than
knowing the rule.

## 6. Architecture

```
ipatlas/
  CLAUDE.md                     engineering contract
  PLAN.md                       this file
  data/
    jurisdictions/<CC>.yaml     one pack per jurisdiction; the asset
    treaties/
      membership.yaml           who is in Paris / PCT / Madrid / Hague / Berne / TRIPS / ...
      pct.yaml                  national-phase months, extensions, per designated office
      madrid.yaml               refusal windows, individual-fee members, dependency, replacement
      hague.yaml                refusal windows, declared members
    offices/<OFFICE>.yaml       computation-of-time rules + holiday packs per office
    schema/*.schema.json        generated from the pydantic models
  src/ipatlas/
    core/      models, loader, provenance, temporal filter, lint
    compare/   attribute comparison across jurisdictions; table + brief rendering
    lifecycle/ term, renewal, maintenance windows; copyright term calculator
    deadlines/ priority, PCT, Madrid, Hague, opposition, response windows (office calendars)
    routes/    filing-route matrix from membership data
    exhaustion/ parallel-import decision table
    takedown/  notice schema, per-regime validator, counter-notice clocks, template render
    portfolio/ portfolio schema -> docket -> ICS
    transfer/  assignment / licence formalities checklist
    cli.py
    server.py  MCP
  skills/
    ip-country-brief/SKILL.md
    filing-strategy/SKILL.md
    takedown-notice/SKILL.md
    portfolio-intake/SKILL.md
  scripts/
    lint_data.py                citations, dates, staleness, schema
    refresh_wipo_membership.py  treaty membership from WIPO's published tables
    refresh_holidays.py         per office
  tests/
    golden/<CC>/                hand-computed cases per jurisdiction
```

**Why one repo.** The whole value is that every module reads the same jurisdiction packs.
The comparator, the deadline engine, the route optimiser and the docket generator all need
"PCT national phase in Vietnam is 31 months" to be one fact in one place. Split the modules
into repos and the data forks within a month.

**Relationship to the six existing repos.** `sg-deadline`'s engine design (rules as data,
trace as product, refuse-to-guess) is copied, not imported: IP offices have their own
computation-of-time rules (PCT Rule 80, EPC Rule 134, 37 CFR 1.7, Madrid Rule 4) and their
own holiday calendars, so `ipatlas/deadlines` is a generalisation with per-office rule
packs. `oblig-register`'s ICS writer is reused for dockets. `citecheck` and `chronology` are
unrelated.

## 7. Data model

### 7.1 Facts with provenance

Every leaf value that a lawyer would want to check is a `Fact`:

```yaml
term:
  value: { years: 10, from: filing_date, renewable: true, renewal_years: 10 }
  cite: "Trade Marks Act 1998, ss 18-19"
  checked: 2026-09-14
  verified: false
  in_force_from: 1999-01-15
  notes: ["Renewal may be requested within 6 months before expiry."]
```

Short form for the common case is allowed and expanded by the loader:

```yaml
term: { years: 10, from: filing_date, renewable: true, renewal_years: 10, cite: "TMA ss 18-19" }
```

A file-level `defaults: { checked: 2026-09-14, verified: false }` avoids repetition; per-fact
values override.

### 7.2 Temporal validity

A fact may carry `in_force_from` and `superseded_by` (a pointer to a fact in the same file's
`history` block). Queries take `as_of` (default today) and the loader resolves the correct
version. This is how the 2021 Singapore Copyright Act and its predecessor both exist
without a fork of the file.

### 7.3 Rights as typed blocks

`trade_mark`, `patent`, `utility_model`, `registered_design`, `copyright`, `trade_secret`,
`geographical_indication`, `plant_variety`. Each is a pydantic model with the attributes
in §5. Unknown attributes are a schema error; missing ones are permitted and render as
"not recorded", never as a default value.

### 7.4 Expressions for terms

Copyright and corporate-work terms need a small expression language, kept deliberately
bounded:

```yaml
copyright:
  term:
    literary: { base: author_death, plus_years: 70 }
    anonymous: { base: publication, plus_years: 70, alt: { base: creation, plus_years: 70 }, rule: earlier }
    corporate_us_style: { base: publication, plus_years: 95, alt: { base: creation, plus_years: 120 }, rule: earlier }
    sound_recording: { base: publication, plus_years: 70 }
  shorter_term_rule: { applies: false, cite: "..." }
```

Bases: `filing_date`, `registration_date`, `grant_date`, `priority_date`, `author_death`,
`publication`, `creation`, `fixation`, `first_sale`. Nothing else, until a real case needs it.

### 7.5 Offices and calendars

Deadlines are computed against the *office* that receives the act, not the jurisdiction:
a Madrid designation of Singapore is an IPOS deadline under WIPO rules. `offices/*.yaml`
carries the computation-of-time rule pack and points at a holiday file. Holiday files are
per office, vendored, dated, and refuse-on-missing exactly as in `sg-deadline`.

## 8. Modules

### 8.1 `compare`

`compare(jurisdictions, right, attributes, as_of) -> Table`. Renders markdown / CSV / JSON.
Every cell carries its cite and check date; unverified cells are marked. `brief(jurisdiction,
right)` renders the one-page country note from the same data, with a "not recorded" section
so the gaps are visible rather than silent.

### 8.2 `lifecycle`

`term(right, jurisdiction, dates) -> Result(expiry, renewal_windows, trace)`. Handles renewal
cycles with grace and restoration, maintenance-fee due dates and windows, patent term
extension where the pack says it exists (as a flag and a maximum, not a computation of the
extension itself, which is fact-specific). Copyright term calculator applies §7.4
expressions, corporate/anonymous branches and, where the pack says so, the rule of the
shorter term against a second jurisdiction.

### 8.3 `deadlines`

Priority windows (12 / 6 months, Paris), PCT national/regional phase per office, Madrid
refusal and response windows, Hague refusal, opposition windows from publication, standard
response windows to office actions where the pack records a default. Same engine shape as
`sg-deadline`: rule as data, office calendar, trace, refuse when the calendar is missing.

### 8.4 `routes`

`routes(right, targets) -> Matrix`. For each target: which treaty routes reach it, which
regional office covers it, whether a national filing is the only route (Taiwan; Hong Kong
for trade marks; Myanmar), and the traps the pack records (individual-fee Madrid members;
countries that require use claims; countries where Madrid replacement is unavailable).
Costs are not computed; a user-supplied fee table may be joined.

### 8.5 `exhaustion`

Decision table `(right, import_into, first_sale_in, conditions) -> outcome, cite`. Regimes:
national, regional (EEA), international; with condition hooks the packs use (Singapore's
TMA s 29(2) exceptions; EU's "legitimate reasons"; US copyright first sale after
*Kirtsaeng*; US patent after *Lexmark*; Australia's s 122A defence). Output is a
determination *under the recorded rule* with the conditions that would change it listed,
never "you may import".

### 8.6 `takedown`

A `Notice` schema (rights holder, right, work identification, infringing material
locators, contact, statements, authorisation, signature) and a per-regime requirement set
(US DMCA §512(c)(3); EU DSA Art 16; China E-Commerce Law Arts 42-43 and the 15-day
counter-notice wait; Singapore Copyright Act 2021 network-service-provider regime; and
others as packs record them). `check(notice, regime) -> findings`. `counter_notice_window
(regime, served_on)` via `deadlines`. `render(notice, regime)` produces a compliant text
from a template that quotes the statutory language where the statute prescribes it.

### 8.7 `portfolio`

Schema: families → rights → jurisdictions → status and key dates. `docket(portfolio, as_of)`
runs `lifecycle` and `deadlines` over every entry and emits a markdown docket and an ICS
with lead-time alarms (reusing `oblig-register`'s writer). This is the open alternative to
the docketing systems, minus the parts that need an office data feed.

### 8.8 `transfer`

`formalities(jurisdiction, right, transaction) -> Checklist`. Writing requirement, recordal
(mandatory / optional / effect against third parties), government approval (China's
technology-export control on outbound patent assignments; SAMR approval of trade mark
assignments), notarisation / legalisation, assignment of associated goodwill, partial
assignment rules.

### 8.9 MCP server

Tools: `list_jurisdictions`, `country_brief`, `compare`, `term`, `deadline`, `routes`,
`exhaustion`, `takedown_check`, `takedown_render`, `transfer_formalities`, `docket`.
Server instructions: answer only from tool results; repeat citations and verification
flags verbatim; when a jurisdiction or attribute is not recorded say so and stop.

### 8.10 Skills

Thin orchestration over the tools, each with a "what you may not do" section:
`ip-country-brief` (assemble and gap-mark, never fill gaps from memory),
`filing-strategy` (routes + deadlines + a decision memo), `takedown-notice` (draft, check,
render, never send), `portfolio-intake` (turn a spreadsheet into the portfolio schema with
every date traced to a source column).

## 9. Phasing

| Phase | Deliverable | Definition of done |
|---|---|---|
| **0 — Spine** (2 weeks) | `core` + `compare` + MCP; packs for SG, US, EU, CN × trade mark, patent, copyright; lint; `ip-country-brief` skill | `compare([SG,CN], trade_mark, [term, opposition, use_requirement, exhaustion])` returns a cited table; lint passes; every fact has a cite or is flagged |
| **1 — Time** (2 weeks) | `deadlines` + `lifecycle`; office packs for IPOS, USPTO, EPO, EUIPO, CNIPA, WIPO (PCT/Madrid) with 2025–2027 holidays; treaty data; `routes` | Golden tests: Paris priority, PCT 30/31 months per office, Madrid refusal windows, SG/US/EU TM renewal with grace; route matrix for a 10-country list |
| **2 — Platforms** (2 weeks) | `exhaustion` + `takedown`; `takedown-notice` skill | Decision table covers SG/US/EU/CN for TM, copyright, patent; DMCA / DSA / CN / SG notice validators with golden good-and-bad notices |
| **3 — Portfolio** (2 weeks) | `portfolio` + `transfer`; `portfolio-intake` skill; ICS docket | A 30-entry sample portfolio produces a docket whose every date is traced |
| **4 — Breadth** (ongoing) | JP, KR, AU, GB, then ASEAN, then by contribution; designs and Hague; trade secrets; copyright term with shorter-term rule | Each pack lands with its golden tests and passes lint |

Phase 0 is the whole bet. If a cited comparison table across four jurisdictions is not
obviously useful to a practitioner, stop there.

## 10. Risks, honestly

| Risk | Mitigation |
|---|---|
| **Curation cost.** A good pack is 1–2 days of careful reading per jurisdiction by someone who knows the system; 16 jurisdictions × 6 rights is months. | Start with 4 × 3. `verified: false` by default. Contribution model is one file. Publish the gaps as the roadmap. |
| **Legal drift.** EU design reform (2024–25), China TM Law amendments, ASEAN accessions: facts rot. | `checked` dates + staleness lint (warn at 12 months, error at 24). Temporal validity keeps history instead of overwriting. Changelog per pack. |
| **Overclaiming.** A clean table looks authoritative; a wrong cell in a clean table is worse than no table. | Cites and flags rendered in every output, not just stored. Unverified cells visibly marked. README leads with what is not recorded. |
| **EU as a jurisdiction.** EUIPO/EPO/directives plus 27 member states with divergent copyright, exhaustion nuances and national TM systems. | Model `EU` as a supranational pack with `member_state_notes`; national packs (DE, FR, ...) only when someone owns them. |
| **Holiday data across ~8 offices.** | Per-office files, refresh scripts, refuse-on-missing. Accept that this is recurring work and say so. |
| **Name collision.** `ipatlas` may be taken on PyPI or GitHub. | Check before init; fallbacks `ip-atlas`, `crossip`, `iprights-data`. |

## 11. What would make this fail

- Trying to ship 16 jurisdictions at once with half the facts unverified. The data's value
  is its trustworthiness, and that is per cell.
- Adding fees, cost estimates or a search feature because users ask. Each drags the repo
  toward staleness or overclaiming.
- Letting the skills fill gaps from model memory "just this once". The MCP instructions and
  the skill rules exist to prevent exactly this; hold the line.

## 12. Open questions for the owner

1. EU modelling: one supranational pack now, member states later — agreed?
2. Utility models: separate right block (CN, JP, KR, DE have them; SG/US do not) or a flag
   on `patent`? Recommendation: separate block; the terms and examination differ too much.
3. Should `takedown` ship platform-specific policy requirements (marketplace programme
   rules) or statutory regimes only? Recommendation: statutory only; platform policies are
   contracts, they change weekly, and they belong in a user-maintained overlay.
4. Licence: MIT for code; CC BY 4.0 for `data/`? The data is the asset and attribution
   is the incentive for contributors. Recommendation: dual-licence exactly so.
