"""The data quality gate. Each rule has a test that triggers it."""

import datetime as dt

import pytest

from ipatlas import load_atlas, load_pack
from ipatlas.core.fact import parse_fact
from ipatlas.core.lint import errors, lint_atlas, lint_fact, lint_pack

TODAY = dt.date(2026, 9, 12)


def _f(node, path="trade_mark.exhaustion"):
    return parse_fact(node, path=path, jurisdiction="ZZ", defaults={})


def _msgs(findings):
    return " | ".join(f.message for f in findings)


@pytest.fixture(scope="module")
def atlas():
    return load_atlas()


def test_bundled_packs_have_no_errors(atlas):
    """The shipped data must always pass. A pack that fails this does not ship."""
    findings = lint_atlas(atlas, as_of=TODAY)
    assert errors(findings) == [], _msgs(errors(findings))


def test_only_the_known_research_gaps_remain_as_warnings(atlas):
    warns = [f for f in lint_atlas(atlas, as_of=TODAY) if f.severity == "warn"]
    assert {(f.jurisdiction, f.path) for f in warns} == {
        ("SG", "copyright.shorter_term_rule"),
        ("CN", "copyright.shorter_term_rule"),
    }


# -- individual rules ------------------------------------------------------------------

def test_uncited_positive_value_is_an_error():
    out = lint_fact(_f({"value": "international", "checked": "2026-09-01"}), as_of=TODAY)
    assert any(f.severity == "error" and "uncited value" in f.message for f in out)


def test_uncited_negative_value_is_only_a_warning():
    out = lint_fact(_f({"available": False, "checked": "2026-09-01"},
                       path="patent.border_measures"), as_of=TODAY)
    assert [f.severity for f in out] == ["warn"]
    assert "asserts an absence" in out[0].message


def test_statute_and_available_are_exempt_from_the_cite_requirement():
    for path in ("trade_mark.statute", "utility_model.available"):
        out = lint_fact(_f({"value": "x", "checked": "2026-09-01"}, path=path), as_of=TODAY)
        assert not any("cite" in f.message for f in out), path


def test_missing_checked_date_is_an_error():
    out = lint_fact(_f({"value": "international", "cite": "s 29"}), as_of=TODAY)
    assert any("no `checked` date" in f.message for f in out)


def test_future_checked_date_is_an_error():
    out = lint_fact(_f({"value": "x", "cite": "c", "checked": "2027-01-01"}), as_of=TODAY)
    assert any("in the future" in f.message for f in out)


def test_staleness_warns_at_twelve_months_and_errors_at_twenty_four():
    fresh = lint_fact(_f({"value": "x", "cite": "c", "checked": "2026-01-01"}), as_of=TODAY)
    assert not any("checked" in f.message and "months ago" in f.message for f in fresh)

    stale = lint_fact(_f({"value": "x", "cite": "c", "checked": "2025-06-01"}), as_of=TODAY)
    assert [f.severity for f in stale if "months ago" in f.message] == ["warn"]

    rotten = lint_fact(_f({"value": "x", "cite": "c", "checked": "2024-01-01"}), as_of=TODAY)
    assert [f.severity for f in rotten if "months ago" in f.message] == ["error"]


def test_verified_without_a_citation_is_an_error():
    out = lint_fact(_f({"value": "x", "verified": True, "checked": "2026-09-01"}), as_of=TODAY)
    assert any("`verified: true` without a citation" in f.message for f in out)


def test_verified_without_a_note_warns():
    out = lint_fact(_f({"value": "x", "cite": "c", "verified": True, "checked": "2026-09-01"}),
                    as_of=TODAY)
    assert any("no note recording what was checked" in f.message for f in out)


def test_verified_with_evidence_is_clean():
    out = lint_fact(_f({"value": "international", "cite": "TMA 1998, s 29", "verified": True,
                        "checked": "2026-09-01",
                        "notes": ["Checked against SSO text in force 2026-09-01."]}), as_of=TODAY)
    assert out == []


