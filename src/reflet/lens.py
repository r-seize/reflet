"""Core bidirectional lens abstraction, operating on tables of records."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Hashable
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any

from reflet.errors import ConflictError, ReadOnlyFieldError
from reflet.provenance import Provenance

# A row's stable identity: its position (no key given) or a key field's value.
RowKey = Hashable
# A row identifier: a single row key, or a tuple of several when a lens
# (e.g. aggregate) merges multiple source rows into one output row.
RowId = RowKey | tuple[RowKey, ...]


class ConflictPolicy(str, Enum):
    """How to resolve a write to a field shared by several source rows."""

    FIRST    = "first"
    LAST     = "last"
    ERROR    = "error"


@dataclass(frozen=True)
class Cell:
    """A single field value together with its provenance."""

    value: Any
    prov: Provenance
    readonly: bool                     = False
    conflict: ConflictPolicy | None    = None
    conflict_size: int                 = 1

    def transform(self, fn: Any, step: str, *, readonly: bool = False) -> Cell:
        return Cell(fn(self.value), self.prov.step(step), readonly=readonly)

    def require_writable(self, field: str) -> None:
        if self.readonly:
            raise ReadOnlyFieldError(field)
        if self.conflict == ConflictPolicy.ERROR:
            raise ConflictError(self.conflict_size)


@dataclass(frozen=True)
class Record:
    """A single row: its (possibly composite) identity plus its field cells."""

    rid: RowId
    fields: dict[str, Cell]

    def with_fields(self, fields: dict[str, Cell]) -> Record:
        return replace(self, fields=fields)


Table = list[Record]


class Lens(ABC):
    """A bidirectional transformation from one table shape to another.

    `get` produces the forward view; `put` takes an edited view (`a`, built by
    editing the result of `get(s)`) together with the original table `s` and
    reconstructs the updated `s`.
    """

    name: str = "lens"

    @abstractmethod
    def get(self, s: Table) -> Table: ...

    @abstractmethod
    def put(self, a: Table, s: Table) -> Table: ...

    def __rshift__(self, other: Lens) -> Lens:
        return ComposedLens(self, other)


class ComposedLens(Lens):
    """Sequential composition of two lenses: self first, then other."""

    def __init__(self, first: Lens, second: Lens) -> None:
        self.first     = first
        self.second    = second
        self.name      = f"{first.name}>>{second.name}"

    def get(self, s: Table) -> Table:
        return self.second.get(self.first.get(s))

    def put(self, a: Table, s: Table) -> Table:
        mid        = self.first.get(s)
        new_mid    = self.second.put(a, mid)
        return self.first.put(new_mid, s)


class IdentityLens(Lens):
    """The no-op lens; used when a pipeline has no transformation steps yet."""

    name = "identity"

    def get(self, s: Table) -> Table:
        return list(s)

    def put(self, a: Table, s: Table) -> Table:
        return list(a)


def index_by_rid(table: Table) -> dict[RowId, Record]:
    return {r.rid: r for r in table}
