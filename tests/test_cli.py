from ipatlas.cli import main


def test_jurisdictions(capsys):
    assert main(["jurisdictions"]) == 0
    out = capsys.readouterr().out
    assert "SG  Singapore" in out and "CNIPA" in out


def test_compare_markdown(capsys):
    assert main(["compare", "trade_mark", "SG", "US", "CN", "-a", "use_requirement"]) == 0
    out = capsys.readouterr().out
    assert "5 years of non-use" in out and "3 years of non-use" in out


def test_compare_unknown_jurisdiction_exits_2(capsys):
    assert main(["compare", "trade_mark", "SG", "ZZ"]) == 2
    assert "CN, SG, US" in capsys.readouterr().err


def test_brief(capsys):
    assert main(["brief", "CN", "patent"]) == 0
    out = capsys.readouterr().out
    assert "China National Intellectual Property Administration" in out
    assert "专利法" in out  # CJK must survive the console


def test_fact_text_and_json(capsys):
    assert main(["fact", "US", "trade_mark.term"]) == 0
    assert "10 years from registration date" in capsys.readouterr().out
    assert main(["fact", "US", "trade_mark.term", "--format", "json"]) == 0
    assert '"verified": false' in capsys.readouterr().out


def test_fact_not_recorded_exits_2(capsys):
    assert main(["fact", "SG", "trade_mark.nope"]) == 2
    assert "not recorded" in capsys.readouterr().err


def test_as_of_flag_changes_the_answer(capsys):
    assert main(["--as-of", "2010-01-01", "fact", "US", "patent.filing_system"]) == 0
    assert "first to invent" in capsys.readouterr().out
    assert main(["fact", "US", "patent.filing_system"]) == 0
    assert "first to file" in capsys.readouterr().out


def test_lint_passes_on_bundled_data(capsys):
    assert main(["lint"]) == 0
    assert "0 error(s)" in capsys.readouterr().err


def test_attributes_listing(capsys):
    assert main(["attributes", "trade_mark"]) == 0
    out = capsys.readouterr().out
    assert "default comparison set for trade_mark" in out


# -- Phase 1 commands ------------------------------------------------------------------

def test_offices_listing(capsys):
    assert main(["offices"]) == 0
    out = capsys.readouterr().out
    # The listing must surface provenance: a projected year behaves differently.
    assert "IPOS" in out and "2026:official, 2027:projected" in out
    assert "USPTO" in out and "2026:derived" in out


def test_deadline_priority(capsys):
    assert main(["deadline", "priority", "CN", "2026-03-13", "--right", "trade_mark"]) == 0
    out = capsys.readouterr().out
    assert "DEADLINE: 2026-09-14" in out
    assert "Art 4C(2)" in out


def test_deadline_opposition_us_is_days(capsys):
    assert main(["deadline", "opposition", "US", "2026-06-01"]) == 0
    assert "DEADLINE: 2026-07-01" in capsys.readouterr().out


def test_deadline_pct_refuses_on_a_projected_calendar(capsys):
    """Exit 3: the deadline lands in IPOS 2027, which is a reconstruction."""
    assert main(["deadline", "pct", "SG", "2024-09-01"]) == 3
    assert "PROJECTED" in capsys.readouterr().err


def test_deadline_pct_json_with_allow_projected(capsys):
    assert main(["--json", "--allow-projected", "deadline", "pct", "SG", "2024-09-01"]) == 0
    import json
    d = json.loads(capsys.readouterr().out)
    assert d["deadline"] == "2027-03-01" and d["office"] == "IPOS"
    assert any("provenance=projected" in line for line in d["trace"])


def test_deadline_missing_calendar_exits_3(capsys):
    assert main(["deadline", "madrid-refusal", "CN", "2026-04-01"]) == 3
    assert "CNIPA has no closure data for 2027" in capsys.readouterr().err


def test_term_command(capsys):
    assert main(["term", "SG", "trade_mark", "--date", "filing_date=2020-03-01"]) == 0
    out = capsys.readouterr().out
    assert "+ 10 years = 2030-03-01" in out
    assert "renewal 1 due 2030-03-01" in out


def test_term_wrong_base_date_exits_2(capsys):
    assert main(["term", "US", "trade_mark", "--date", "filing_date=2020-03-01"]) == 2
    assert "runs from registration_date" in capsys.readouterr().err


def test_copyright_term_command(capsys):
    assert main(["copyright-term", "CN", "literary_dramatic_musical_artistic",
                 "--date", "author_death=2000-06-15"]) == 0
    assert "COPYRIGHT EXPIRES: 2050-12-31" in capsys.readouterr().out


def test_routes_command(capsys):
    assert main(["routes", "trade_mark", "SG", "US", "CN"]) == 0
    out = capsys.readouterr().out
    assert "Madrid international registration" in out
    assert "does not recommend a route" in out
