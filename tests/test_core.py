"""Loader, fact expansion, temporal resolution. Expectations are literal, not derived."""

import datetime as dt

import pytest

from ipatlas import NotRecordedError, load_atlas
from ipatlas.core.fact import is_fact_mapping, parse_fact
from ipatlas.core.pack import PackError, load_pack


@pytest.fixture(scope="module")
def atlas():
    return load_atlas()


# -- fact expansion -------------------------------------------------------------------

def _f(node, path="x.y"):
    return parse_fact(node, path=path, jurisdiction="ZZ", defaults={})


def test_short_form_becomes_value_dict():
    f = _f({"years": 10, "from": "filing_date", "cite": "TMA ss 18-19"})
    assert f.value == {"years": 10, "from": "filing_date"}
    assert f.extra == {}
    assert f.cite.text == "TMA ss 18-19"


def test_explicit_value_keeps_qualifiers_as_extra():
    f = _f({"value": "nice", "edition_followed": "current", "cite": "r 19"})
    assert f.value == "nice"
    assert f.extra == {"edition_followed": "current"}


def test_url_is_attached_to_the_cite_not_the_value():
    f = _f({"value": "international", "cite": "s 29", "url": "https://example.test"})
    assert f.value == "international"
    assert f.cite.url == "https://example.test"
    assert f.extra == {}


def test_defaults_supply_checked_and_verified():
    f = parse_fact({"value": 1, "cite": "c"}, path="p", jurisdiction="ZZ",
                   defaults={"checked": "2026-01-02", "verified": True})
    assert f.checked == dt.date(2026, 1, 2)
    assert f.verified is True


def test_per_fact_keys_override_defaults():
    f = parse_fact({"value": 1, "cite": "c", "verified": False, "checked": "2026-03-04"},
                   path="p", jurisdiction="ZZ", defaults={"checked": "2026-01-02",
                                                          "verified": True})
    assert f.verified is False and f.checked == dt.date(2026, 3, 4)


def test_group_vs_fact_detection():
    assert is_fact_mapping({"value": "x", "cite": "c"})
    assert is_fact_mapping({"years": 10, "from": "filing_date"})  # flat leaf
    assert is_fact_mapping({"available": False, "notes": ["n"]})
    assert not is_fact_mapping({"term": {"years": 10}, "priority": {"months": 6}})  # group
    assert not is_fact_mapping("scalar")


def test_fact_with_nested_mapping_and_own_cite_is_still_a_fact():
    # `alt` is a nested mapping, but the presence of `cite` makes this one fact.
    assert is_fact_mapping({"base": "publication", "plus_years": 95,
                            "alt": {"base": "creation", "plus_years": 120}, "cite": "§ 302(c)"})


def test_unverified_flag_is_in_the_rendered_output():
    assert _f({"value": "international", "cite": "c"}).render().endswith("[unverified]")
    f = parse_fact({"value": "international", "cite": "c", "verified": True},
                   path="p", jurisdiction="ZZ", defaults={})
    assert "[unverified]" not in f.render()


def test_negative_fact_detection():
    assert _f({"available": False}).is_negative
    assert _f({"value": "none"}).is_negative
    assert _f({"value": "not_available"}).is_negative
    assert not _f({"available": True}).is_negative
    assert not _f({"value": "international"}).is_negative


# -- value rendering ------------------------------------------------------------------

def test_renders_term_as_a_lawyer_would_say_it():
    assert _f({"years": 10, "from": "filing_date", "renewable": True, "renewal_years": 10,
               "cite": "c"}).render_value() == "10 years from filing date, renewable for 10 years"
    assert _f({"years": 5, "from": "filing_date", "renewable": True, "renewal_years": 5,
               "max_years": 15, "cite": "c"}).render_value() == \
        "5 years from filing date, renewable for 5 years (maximum 15 years)"
    assert _f({"years": 15, "from": "grant_date", "renewable": False, "cite": "c"}) \
        .render_value() == "15 years from grant date, not renewable"


def test_renders_copyright_term_expression():
    assert _f({"base": "author_death", "plus_years": 70, "cite": "c"}).render_value() == \
        "author death plus 70 years"
    assert _f({"base": "publication", "plus_years": 95,
               "alt": {"base": "creation", "plus_years": 120}, "rule": "earlier",
               "cite": "c"}).render_value() == \
        "publication plus 95 years, or creation plus 120 years, whichever is earlier"


