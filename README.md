# ipatlas

Cross-border intellectual property as structured, cited, versioned data, with deterministic
engines on top.

```
$ ipatlas compare trade_mark SG US CN -a filing_system -a term -a use_requirement

| Attribute          | SG                          | US                               | CN                               |
|---|---|---|---|
| **Filing system**  | first to file               | first to use                     | first to file                    |
| **Term**           | 10 years from filing date,  | 10 years from registration date, | 10 years from registration date, |
|                    | renewable for 10 years      | renewable for 10 years           | renewable for 10 years           |
| **Use requirement**| 5 years of non-use, then    | 3 years of non-use, then         | 3 years of non-use, then         |
|                    | revocation on application   | cancellation on petition         | cancellation on application      |

## Where they differ
- Filing system
- Term
- Use requirement

## Sources
[^1]: SG — TMA 1998, s 5 and Part III generally (UNVERIFIED, checked 2026-09-12)
[^2]: US — 15 U.S.C. §§ 1051, 1057(c) (UNVERIFIED, checked 2026-09-12)
[^3]: CN — 商标法 第31条 (Trademark Law, Art 31) (UNVERIFIED, checked 2026-09-12)
...
```

**Status: Phase 1 complete.** Data model, loader, linter, comparator, office calendars,
deadline engine, lifecycle (terms/renewals/copyright) and filing-route matrices are built
and tested (131 tests). Packs for **SG, US, CN**; office packs for **IPOS, USPTO, CNIPA,
WIPO, EPO, EUIPO**; treaty packs for **Paris, PCT, Madrid, Hague**. The exhaustion,
takedown, portfolio and transfer engines are designed but not written — see
[PLAN.md](PLAN.md) for the design and phasing, [CLAUDE.md](CLAUDE.md) for the engineering
contract.

**Nothing in the data is verified.** Every fact carries `verified: false` and every output
surface says so. Do not rely on a cell without checking its citation.

## Why

Every cross-border IP question has the same shape: *for right R in jurisdiction J, what is
the rule on X, what is the date, and what is the source?* Today those answers live in
paywalled country guides, in foreign associates' heads, and in docketing systems that cost
six figures. None of it is open, structured, or callable by an assistant — so when an AI is
asked one of these questions it answers from memory, which is where the errors come from.

IP law is unusually tabular: the treaties (Paris, TRIPS, Berne, PCT, Madrid, Hague)
harmonise the *categories*, so the same attributes exist everywhere and only the values
differ. That is exactly the shape a comparator wants.

## What works today

| Command | What it does |
|---|---|
| `ipatlas jurisdictions` | List loaded packs, their offices, fact counts and available rights |
| `ipatlas compare <right> <JUR...>` | Cited comparison table (markdown / CSV / JSON) with a "where they differ" section and gaps listed as gaps |
| `ipatlas brief <JUR> <right>` | One-page country note assembled from the pack, with unrecorded attributes shown as unrecorded |
| `ipatlas fact <JUR> <path>` | One fact with its citation, check date and notes |
| `ipatlas offices` | Office packs and their closure-data coverage |
| `ipatlas deadline <kind> <JUR> <date>` | Paris priority, PCT national phase, opposition, Madrid refusal — with a full derivation |
| `ipatlas term <JUR> <right> --date base=YYYY-MM-DD` | Expiry and renewal schedule with grace and restoration |
| `ipatlas copyright-term <JUR> <category>` | Copyright term expressions, including "whichever is earlier" limbs |
| `ipatlas routes <right> <JUR...>` | Filing-route matrix with the traps the packs record |
| `ipatlas lint` | The data quality gate; exit 1 on errors |
| `--as-of YYYY-MM-DD` | Answer under the law in force on that date |

### Deadlines

```
$ ipatlas deadline priority CN 2026-03-13 --right trade_mark

Paris priority deadline for trade mark filing in CN
the day of first filing is excluded from the priority period (Paris Convention, Art 4C(2))
period: 6 months (pack CN:trade_mark.priority: 商标法 第25条 (Art 25)) [unverified]
trigger: 2026-03-13 (Fri)
office: CNIPA (China National Intellectual Property Administration)
month arithmetic (corresponding_date, 专利法实施细则): 2026-03-13 (Fri) + 6 months = 2026-09-13 (Sun)
2026-09-13 (Sun): Sunday. Rolled forward to the next day the office is open, 2026-09-14 (Mon)
DEADLINE: 2026-09-14 (Mon)
CNIPA closure data 2026: UNVERIFIED, source=State Council annual holiday notice
  caution: INCOMPLETE. Holiday blocks are approximate and the compensating working weekends
  are NOT recorded, so any computation crossing a block must be checked.
WARNING: the period was read from pack CN:trade_mark.priority, which is marked unverified
```

Deadlines compute against the **office that receives the act**, not the jurisdiction. Periods
come from the packs, so the citation travels with the answer. Three properties worth noting:

- **The office calendar refuses rather than assumes.** `ipatlas deadline madrid-refusal CN
  2026-04-01` exits 3: an 18-month window lands in 2027 and the CNIPA pack has no 2027
  closure data. Chinese holidays are set annually by State Council notice and include
  compensating working weekends, so padding the pack with guessed dates would be worse than
  the refusal.
- **Days and months are different.** US trade mark opposition is 30 *days* from publication;
  Singapore's is 2 *months*; China's is 3 months and not extendable. The engine reads whichever
  the pack records and says which.
- **Unverified periods produce a warning on every result**, not just in the data file.

### Terms and renewals

```
$ ipatlas term US trade_mark --date filing_date=2020-03-01
missing date: US trade_mark term runs from registration_date, which you did not supply.
Supplied: filing_date. This matters: a term running from registration expires later than
one running from filing.
```

