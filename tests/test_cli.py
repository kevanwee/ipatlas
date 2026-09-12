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