def test_renders_windows_and_use_requirements():
    assert _f({"window_months": 2, "from": "publication", "extendable": True,
               "max_extension_months": 4, "cite": "c"}).render_value() == \
        "2 months from publication (extendable by up to 4 months)"
    assert _f({"window_months": 3, "from": "publication", "extendable": False,
               "cite": "c"}).render_value() == "3 months from publication (not extendable)"
    assert _f({"non_use_years": 3, "consequence": "cancellation_on_application",
               "cite": "c"}).render_value() == \
        "3 years of non-use, then cancellation on application"


def test_unrecognised_shape_still_renders_every_key():
    out = _f({"frequency": "annual", "from_year": 5, "cite": "c"}).render_value()
    assert "frequency: annual" in out and "from year: 5" in out


# -- pack loading ---------------------------------------------------------------------

def test_three_packs_load(atlas):
    assert atlas.codes == ["CN", "SG", "US"]
    assert atlas["sg"].name == "Singapore"  # case-insensitive lookup
    assert "SG" in atlas and "JP" not in atlas


def test_unknown_jurisdiction_names_what_is_loaded(atlas):
    with pytest.raises(NotRecordedError, match="CN, SG, US"):
        atlas["JP"]  # noqa: B018


def test_dotted_path_addressing(atlas):
    f = atlas["SG"].get("trade_mark.use_requirement")
    assert f.value["non_use_years"] == 5
    assert atlas["US"].get("trade_mark.use_requirement").value["non_use_years"] == 3
    assert atlas["CN"].get("copyright.term.legal_person_works").value["plus_years"] == 50


def test_missing_attribute_raises_rather_than_defaulting(atlas):
    with pytest.raises(NotRecordedError, match="not recorded"):
        atlas["SG"].get("trade_mark.no_such_attribute")
    assert atlas["SG"].try_get("trade_mark.no_such_attribute") is None


def test_has_right_respects_an_explicit_unavailable(atlas):
    assert atlas["CN"].has_right("utility_model")
    assert not atlas["SG"].has_right("utility_model")
    assert not atlas["US"].has_right("utility_model")
    assert "utility_model" not in atlas["SG"].rights
    assert "utility_model" in atlas["CN"].rights


def test_pack_filename_must_match_jurisdiction(tmp_path):
    p = tmp_path / "XX.yaml"
    p.write_text("jurisdiction: YY\nname: Wrong\n", encoding="utf-8")
    with pytest.raises(PackError, match="filename must match"):
        load_pack(p)


def test_lowercase_jurisdiction_code_rejected(tmp_path):
    p = tmp_path / "zz.yaml"
    p.write_text("jurisdiction: zz\nname: Lower\n", encoding="utf-8")
    with pytest.raises(PackError, match="upper-case"):
        load_pack(p)


def test_history_needs_both_validity_bounds(tmp_path):
    p = tmp_path / "ZZ.yaml"
    p.write_text(
        "jurisdiction: ZZ\nname: Test\n"
        "patent:\n  term: { years: 20, from: filing_date, cite: c, in_force_from: 2000-01-01 }\n"
        "history:\n  patent.term:\n    - value: { years: 17 }\n      in_force_from: 1990-01-01\n"
        "      cite: old\n",
        encoding="utf-8")
    with pytest.raises(PackError, match="in_force_until"):
        load_pack(p)


# -- temporal resolution --------------------------------------------------------------

def test_as_of_resolves_the_rule_then_in_force(atlas):
    us = atlas["US"]
    assert us.get("patent.filing_system", as_of=dt.date(2026, 1, 1)).value == "first_to_file"
    assert us.get("patent.filing_system", as_of=dt.date(2010, 1, 1)).value == "first_to_invent"
    # The AIA boundary: 16 March 2013.
    assert us.get("patent.filing_system", as_of=dt.date(2013, 3, 15)).value == "first_to_invent"
    assert us.get("patent.filing_system", as_of=dt.date(2013, 3, 16)).value == "first_to_file"


def test_as_of_resolves_exhaustion_across_lexmark(atlas):
    us = atlas["US"]
    assert us.get("patent.exhaustion", as_of=dt.date(2017, 5, 29)).value == "national"
    assert us.get("patent.exhaustion", as_of=dt.date(2017, 5, 30)).value == "international"


def test_as_of_resolves_cn_design_term_across_the_2020_amendment(atlas):
    cn = atlas["CN"]
    assert cn.get("registered_design.term", as_of=dt.date(2021, 5, 31)).value["years"] == 10
    assert cn.get("registered_design.term", as_of=dt.date(2021, 6, 1)).value["years"] == 15


