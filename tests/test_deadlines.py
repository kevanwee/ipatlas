"""Deadline engine. Every expected date is hand-derived; the derivation is in the comment.

If a test here fails after an engine change, assume the engine is wrong until proven
otherwise.
"""

import datetime as dt

import pytest

from ipatlas import (
    CalendarDataMissingError,
    NotRecordedError,
    load_atlas,
    load_offices,
    load_treaty_pack,
)
from ipatlas.deadlines import (
    madrid_refusal_deadline,
    opposition_deadline,
    pct_national_phase,
    priority_deadline,
)
from ipatlas.deadlines.engine import _add_months


@pytest.fixture(scope="module")
def atlas():
    return load_atlas()


@pytest.fixture(scope="module")
def offices():
    return load_offices()


@pytest.fixture(scope="module")
def paris():
    return load_treaty_pack("paris")


@pytest.fixture(scope="module")
def pct():
    return load_treaty_pack("pct")


@pytest.fixture(scope="module")
def madrid():
    return load_treaty_pack("madrid")


# -- month arithmetic ------------------------------------------------------------------

def test_corresponding_date_arithmetic():
    assert _add_months(dt.date(2026, 3, 13), 6) == (dt.date(2026, 9, 13), False)
    assert _add_months(dt.date(2024, 9, 1), 30) == (dt.date(2027, 3, 1), False)
    # 31 August + 6 months = 28 February (no 31st), clamped and flagged
    assert _add_months(dt.date(2026, 8, 31), 6) == (dt.date(2027, 2, 28), True)
    # leap year target keeps the 29th
    assert _add_months(dt.date(2023, 8, 29), 6) == (dt.date(2024, 2, 29), False)
    assert _add_months(dt.date(2026, 12, 15), 12) == (dt.date(2027, 12, 15), False)


# -- offices load ----------------------------------------------------------------------

def test_offices_load(offices):
    assert offices.codes == ["CNIPA", "EPO", "EUIPO", "IPOS", "USPTO", "WIPO"]
    assert offices.for_jurisdiction("SG").code == "IPOS"
    assert offices.for_jurisdiction("us").code == "USPTO"
    assert offices["WIPO"].jurisdiction is None


def test_office_closure_detection(offices):
    ipos = offices["IPOS"]
    assert ipos.is_open(dt.date(2026, 3, 2))  # Monday
    assert not ipos.is_open(dt.date(2026, 4, 3))  # Good Friday
    assert ipos.why_closed(dt.date(2026, 4, 3)) == "office closed (Good Friday)"
    assert ipos.why_closed(dt.date(2026, 3, 7)) == "Saturday"
    assert ipos.why_closed(dt.date(2026, 3, 2)) is None


def test_uspto_uses_federal_holidays(offices):
    uspto = offices["USPTO"]
    # 4 July 2026 is a Saturday, observed Friday 3 July.
    assert not uspto.is_open(dt.date(2026, 7, 3))
    assert not uspto.is_open(dt.date(2026, 11, 26))  # Thanksgiving
    assert uspto.is_open(dt.date(2026, 11, 27))  # the Friday after is not a federal holiday


def test_calendar_refuses_uncovered_year(offices):
    with pytest.raises(CalendarDataMissingError, match="no closure data for 2031"):
        offices["IPOS"].is_open(dt.date(2031, 6, 1))


def test_next_open_skips_a_holiday_block(offices):
    # CNIPA National Day block 1-7 Oct 2026; 8 Oct is a Thursday.
    assert offices["CNIPA"].next_open(dt.date(2026, 10, 1)) == dt.date(2026, 10, 8)


# -- Paris priority --------------------------------------------------------------------

def test_tm_priority_six_months_rolls_off_a_sunday(atlas, offices, paris):
    # 13 Mar 2026 + 6 months = Sun 13 Sep 2026 -> Mon 14 Sep
    d = priority_deadline(atlas, offices, "trade_mark", dt.date(2026, 3, 13),
                          target="CN", treaty=paris)
    assert d.date == dt.date(2026, 9, 14)
    assert d.office == "CNIPA"
    assert d.source.months == 6
    assert any("Rolled forward" in line for line in d.trace)
    assert any("Art 4C(2)" in line for line in d.trace)


def test_patent_priority_is_twelve_months(atlas, offices, paris):
    d = priority_deadline(atlas, offices, "patent", dt.date(2025, 6, 10),
                          target="US", treaty=paris)
    assert d.source.months == 12
    assert d.date == dt.date(2026, 6, 10)  # Wednesday, USPTO open


def test_priority_falls_back_to_the_treaty_when_no_target(atlas, offices, paris):
    d = priority_deadline(atlas, offices, "trade_mark", dt.date(2026, 3, 13), treaty=paris)
    assert d.source.origin == "treaty paris"
    assert d.office == "WIPO"


def test_priority_without_a_period_refuses(atlas, offices):
    with pytest.raises(NotRecordedError, match="no priority period"):
        priority_deadline(atlas, offices, "trade_secret", dt.date(2026, 3, 13), target="SG")


# -- PCT -------------------------------------------------------------------------------

def test_pct_national_phase_thirty_months(atlas, offices, pct):
    # Priority 1 Sep 2024 + 30 months = 1 Mar 2027 (Monday, IPOS open)
    d = pct_national_phase(atlas, offices, "SG", dt.date(2024, 9, 1), treaty=pct)
    assert d.date == dt.date(2027, 3, 1)
    assert d.source.months == 30
    assert d.source.origin == "pack SG:patent.pct"


