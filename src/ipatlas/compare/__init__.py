"""Comparison across jurisdictions, and the one-page country brief.

Both read the same packs. Both show citations and verification flags in their output: a
clean table whose cells cannot be checked is worse than no table at all.
"""

from .table import DEFAULT_ATTRIBUTES, Cell, Table, brief, compare

__all__ = ["compare", "brief", "Table", "Cell", "DEFAULT_ATTRIBUTES"]
