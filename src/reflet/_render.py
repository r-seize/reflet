"""Tiny shared TSV rendering, used by `Pipeline.preview()` and the CLI."""

from __future__ import annotations


def render_table(rows: list[dict[str, object]], limit: int | None = None) -> str:
    """Render rows (as from `View.to_dicts()`) as a tab-separated table."""
    if not rows:
        return "(empty view)"
    shown = rows if limit is None else rows[:limit]
    fields = list(shown[0].keys())
    lines = ["\t".join(fields)]
    lines.extend("\t".join(str(row[f]) for f in fields) for row in shown)
    return "\n".join(lines)
