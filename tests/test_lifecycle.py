import datetime as dt

import pytest

from ipatlas import NotRecordedError, copyright_term, load_atlas, renewal_schedule, term_expiry
from ipatlas.lifecycle.term import MissingDateError


@pytest.fixture(scope="module")
def atlas():
    return load_atlas()


# -- registered rights -----------------------------------------------------------------

def test_sg_tm_term_runs_from_filing(atlas):
    r = term_expiry(atlas, "trade_mark", "SG", {"filing_date": dt.date(2020, 3, 1)})
    assert r.base == "filing_date"
    assert r.expiry == dt.date(2030, 3, 1)
    assert r.renewable is True


def test_us_tm_term_refuses_a_filing_date_because_it_runs_from_registration(atlas):
    """The divergence that matters: supplying the wrong date must refuse, never approximate."""
    with pytest.raises(MissingDateError, match="runs from registration_date"):
        term_expiry(atlas, "trade_mark", "US", {"filing_date": dt.date(2020, 3, 1)})
    r = term_expiry(atlas, "trade_mark", "US", {"registration_date": dt.date(2021, 5, 4)})
    assert r.expiry == dt.date(2031, 5, 4)


def test_patent_term_twenty_years_from_filing(atlas):
    for j in ("SG", "US", "CN"):
        r = term_expiry(atlas, "patent", j, {"filing_date": dt.date(2020, 1, 15)})
        assert r.expiry == dt.date(2040, 1, 15), j
        assert r.renewable is False


def test_leap_day_filing_clamps(atlas):
    r = term_expiry(atlas, "patent", "SG", {"filing_date": dt.date(2024, 2, 29)})
    assert r.expiry == dt.date(2044, 2, 29)  # 2044 is a leap year
    r = term_expiry(atlas, "trade_mark", "SG", {"filing_date": dt.date(2024, 2, 29)})
    assert r.expiry == dt.date(2034, 2, 28)  # 2034 is not
    assert any("29 February" in line for line in r.trace)


def test_cn_design_term_depends_on_the_as_of_date(atlas):
    dates = {"filing_date": dt.date(2020, 6, 1)}
    assert term_expiry(atlas, "registered_design", "CN", dates,
                       as_of=dt.date(2021, 1, 1)).expiry == dt.date(2030, 6, 1)
    assert term_expiry(atlas, "registered_design", "CN", dates,
                       as_of=dt.date(2026, 1, 1)).expiry == dt.date(2035, 6, 1)


def test_us_design_patent_runs_from_grant_and_is_not_renewable(atlas):
    r = term_expiry(atlas, "registered_design", "US", {"grant_date": dt.date(2024, 5, 1)},
                    renewals=2)
    assert r.base == "grant_date"
    assert r.expiry == dt.date(2039, 5, 1)
    assert r.renewable is False
    assert r.renewals == []
    assert any("not renewable" in w for w in r.warnings)


# -- renewals --------------------------------------------------------------------------

def test_sg_tm_renewal_schedule_with_grace_and_restoration(atlas):
    r = renewal_schedule(atlas, "trade_mark", "SG", {"filing_date": dt.date(2020, 3, 1)},
                         count=2)
    assert [w.due for w in r.renewals] == [dt.date(2030, 3, 1), dt.date(2040, 3, 1)]
    first = r.renewals[0]
    assert first.grace_until == dt.date(2030, 9, 1)          # 6 months
    # Restoration runs 6 months from the date the registry REMOVES the mark (Trade Marks
    # Rules r 53(1)), not from the grace expiry. Grace expiry is the engine proxy, and the
    # trace must say the actual removal date governs.
    assert first.restoration_until == dt.date(2031, 3, 1)
    assert any("actual removal date governs" in line for line in r.trace)


def test_cn_tm_renewal_window_opens_twelve_months_before_expiry(atlas):
    r = renewal_schedule(atlas, "trade_mark", "CN",
                         {"registration_date": dt.date(2020, 3, 1)}, count=1)
    w = r.renewals[0]
    assert w.due == dt.date(2030, 3, 1)
    assert w.window_opens == dt.date(2029, 3, 1)
    assert w.grace_until == dt.date(2030, 9, 1)


