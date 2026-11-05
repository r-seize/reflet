"""Pipeline builder: chains lenses in front of a source."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from functools import reduce
from typing import Any

from reflet._render import render_table
from reflet.lens import ConflictPolicy, IdentityLens, Lens
from reflet.lenses import (
    AggregateLens,
    ComputeLens,
    ConstantLens,
    FilterLens,
    JoinLens,
    MapLens,
    MergeLens,
    RenameLens,
    RowView,
    SelectLens,
    SortLens,
    SplitLens,
)
from reflet.sources import SourceBackend
from reflet.sources.csv_source import CsvSource
from reflet.sources.json_path_source import JsonPathSource
from reflet.sources.json_source import JsonSource
from reflet.sources.sqlite_source import SqliteSource
from reflet.view import Validator, View

_SQLITE_EXTENSIONS = (".sqlite", ".sqlite3", ".db")


def _backend_for(
    path: str, key: str | None, table: str | None, rows_at: str | None
) -> SourceBackend:
    if path.endswith(_SQLITE_EXTENSIONS):
        if table is None:
            raise ValueError(f"{path!r}: a SQLite source requires table=...")
        return SqliteSource(path, table, key)
    if path.endswith(".json"):
        if rows_at is not None:
            return JsonPathSource(path, rows_at, key)
        return JsonSource(path, key)
    if path.endswith(".csv"):
        if rows_at is not None:
            raise ValueError("rows_at= is only supported for JSON sources")
        return CsvSource(path, key)
    raise ValueError(
        f"unsupported source file: {path!r} (expected .csv, .json, or a SQLite file)"
    )


class Pipeline:
    """A chain of lenses to apply in front of a source backend."""

    def __init__(
        self,
        backend: SourceBackend,
        lenses: tuple[Lens, ...]                         = (),
        validators: dict[str, list[Validator]] | None    = None,
        tombstone_field: str | None                      = None,
    ) -> None:
        self.backend            = backend
        self.lenses             = lenses
        self.validators         = validators or {}
        self.tombstone_field    = tombstone_field

    def _add(self, lens: Lens) -> Pipeline:
        return Pipeline(
            self.backend, (*self.lenses, lens), self.validators, self.tombstone_field
        )

    def __repr__(self) -> str:
        lens_names = ", ".join(lens.name for lens in self.lenses) or "none"
        return f"Pipeline({self.backend.path!r}, lenses=[{lens_names}])"

    def filter(
        self, predicate: Callable[[RowView], bool], defaults: dict[str, Any] | None = None
    ) -> Pipeline:
        """`defaults` are the field values a `View.insert()`-ed row needs to
        satisfy this filter (see `FilterLens`)."""
        return self._add(FilterLens(predicate, defaults))

    def rename(self, **mapping: str) -> Pipeline:
        """`rename(customer="name")` renames source field `name` to `customer`."""
        return self._add(RenameLens(mapping))

    def select(self, *fields: str) -> Pipeline:
        return self._add(SelectLens(fields))

    def sort(self, field: str, reverse: bool = False) -> Pipeline:
        """Orders the view by `field`; write-back ignores order, keyed by rid."""
        return self._add(SortLens(field, reverse))

    def map(
        self, field: str, *, fwd: Callable[[Any], Any], bwd: Callable[[Any], Any]
    ) -> Pipeline:
        return self._add(MapLens(field, fwd, bwd))

    def cast(
        self, field: str, to: Callable[[Any], Any], back: Callable[[Any], Any]
    ) -> Pipeline:
        """Sugar for `.map()` when the transform is just a type conversion.

        `back` is required (not guessed) — e.g. `.cast("price", to=float, back=str)`
        if the source stores it as text.
        """
        return self._add(MapLens(field, to, back))

    def split(
        self,
        field: str,
        into: tuple[str, ...],
        fwd: Callable[[Any], tuple[Any, ...]],
        bwd: Callable[[tuple[Any, ...]], Any],
    ) -> Pipeline:
        """Splits one source field into several view fields (e.g. a full name
        into first/last)."""
        return self._add(SplitLens(field, into, fwd, bwd))

    def merge(
        self,
        fields: tuple[str, ...],
        into: str,
        fwd: Callable[[tuple[Any, ...]], Any],
        bwd: Callable[[Any], tuple[Any, ...]],
    ) -> Pipeline:
        """Merges several source fields into one view field — the dual of `.split()`."""
        return self._add(MergeLens(fields, into, fwd, bwd))

    def join(
        self,
        other: Pipeline,
        on: str,
        other_on: str | None    = None,
        prefix: str | None      = None,
    ) -> Pipeline:
        """Inner-joins against `other`'s rows by key. Right-hand fields are
        read-only — see `JoinLens` and the README's Join section."""
        return self._add(JoinLens(other, on, other_on, prefix))

    def constant(self, field: str, value: Any) -> Pipeline:
        return self._add(ConstantLens(field, value))

    def compute(self, field: str, fn: Callable[[RowView], Any]) -> Pipeline:
        return self._add(ComputeLens(field, fn))

    def aggregate(
        self,
        group_by: str,
        agg_field: str,
        agg_fn: Callable[[list[Any]], Any],
        source_field: str | None    = None,
        policy: ConflictPolicy      = ConflictPolicy.ERROR,
    ) -> Pipeline:
        return self._add(
            AggregateLens(group_by, agg_field, agg_fn, source_field=source_field, policy=policy)
        )

    def validate(
        self, field: str, predicate: Callable[[Any], bool], message: str | None = None
    ) -> Pipeline:
        """Reject an edit to `field` before it ever reaches the source.

        `predicate` is checked against the new value at edit time
        (`row.field = value`), not at `sync()`. On failure, raises
        `ValidationError` with `message` (or a default) plus the field's
        provenance, so the error points at where the bad value came from.
        """
        validators = {k: list(v) for k, v in self.validators.items()}
        validators.setdefault(field, []).append((predicate, message))
        return Pipeline(self.backend, self.lenses, validators, self.tombstone_field)

    def combined_lens(self) -> Lens:
        if not self.lenses:
            return IdentityLens()
        return reduce(lambda a, b: a >> b, self.lenses)

    def run(self) -> View:
        source_table    = self.backend.read()
        lens            = self.combined_lens()
        view_table      = lens.get(source_table)
        return View(
            view_table,
            source_table,
            lens,
            self.backend,
            lenses             = self.lenses,
            validators         = self.validators,
            tombstone_field    = self.tombstone_field,
        )

    def preview(self, n: int = 5) -> None:
        """Run the pipeline and print the first `n` rows as a table — a quick
        look without writing a loop."""
        print(render_table(self.run().to_dicts(), limit=n))


def Source(
    path: str,
    key: str | None                = None,
    tombstone_field: str | None    = None,
    table: str | None              = None,
    rows_at: str | None            = None,
) -> Pipeline:
    """Entry point: `rf.Source("clients.csv")` starts a pipeline over that file.

    `key` names a source field that uniquely identifies each row, so
    write-back keeps tracking the right row even if the file is reordered
    externally between a `run()` and a `sync()`. Without it, a row's identity
    is simply its position in the file.

    `tombstone_field` names an existing column to set instead of actually
    removing a row, for `View.delete(..., on_delete="tombstone")`.

    `table` names the table to read for a SQLite source (`.sqlite`/`.sqlite3`/
    `.db`); required for those, ignored otherwise.

    `rows_at` is a dotted path (e.g. `"servers"`) to the list to treat as the
    table, for a JSON file whose rows are nested inside a larger document
    rather than being the document itself.
    """
    return Pipeline(_backend_for(path, key, table, rows_at), tombstone_field=tombstone_field)


__all__: Sequence[str] = ["Pipeline", "Source"]
