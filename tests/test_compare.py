import datetime as dt

import pytest

from ipatlas import NotRecordedError, brief, compare, load_atlas, load_pack
from ipatlas.compare import DEFAULT_ATTRIBUTES


@pytest.fixture(scope="module")
def atlas():
    return load_atlas()


def test_compare_surfaces_the_real_divergences(atlas):
    t = compare(atlas, "trade_mark", ["SG", "US", "CN"],
                ["filing_system", "term", "use_requirement", "opposition", "exhaustion"])
    assert t.coverage == (15, 15)
    assert t.unverified == 15  # nothing is verified yet, and the table must say so
    assert set(t.divergences()) == {"filing_system", "term", "use_requirement",
                                    "opposition", "exhaustion"}
    assert t.cell("filing_system", "US").fact.value == "first_to_use"
    assert t.cell("filing_system", "SG").fact.value == "first_to_file"
    # Term length agrees but the start date does not: the cell values must differ.
    assert t.cell("term", "SG").fact.value["from"] == "filing_date"
    assert t.cell("term", "US").fact.value["from"] == "registration_date"


def test_compare_finds_agreement_where_it_exists(atlas):
    t = compare(atlas, "patent", ["SG", "US", "CN"], ["term", "pct"])
    assert t.divergences() == ["pct"]  # all three are 20 years from filing
    assert {t.cell("term", j).fact.value["years"] for j in ("SG", "US", "CN")} == {20}


def test_unavailable_right_is_reported_not_blank(atlas):
    t = compare(atlas, "utility_model", ["SG", "CN"], ["term"])
    sg = t.cell("term", "SG")
    assert not sg.recorded
    assert "does not provide this right" in sg.missing_reason
    assert t.cell("term", "CN").fact.value["years"] == 10


def test_maintenance_divergence_is_visible(atlas):
    """The US § 8 declaration is an obligation SG and CN have no analogue for."""
    t = compare(atlas, "trade_mark", ["SG", "US", "CN"], ["maintenance"])
    assert t.coverage == (3, 3)
    assert t.divergences() == ["maintenance"]
    assert t.cell("maintenance", "US").fact.value["consequence"] == "cancellation"
    assert t.cell("maintenance", "SG").fact.value == {"separate_obligation": False}


def test_missing_attribute_is_a_gap_with_a_reason(atlas):
    t = compare(atlas, "patent", ["SG", "US"], ["provisional_applications"])
    sg = t.cell("provisional_applications", "SG")
    assert not sg.recorded and "not recorded" in sg.missing_reason
    assert t.cell("provisional_applications", "US").recorded
    md = t.to_markdown()
    assert "## Not recorded" in md and "SG" in md


def test_compare_is_dated(atlas):
    now = compare(atlas, "patent", ["US"], ["exhaustion"], as_of=dt.date(2026, 1, 1))
    then = compare(atlas, "patent", ["US"], ["exhaustion"], as_of=dt.date(2015, 1, 1))
    assert now.cell("exhaustion", "US").fact.value == "international"
    assert then.cell("exhaustion", "US").fact.value == "national"


def test_default_attribute_set_is_used_when_none_given(atlas):
    t = compare(atlas, "trade_mark", ["SG"])
    assert t.attributes == DEFAULT_ATTRIBUTES["trade_mark"]


def test_unknown_right_lists_the_known_ones(atlas):
    with pytest.raises(NotRecordedError, match="known:"):
        compare(atlas, "moral_rights", ["SG"])


def test_markdown_carries_flags_and_numbered_sources(atlas):
    md = compare(atlas, "trade_mark", ["SG", "CN"], ["term", "exhaustion"]).to_markdown()
    assert "[unverified]" in md
    assert "## Sources" in md and "[^1]:" in md
    assert "UNVERIFIED, checked 2026-09-12" in md
    # CJK citations must survive rendering intact.
    assert "商标法" in md


def test_markdown_escapes_pipes(atlas):
    md = compare(atlas, "trade_mark", ["US"], ["exhaustion"]).to_markdown()
    for line in md.splitlines():
        if line.startswith("| **"):
            assert line.count("|") == 3  # leading, separator, trailing only


def test_csv_round_trip_has_provenance_columns(atlas):
    csv_text = compare(atlas, "trade_mark", ["SG"], ["term"]).to_csv()
    header, row = csv_text.splitlines()[:2]
    assert header.split(",") == ["attribute", "jurisdiction", "value", "verified", "cite",
                                 "url", "checked", "notes"]
    assert row.startswith("term,SG,")
    assert ",no," in row  # verified = no


def test_json_shape(atlas):
    d = compare(atlas, "trade_mark", ["SG", "US"], ["term"]).to_dict()
    assert d["coverage"] == {"recorded": 2, "total": 2, "unverified": 2}
    assert d["divergences"] == ["term"]
    assert len(d["cells"]) == 2
    assert d["cells"][0]["fact"]["cite"] == "TMA 1998, ss 18-19"


# -- briefs ----------------------------------------------------------------------------

def test_brief_warns_about_unverified_content(atlas):
    out = brief(atlas["SG"], "trade_mark")
    assert "**unverified**" in out
    assert "Intellectual Property Office of Singapore (IPOS)" in out
    assert "TMA 1998, ss 18-19" in out


def test_brief_shows_an_unresearched_attribute_as_not_recorded(atlas):
    """`shorter_term_rule` is a value-less note in both packs: an open research gap."""
    out = brief(atlas["SG"], "copyright")
    assert "**Shorter term rule** — not recorded." in out
    assert "Not yet researched" in out


def test_brief_lists_missing_comparison_attributes(tmp_path):
    """A sparse pack must advertise its gaps rather than read as complete.

    Tested on a fixture, not on a shipped pack: the shipped packs are complete against
    their default comparison sets, and this code path must stay covered even so.
    """
    p = tmp_path / "ZZ.yaml"
    p.write_text(
        "jurisdiction: ZZ\nname: Testland\noffice: ZZO\n"
        "defaults: { checked: 2026-09-01 }\n"
        "trade_mark:\n"
        "  term: { years: 10, from: filing_date, cite: 'Testland TMA s 1' }\n",
        encoding="utf-8")
    out = brief(load_pack(p), "trade_mark")
    assert "## Not recorded" in out
    assert "gaps in the data, not statements that the law is silent" in out
    assert "- Filing system" in out and "- Exhaustion" in out
    assert "10 years from filing date" in out


def test_brief_for_unavailable_right_says_so(atlas):
    out = brief(atlas["SG"], "utility_model")
    assert "**Not available.**" in out
    assert "no utility model" in out.lower()


def test_brief_is_dated(atlas):
    old = brief(atlas["CN"], "registered_design", as_of=dt.date(2021, 1, 1))
    new = brief(atlas["CN"], "registered_design", as_of=dt.date(2026, 1, 1))
    assert "10 years from filing date" in old
    assert "15 years from filing date" in new