def test_registered_design_stops_at_the_maximum_duration(atlas):
    r = renewal_schedule(atlas, "registered_design", "SG",
                         {"filing_date": dt.date(2020, 1, 1)}, count=5)
    assert r.max_expiry == dt.date(2035, 1, 1)  # 15-year maximum
    assert all(w.due <= r.max_expiry for w in r.renewals)
    assert any("maximum duration" in line for line in r.trace)


def test_term_not_recorded_refuses(atlas):
    with pytest.raises(NotRecordedError, match="term is not recorded"):
        term_expiry(atlas, "trade_secret", "SG", {"filing_date": dt.date(2020, 1, 1)})


# -- copyright -------------------------------------------------------------------------

def test_sg_copyright_runs_to_the_end_of_the_seventieth_year(atlas):
    """s 114(1)(a) is '70 years after the END OF THE YEAR in which the author dies', so the
    term expires on 31 December, not on the anniversary."""
    c = copyright_term(atlas, "SG", "literary_dramatic_musical_artistic",
                       {"author_death": dt.date(2000, 6, 15)})
    assert c.expiry == dt.date(2070, 12, 31)
    assert any("calendar year" in line for line in c.trace)


def test_sg_copyright_where_the_author_is_not_identified(atlas):
    """The 2021 Act's operative trigger is whether the author is IDENTIFIED, not anonymity."""
    c = copyright_term(atlas, "SG", "author_not_identified",
                       {"publication": dt.date(2000, 6, 15)})
    assert c.expiry == dt.date(2070, 12, 31)


def test_cn_copyright_is_fifty_years_to_the_year_end(atlas):
    """CN runs to 31 December of the fiftieth year, and the pack note says so."""
    c = copyright_term(atlas, "CN", "literary_dramatic_musical_artistic",
                       {"author_death": dt.date(2000, 6, 15)})
    assert c.expiry == dt.date(2050, 12, 31)
    assert any("calendar year" in line for line in c.trace)


def test_us_works_made_for_hire_takes_the_earlier_limb(atlas):
    c = copyright_term(atlas, "US", "works_made_for_hire",
                       {"publication": dt.date(2000, 1, 1), "creation": dt.date(1990, 1, 1)})
    assert c.expiry == dt.date(2095, 1, 1)  # pub+95 = 2095 beats creation+120 = 2110
    assert any("whichever is earlier" in line for line in c.trace)


def test_us_works_made_for_hire_when_unpublished_for_long(atlas):
    # Created 1990, published 2060: creation+120 = 2110 beats publication+95 = 2155
    c = copyright_term(atlas, "US", "works_made_for_hire",
                       {"publication": dt.date(2060, 1, 1), "creation": dt.date(1990, 1, 1)})
    assert c.expiry == dt.date(2110, 1, 1)


def test_copyright_missing_base_date_refuses(atlas):
    with pytest.raises(MissingDateError, match="runs from author_death"):
        copyright_term(atlas, "SG", "literary_dramatic_musical_artistic",
                       {"publication": dt.date(2000, 1, 1)})


def test_unknown_category_lists_what_is_recorded(atlas):
    with pytest.raises(NotRecordedError, match="Categories recorded"):
        copyright_term(atlas, "SG", "software", {"author_death": dt.date(2000, 1, 1)})


def test_jurisdictions_diverge_on_copyright_term(atlas):
    """Same author, three answers. The reason the dataset exists."""
    death = {"author_death": dt.date(2000, 6, 15)}
    sg = copyright_term(atlas, "SG", "literary_dramatic_musical_artistic", death).expiry
    us = copyright_term(atlas, "US", "literary_dramatic_musical_artistic", death).expiry
    cn = copyright_term(atlas, "CN", "literary_dramatic_musical_artistic", death).expiry
    # All three are a flat "+70" or "+50" on paper, yet all three give a different date:
    # SG and CN run to the end of the calendar year, the US runs to the anniversary.
    assert sg == dt.date(2070, 12, 31)
    assert us == dt.date(2070, 6, 15)
    assert cn == dt.date(2050, 12, 31)
    assert cn < us < sg