def test_closed_enum_rejects_an_invented_member():
    out = lint_fact(_f({"value": "quasi_international", "cite": "c", "checked": "2026-09-01"}),
                    as_of=TODAY)
    assert any("not in the closed set" in f.message for f in out)


def test_first_to_invent_is_expressible_for_history():
    out = lint_fact(_f({"value": "first_to_invent", "cite": "pre-AIA § 102(g)",
                        "checked": "2026-09-01"}, path="patent.filing_system"), as_of=TODAY)
    assert not any("closed set" in f.message for f in out)


def test_unsettled_must_carry_a_note():
    bare = lint_fact(_f({"value": "unsettled", "cite": "c", "checked": "2026-09-01"}),
                     as_of=TODAY)
    assert any("must carry a note" in f.message for f in bare)
    noted = lint_fact(_f({"value": "unsettled", "cite": "c", "checked": "2026-09-01",
                          "notes": ["Courts have diverged."]}), as_of=TODAY)
    assert noted == []


def test_group_notes_are_not_flagged_as_empty_placeholders(atlas):
    # copyright.term carries a group-level note in SG and US; it must not warn.
    findings = lint_pack(atlas["US"], as_of=TODAY)
    assert not any(f.path == "copyright.term" for f in findings)


def test_value_less_note_is_flagged_as_an_open_gap(atlas):
    findings = lint_pack(atlas["SG"], as_of=TODAY)
    gap = [f for f in findings if f.path == "copyright.shorter_term_rule"]
    assert gap and "record the fact or delete the placeholder" in gap[0].message


def test_inverted_validity_period_is_an_error():
    out = lint_fact(_f({"value": "x", "cite": "c", "checked": "2026-09-01",
                        "in_force_from": "2020-01-01", "in_force_until": "2019-01-01"}),
                    as_of=TODAY)
    assert any("precedes in_force_from" in f.message for f in out)


# -- pack-level rules ------------------------------------------------------------------

def _pack(tmp_path, body: str):
    p = tmp_path / "ZZ.yaml"
    p.write_text("jurisdiction: ZZ\nname: Test\noffice: ZZO\n"
                 "defaults: { checked: 2026-09-01 }\n" + body, encoding="utf-8")
    return load_pack(p)


def test_overlapping_history_periods_are_an_error(tmp_path):
    pack = _pack(tmp_path, """
patent:
  term: { years: 20, from: filing_date, cite: c, in_force_from: 2010-01-01 }
history:
  patent.term:
    - value: { years: 17 }
      cite: a
      in_force_from: 1990-01-01
      in_force_until: 2005-06-01
    - value: { years: 18 }
      cite: b
      in_force_from: 2005-01-01
      in_force_until: 2009-12-31
""")
    out = lint_pack(pack, as_of=TODAY)
    assert any("overlapping validity periods" in f.message for f in out)


def test_current_fact_with_history_must_declare_its_own_start(tmp_path):
    pack = _pack(tmp_path, """
patent:
  term: { years: 20, from: filing_date, cite: c }
history:
  patent.term:
    - value: { years: 17 }
      cite: a
      in_force_from: 1990-01-01
      in_force_until: 2009-12-31
""")
    out = lint_pack(pack, as_of=TODAY)
    assert any("no `in_force_from` of its own" in f.message for f in out)


def test_history_for_an_unknown_path_is_an_error(tmp_path):
    pack = _pack(tmp_path, """
history:
  patent.nonexistent:
    - value: 1
      cite: a
      in_force_from: 1990-01-01
      in_force_until: 2000-01-01
""")
    out = lint_pack(pack, as_of=TODAY)
    assert any("history for a path with no current fact" in f.message for f in out)


def test_pack_without_an_office_warns(tmp_path):
    p = tmp_path / "ZZ.yaml"
    p.write_text("jurisdiction: ZZ\nname: Test\n", encoding="utf-8")
    out = lint_pack(load_pack(p), as_of=TODAY)
    assert any(f.path == "office" and f.severity == "warn" for f in out)