def test_pct_uses_the_office_period_when_longer(atlas, offices, pct, tmp_path):
    """A designated Office allowing 31 months must override the Treaty's 30."""
    import yaml

    from ipatlas import load_pack
    raw = yaml.safe_load((atlas["SG"].path).read_text(encoding="utf-8"))
    raw["patent"]["pct"]["national_phase_months"] = 31
    raw["jurisdiction"] = "SG"
    p = tmp_path / "SG.yaml"
    p.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    from ipatlas.core.pack import Atlas
    alt = Atlas({"SG": load_pack(p)})
    d = pct_national_phase(alt, offices, "SG", dt.date(2024, 9, 1), treaty=pct)
    assert d.date == dt.date(2027, 4, 1)
    assert any("longer than the Treaty default of 30" in line for line in d.trace)


# -- opposition ------------------------------------------------------------------------

def test_us_opposition_is_thirty_days_not_months(atlas, offices):
    # 1 Jun 2026 + 30 days = 1 Jul 2026 (Wednesday)
    d = opposition_deadline(atlas, offices, "trade_mark", "US", dt.date(2026, 6, 1))
    assert d.date == dt.date(2026, 7, 1)
    assert d.source.days == 30 and d.source.months is None
    assert any("extendable by up to 3 months" in line for line in d.trace)


def test_sg_opposition_is_two_months(atlas, offices):
    d = opposition_deadline(atlas, offices, "trade_mark", "SG", dt.date(2026, 6, 1))
    assert d.date == dt.date(2026, 8, 1) or d.date == dt.date(2026, 8, 3)
    # 1 Aug 2026 is a Saturday, so it must roll to Monday 3 Aug.
    assert d.date == dt.date(2026, 8, 3)
    assert any("Saturday" in line for line in d.trace)


def test_cn_opposition_is_three_months_and_not_extendable(atlas, offices):
    d = opposition_deadline(atlas, offices, "trade_mark", "CN", dt.date(2026, 6, 1))
    assert d.date == dt.date(2026, 9, 1)
    assert any("NOT extendable" in line for line in d.trace)


def test_opposition_not_recorded_refuses(atlas, offices):
    with pytest.raises(NotRecordedError, match="window_months"):
        opposition_deadline(atlas, offices, "patent", "SG", dt.date(2026, 6, 1))


# -- Madrid ----------------------------------------------------------------------------

def test_madrid_refusal_window_eighteen_months(atlas, offices, madrid):
    # All three packs declare the 18-month window. 1 Mar 2026 + 18 = 1 Sep 2027 (Wednesday)
    d = madrid_refusal_deadline(atlas, offices, "SG", dt.date(2026, 3, 1), treaty=madrid)
    assert d.source.months == 18
    assert d.date == dt.date(2027, 9, 1)
    assert any("Art 5(2)(c)" in line for line in d.trace)


def test_madrid_refusal_uses_the_designated_office_calendar(atlas, offices, madrid):
    """The refusal is notified BY the designated Office, so its calendar governs, not WIPO's."""
    d = madrid_refusal_deadline(atlas, offices, "SG", dt.date(2026, 3, 1), treaty=madrid)
    assert d.office == "IPOS"
    assert any("IPOS closure data" in line for line in d.trace)
    assert not any("WIPO" in line for line in d.trace)


def test_madrid_refusal_for_cn_refuses_for_want_of_2027_closure_data(atlas, offices, madrid):
    """An honest coverage gap, not a bug.

    An 18-month window from any 2026 notification lands in 2027, and the CNIPA pack has no
    2027 closure data (Chinese holidays are set annually by State Council notice and include
    compensating working weekends). The engine must refuse rather than assume the office was
    open. Padding the pack with guessed lunar dates would be worse than this failure.
    """
    with pytest.raises(CalendarDataMissingError, match="CNIPA has no closure data for 2027"):
        madrid_refusal_deadline(atlas, offices, "CN", dt.date(2026, 4, 1), treaty=madrid)


# -- traces and provenance -------------------------------------------------------------

def test_every_deadline_warns_when_the_period_is_unverified(atlas, offices, paris):
    d = priority_deadline(atlas, offices, "trade_mark", dt.date(2026, 3, 13),
                          target="SG", treaty=paris)
    assert d.warnings and "unverified" in d.warnings[0]


def test_trace_carries_the_closure_data_provenance(atlas, offices, paris):
    d = priority_deadline(atlas, offices, "trade_mark", dt.date(2026, 3, 13),
                          target="SG", treaty=paris)
    assert any("IPOS closure data 2026" in line for line in d.trace)
    assert any(line.startswith("DEADLINE:") for line in d.trace)


def test_provenance_does_not_demand_data_for_the_trigger_year(atlas, offices, pct):
    """A 2024 priority date must not require 2024 closure data: the computation never
    asks whether the office was open in 2024, only on the computed expiry."""
    d = pct_national_phase(atlas, offices, "SG", dt.date(2024, 9, 1), treaty=pct)
    assert d.date == dt.date(2027, 3, 1)
    assert not any("2024" in line for line in d.trace if "closure data" in line)


def test_to_dict_shape(atlas, offices, paris):
    d = priority_deadline(atlas, offices, "trade_mark", dt.date(2026, 3, 13),
                          target="SG", treaty=paris).to_dict()
    assert d["deadline"] == "2026-09-14"
    assert d["office"] == "IPOS"
    assert d["verified"] is False
    assert "TMA 1998, s 10" in d["cite"]