That refusal is the feature. Singapore trade mark terms run from filing and US and Chinese
terms run from registration, so the same mark expires on different dates — and an engine
that quietly accepted the wrong date would hide exactly the divergence the dataset exists to
record. Renewal schedules carry the grace and restoration windows; `registered_design` stops
at the recorded maximum duration.

Copyright terms apply the recorded expression, including two-limb rules:

```
$ ipatlas copyright-term US works_made_for_hire --date publication=2000-01-01 --date creation=1990-01-01
  primary: publication 2000-01-01 + 95 years = 2095-01-01
  alternative: creation 1990-01-01 + 120 years = 2110-01-01
  rule: whichever is earlier -> 2095-01-01
```

Same author's death, three jurisdictions: SG and US give 2070-06-15; China gives
2050-12-31, because the term is 50 years and runs to the end of the calendar year.

Rights covered by the three packs: trade marks, patents, utility models, registered
designs, copyright, trade secrets, geographical indications, plant varieties (SG), plus
transfer formalities and statutory takedown regimes.

## Install

```bash
pip install -e ".[dev]"
python -m pytest          # 131 tests
ipatlas lint              # 0 errors, 2 known research gaps
```

Python 3.11+.

## The data model

Every leaf is a **Fact**: a value plus the provenance that makes it checkable.

```yaml
term: { years: 10, from: filing_date, renewable: true, renewal_years: 10,
        cite: "TMA 1998, ss 18-19" }
```

Short form expands to a full `Fact`; a file-level `defaults:` supplies `checked` and
`verified`. A fact with a value and no citation is a **lint error** — an uncited value is a
rumour, not a fact.

### Temporal validity

Laws change, so facts have validity periods and queries have an `as_of`:

```bash
$ ipatlas fact US patent.filing_system
first to file [unverified]
  source: 35 U.S.C. § 102 as amended by the Leahy-Smith America Invents Act

$ ipatlas --as-of 2010-01-01 fact US patent.filing_system
first to invent [unverified]
  source: 35 U.S.C. § 102(g) (pre-AIA)
```

Superseded rules move into a `history:` block rather than being overwritten. The packs carry
real examples: the AIA shift to first-to-file (16 March 2013), *Lexmark* moving US patent
exhaustion from national to international (30 May 2017), China's design term going from 10
to 15 years (1 June 2021), and Singapore's 1987 Copyright Act giving way to the 2021 Act.

### The linter is the mechanism

`ipatlas lint` enforces what `CLAUDE.md` promises: citations present, `checked` dates
present and not in the future, staleness (warn at 12 months, **error at 24**), closed
enumerations, `unsettled` values carrying an explanation, non-overlapping history, and
`verified: true` backed by a note recording what was checked. Negative facts ("no utility
model system here") are held to a warning, because you can rarely cite the absence of a
provision.

A genuinely un-researched attribute is written as a note with no value, so the linter
reports it as an open gap:

```yaml
shorter_term_rule:
  notes: ["Not yet researched. Record whether SG applies Berne Art 7(8)."]
```

Never `applies: null` — a null is not an answer.

## What the comparison actually surfaces

The three packs are chosen to make the divergences that matter visible:

- **Trade mark term runs from different events.** Filing in SG, registration in US and CN —
  so the same mark expires on different dates in each.
- **The US § 8 declaration of use** has no analogue in SG or CN, and is the most commonly
  missed US trade mark deadline. `maintenance` is a separate attribute from `renewal` for
  exactly this reason.
- **Patent grace periods are asymmetric.** 12 months for an inventor's own disclosure in the
  US and SG; 6 months on enumerated grounds only in China. A US-led programme relying on
  § 102(b)(1) destroys novelty in China.
- **Patent annuities differ in kind.** Three fees from grant in the US; annual from filing in
  SG and CN. Docketing on an annuity assumption mis-handles US cases.
- **Trade mark assignment recordal is constitutive in China** and merely protective in SG and
  the US — and a Chinese patent assignment to a foreign party is a technology export
  requiring clearance, which is a closing condition rather than a formality.
- **Chinese trade mark exhaustion is recorded as `unsettled`**, with a note, rather than
  forced into a clean value. That is the honest answer and the schema permits it.

## Not built yet

The exhaustion decision table, takedown notice validation, portfolio dockets with ICS
export, and transfer-formality checklists. All designed in [PLAN.md](PLAN.md) §8; phased
in §9.

Known coverage gaps in what *is* built:

- **Closure data is thin.** IPOS and USPTO have 2026–2027; the rest have 2026 only. Every
  year is `verified: false`, and the 2027 IPOS set is projected rather than gazetted.
- **CNIPA compensating working weekends are not modelled.** The field exists and is
  deliberately empty: a wrongly-designated working day *shortens* a deadline, so guessing is
  the dangerous direction.
- **EPO, EUIPO and WIPO closure lists are projected**, not taken from the published lists.
  EPO Rule 134(1) turns on *all* filing offices being open, which widens the effective set.

## Deliberately out of scope

Official fees (they change quarterly and would drag the dataset into staleness),
case-law retrieval, prior-art search, freedom-to-operate, and platform-specific programme
rules. Statutory regimes only.

## Contributing

One jurisdiction, one file, one owner. `data/jurisdictions/SG.yaml` is the reference shape.
Read `CLAUDE.md` first — it binds humans and AI assistants equally. A pack PR lands with its
golden tests and passes `python scripts/lint_data.py`.

## Licence

Code MIT. Data (`data/`) intended as CC BY 4.0 — see PLAN.md §12 open question 4.
