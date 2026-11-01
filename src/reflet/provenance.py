"""Per-cell lineage tracking."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Provenance:
    """Lineage of a single cell: where it came from and the steps applied to it.

    `source` is the origin identifier (e.g. a file path), `source_field` is the
    field name as it appeared in the source, and `steps` is the ordered list of
    transformation descriptions applied since then (oldest first).
    """

    source: str
    source_field: str
    steps: tuple[str, ...] = field(default_factory=tuple)

    def step(self, description: str) -> Provenance:
        """Return a new Provenance with `description` appended to the step chain."""
        return Provenance(self.source, self.source_field, (*self.steps, description))

    def render(self) -> str:
        chain = " -> ".join((f"{self.source}:{self.source_field}", *self.steps))
        return chain

    def __str__(self) -> str:  # pragma: no cover - thin wrapper
        return self.render()
