"""Jurisdiction packs: load, address by dotted path, resolve as at a date.

A pack is one YAML file per jurisdiction. The loader walks it into a flat map of
dotted path -> Fact, keeping the `history:` block separate so that a query with an `as_of`
in the past gets the rule that was then in force rather than today's.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .fact import PROVENANCE_KEYS, Fact, is_fact_mapping, parse_fact

_PKG_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR = _PKG_ROOT / "data"
JURISDICTIONS_DIR = DATA_DIR / "jurisdictions"
TREATIES_DIR = DATA_DIR / "treaties"

# Top-level keys that are metadata about the pack, not legal facts.
META_KEYS = frozenset({
    "jurisdiction", "name", "office", "office_name", "languages", "legal_system",
    "currency", "defaults", "history",
})

RIGHTS = (
    "trade_mark", "patent", "utility_model", "registered_design", "copyright",
    "trade_secret", "geographical_indication", "plant_variety",
)


class PackError(ValueError):
    """Structural problem with a pack that prevents loading."""


class NotRecordedError(LookupError):
    """The attribute is not present in the pack. Never substitute a default."""


@dataclass
class Pack:
    jurisdiction: str
    name: str
    office: str | None
    office_name: str | None
    path: Path
    meta: dict[str, Any] = field(default_factory=dict)
    facts: dict[str, Fact] = field(default_factory=dict)
    history: dict[str, list[Fact]] = field(default_factory=dict)

    # -- addressing -------------------------------------------------------------------

    def get(self, attr: str, *, as_of: dt.date | None = None) -> Fact:
        """Fact at a dotted path, as in force on `as_of`. Raises NotRecordedError if absent."""
        when = as_of or dt.date.today()
        current = self.facts.get(attr)
        if current is not None and current.in_force_on(when):
            return current
        for old in self.history.get(attr, []):
            if old.in_force_on(when):
                return old
        if current is None and attr not in self.history:
            raise NotRecordedError(f"{self.jurisdiction}: {attr!r} is not recorded")
        raise NotRecordedError(
            f"{self.jurisdiction}: {attr!r} has no version in force on {when.isoformat()}"
        )

    def try_get(self, attr: str, *, as_of: dt.date | None = None) -> Fact | None:
        try:
            return self.get(attr, as_of=as_of)
        except NotRecordedError:
            return None

    def subvalue(self, attr: str, key: str, *,
                 as_of: dt.date | None = None) -> tuple[object | None, Fact | None]:
        """Read one key of a fact, whichever shape the pack used.

        A flat leaf mapping such as

            madrid: { designation_accepted: true, refusal_window_months: 18, cite: ... }

        loads as ONE fact whose value is a dict, so `madrid.designation_accepted` is not a
        path. A pack that instead nests each key as its own cited fact produces real
        sub-paths. Both spellings are legitimate, so callers must not assume either:
        `subvalue("trade_mark.madrid", "designation_accepted")` works for both.

        Returns (value, owning fact), or (None, None) when not recorded.
        """
        nested = self.try_get(f"{attr}.{key}", as_of=as_of)
        if nested is not None:
            return nested.value, nested
        parent = self.try_get(attr, as_of=as_of)
        if parent is not None and isinstance(parent.value, dict) and key in parent.value:
            return parent.value[key], parent
        if parent is not None and key in parent.extra:
            return parent.extra[key], parent
        return None, None

    def has_right(self, right: str) -> bool:
        """False when the pack records the right as unavailable (e.g. utility models in SG)."""
        f = self.try_get(f"{right}.available")
        if f is not None and f.value is False:
            return False
        f = self.try_get(right)
        if f is not None and isinstance(f.value, dict) and f.value.get("available") is False:
            return False
        return any(k == right or k.startswith(f"{right}.") for k in self.facts)

    def attributes(self, prefix: str = "") -> list[str]:
        keys = sorted(self.facts)
        return [k for k in keys if k.startswith(prefix)] if prefix else keys

    @property
    def rights(self) -> list[str]:
        return [r for r in RIGHTS if self.has_right(r)]


# -- loading ---------------------------------------------------------------------------


def _walk(node: Any, *, prefix: str, jurisdiction: str, defaults: dict,
          out: dict[str, Fact]) -> None:
    if not isinstance(node, dict) or is_fact_mapping(node):
        out[prefix] = parse_fact(node, path=prefix, jurisdiction=jurisdiction, defaults=defaults)
        return
    # A group: recurse into non-provenance children. Group-level notes attach to the group
    # as a value-less fact so they are not lost.
    group_notes = node.get("notes")
    if group_notes:
        fact = parse_fact({"notes": group_notes}, path=prefix, jurisdiction=jurisdiction,
                          defaults=defaults)
        fact.is_group_note = True
        out[prefix] = fact
    for key, child in node.items():
        if key in PROVENANCE_KEYS:
            continue
        _walk(child, prefix=f"{prefix}.{key}" if prefix else key,
              jurisdiction=jurisdiction, defaults=defaults, out=out)


def _load_history(raw: Any, *, jurisdiction: str, defaults: dict) -> dict[str, list[Fact]]:
    out: dict[str, list[Fact]] = {}
    if not raw:
        return out
    if not isinstance(raw, dict):
        raise PackError(f"{jurisdiction}: `history` must be a mapping of path -> versions")
    for path, versions in raw.items():
        if not isinstance(versions, list):
            raise PackError(f"{jurisdiction}: history.{path} must be a list of past versions")
        facts = []
        for v in versions:
            f = parse_fact(v, path=path, jurisdiction=jurisdiction, defaults=defaults)
            if f.in_force_from is None or f.in_force_until is None:
                raise PackError(
                    f"{jurisdiction}: history.{path} entries need in_force_from and "
                    "in_force_until so a query can resolve which version applied"
                )
            facts.append(f)
        out[path] = sorted(facts, key=lambda f: f.in_force_from)
    return out


def load_pack(path: str | Path) -> Pack:
    path = Path(path)
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or "jurisdiction" not in raw:
        raise PackError(f"{path}: missing top-level `jurisdiction`")
    code = str(raw["jurisdiction"])
    if code != code.upper():
        raise PackError(f"{path}: jurisdiction code {code!r} must be upper-case ISO 3166-1 alpha-2")
    if path.stem != code:
        raise PackError(f"{path}: filename must match the jurisdiction code ({code}.yaml)")

    defaults = raw.get("defaults") or {}
    facts: dict[str, Fact] = {}
    for key, node in raw.items():
        if key in META_KEYS:
            continue
        _walk(node, prefix=key, jurisdiction=code, defaults=defaults, out=facts)

    return Pack(
        jurisdiction=code,
        name=str(raw.get("name", code)),
        office=raw.get("office"),
        office_name=raw.get("office_name"),
        path=path,
        meta={k: raw.get(k) for k in META_KEYS if k in raw and k != "history"},
        facts=facts,
        history=_load_history(raw.get("history"), jurisdiction=code, defaults=defaults),
    )


@dataclass
class Atlas:
    """Every loaded pack, addressed by jurisdiction code."""

    packs: dict[str, Pack] = field(default_factory=dict)

    def __getitem__(self, code: str) -> Pack:
        try:
            return self.packs[code.upper()]
        except KeyError:
            known = ", ".join(sorted(self.packs)) or "none"
            raise NotRecordedError(
                f"no pack for {code!r}; loaded jurisdictions: {known}"
            ) from None

    def __contains__(self, code: str) -> bool:
        return code.upper() in self.packs

    @property
    def codes(self) -> list[str]:
        return sorted(self.packs)


def load_atlas(directory: str | Path | None = None) -> Atlas:
    directory = Path(directory or JURISDICTIONS_DIR)
    packs = {}
    for p in sorted(directory.glob("*.yaml")):
        pack = load_pack(p)
        if pack.jurisdiction in packs:
            raise PackError(f"duplicate jurisdiction pack {pack.jurisdiction}")
        packs[pack.jurisdiction] = pack
    return Atlas(packs)


def load_treaty(name: str, directory: str | Path | None = None) -> dict:
    directory = Path(directory or TREATIES_DIR)
    return yaml.safe_load((directory / f"{name}.yaml").read_text(encoding="utf-8"))
