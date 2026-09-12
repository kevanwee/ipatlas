import datetime as dt

import pytest

from ipatlas import NotRecordedError, load_atlas, load_pack, routes


@pytest.fixture(scope="module")
def atlas():
    return load_atlas()


def _by(m):
    return {t.jurisdiction: t for t in m.targets}


def test_madrid_route_is_found_for_all_three(atlas):
    """Regression: the loader parses `trade_mark.madrid` as one flat fact, so
    `madrid.designation_accepted` is not a path. Routes must read it via subvalue()."""
    t = _by(routes(atlas, "trade_mark", ["SG", "US", "CN"]))
    for code in ("SG", "US", "CN"):
        assert t[code].treaty_routes == ["Madrid international registration"], code
        assert not t[code].national_only
        assert t[code].not_recorded == []


def test_pct_and_hague_routes(atlas):
    assert _by(routes(atlas, "patent", ["SG"]))["SG"].treaty_routes == \
        ["PCT international application"]
    assert _by(routes(atlas, "registered_design", ["CN"]))["CN"].treaty_routes == \
        ["Hague international registration"]


def test_unavailable_right_is_reported(atlas):
    t = _by(routes(atlas, "utility_model", ["SG", "US", "CN"]))
    assert not t["SG"].right_available and t["SG"].summary == "right not available"
    assert not t["US"].right_available
    assert t["CN"].right_available


def test_paris_priority_flag(atlas):
    for t in routes(atlas, "trade_mark", ["SG", "US", "CN"]).targets:
        assert t.priority_available is True


def test_traps_are_collected_from_the_packs(atlas):
    t = _by(routes(atlas, "trade_mark", ["SG", "US", "CN"]))
    us = " ".join(t["US"].traps)
    assert "first-to-use" in us
    assert "individual fee" in us           # via subvalue on the flat madrid fact
    assert "non-use vulnerability after only 3 years" in us
    cn = " ".join(t["CN"].traps)
    assert "subclass" in cn
    assert "exhaustion position is unsettled" in cn
    # SG has a 5-year non-use period, so it must NOT be flagged as short.
    assert not any("non-use vulnerability" in x for x in t["SG"].traps)


def test_national_only_when_not_a_treaty_member(tmp_path, atlas):
    """A jurisdiction outside Madrid must come back national-only, not blank."""
    import yaml
    raw = yaml.safe_load(atlas["SG"].path.read_text(encoding="utf-8"))
    raw["jurisdiction"] = "ZZ"
    raw["name"] = "Nonmemberland"
    raw["memberships"]["value"] = ["paris", "trips"]
    p = tmp_path / "ZZ.yaml"
    p.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    from ipatlas.core.pack import Atlas
    m = routes(Atlas({"ZZ": load_pack(p)}), "trade_mark", ["ZZ"])
    t = m.targets[0]
    assert t.treaty_routes == []
    assert t.national_only
    assert t.summary == "national filing only"
    assert t.priority_available is True


def test_missing_memberships_is_reported_not_assumed(tmp_path):
    p = tmp_path / "ZZ.yaml"
    p.write_text("jurisdiction: ZZ\nname: Testland\noffice: ZZO\n"
                 "defaults: { checked: 2026-09-01 }\n"
                 "trade_mark:\n  term: { years: 10, from: filing_date, cite: x }\n",
                 encoding="utf-8")
    from ipatlas.core.pack import Atlas
    t = routes(Atlas({"ZZ": load_pack(p)}), "trade_mark", ["ZZ"]).targets[0]
    assert t.treaty_routes == []
    assert any("memberships are not recorded" in x for x in t.not_recorded)
    assert t.priority_available is False


def test_unknown_right_refuses(atlas):
    with pytest.raises(NotRecordedError, match="no route treaty mapping"):
        routes(atlas, "trade_secret", ["SG"])


def test_markdown_and_dict(atlas):
    m = routes(atlas, "trade_mark", ["SG", "US", "CN"], as_of=dt.date(2026, 6, 1))
    md = m.to_markdown()
    assert "## Traps" in md
    assert "does not recommend a route" in md
    d = m.to_dict()
    assert d["as_of"] == "2026-06-01"
    assert len(d["targets"]) == 3