def test_as_of_resolves_superseded_statute(atlas):
    sg = atlas["SG"]
    assert "2021" in sg.get("copyright.statute").value["name"]
    old = sg.get("copyright.statute", as_of=dt.date(2010, 1, 1))
    assert "1987" in old.value["name"]


def test_date_before_any_version_is_not_recorded(atlas):
    with pytest.raises(NotRecordedError, match="no version in force"):
        atlas["SG"].get("copyright.statute", as_of=dt.date(1900, 1, 1))


# -- pending: adopted but not yet in force ---------------------------------------------

def test_pending_resolves_for_dates_on_or_after_commencement(atlas):
    """China's fifth Trademark Law amendment cuts the opposition window from 3 months to 2
    with effect from 1 January 2027. It was adopted on 26 June 2026, so the change is law
    but not yet in force, and both answers must be available by date."""
    cn = atlas["CN"]
    before = cn.get("trade_mark.opposition", as_of=dt.date(2026, 12, 31))
    after = cn.get("trade_mark.opposition", as_of=dt.date(2027, 1, 1))
    assert before.value["window_months"] == 3
    assert after.value["window_months"] == 2
    assert "第33条" in before.cite.text
    assert "第36条" in after.cite.text


def test_pending_records_adoption_separately_from_commencement(atlas):
    """The gap between adoption and commencement is load-bearing for advice: an applicant
    filing in December 2026 is already deciding against the 2027 rules."""
    f = atlas["CN"].get("trade_mark.opposition", as_of=dt.date(2027, 6, 1))
    assert f.adopted == dt.date(2026, 6, 26)
    assert f.in_force_from == dt.date(2027, 1, 1)
    assert f.adopted < f.in_force_from


def test_renumbering_alone_is_still_recorded(atlas):
    """Where the amendment only renumbers, the value is unchanged but the citation moves.
    A pleading citing the old article after commencement cites a repealed numbering."""
    cn = atlas["CN"]
    old = cn.get("trade_mark.term", as_of=dt.date(2026, 6, 1))
    new = cn.get("trade_mark.term", as_of=dt.date(2027, 6, 1))
    assert old.value["years"] == new.value["years"] == 10
    assert "第39-40条" in old.cite.text
    assert "第43-44条" in new.cite.text


def test_pending_entry_without_adopted_is_rejected(tmp_path):
    p = tmp_path / "ZZ.yaml"
    p.write_text(
        "jurisdiction: ZZ\nname: Test\noffice: ZZO\n"
        "defaults: { checked: 2026-09-01 }\n"
        "trade_mark:\n  term: { years: 10, from: filing_date, cite: c }\n"
        "pending:\n  trade_mark.term:\n"
        "    - value: { years: 15 }\n      cite: new\n      in_force_from: 2027-01-01\n",
        encoding="utf-8")
    with pytest.raises(PackError, match="need `adopted`"):
        load_pack(p)


def test_pending_entry_without_commencement_is_rejected(tmp_path):
    p = tmp_path / "ZZ.yaml"
    p.write_text(
        "jurisdiction: ZZ\nname: Test\noffice: ZZO\n"
        "defaults: { checked: 2026-09-01 }\n"
        "trade_mark:\n  term: { years: 10, from: filing_date, cite: c }\n"
        "pending:\n  trade_mark.term:\n"
        "    - value: { years: 15 }\n      cite: new\n      adopted: 2026-06-26\n",
        encoding="utf-8")
    with pytest.raises(PackError, match="need `in_force_from`"):
        load_pack(p)


def test_commencement_before_adoption_is_a_lint_error(tmp_path):
    from ipatlas.core.lint import errors, lint_pack
    p = tmp_path / "ZZ.yaml"
    p.write_text(
        "jurisdiction: ZZ\nname: Test\noffice: ZZO\n"
        "defaults: { checked: 2026-09-01 }\n"
        "trade_mark:\n"
        "  term: { years: 10, from: filing_date, cite: c, in_force_until: 2026-12-31 }\n"
        "pending:\n  trade_mark.term:\n"
        "    - value: { years: 15 }\n      cite: new\n      adopted: 2027-06-01\n"
        "      in_force_from: 2027-01-01\n",
        encoding="utf-8")
    out = lint_pack(load_pack(p), as_of=dt.date(2026, 9, 12))
    assert any("cannot commence before it is adopted" in f.message for f in errors(out))
