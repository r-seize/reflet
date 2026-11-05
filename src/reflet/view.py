"""View: the editable, provenance-carrying result of running a pipeline."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from reflet.errors import (
    InsertError,
    ReadOnlyFieldError,
    SourceConflictError,
    UnknownFieldError,
    UnsupportedOperationError,
    ValidationError,
)
from reflet.lens import Cell, Lens, Record, RowId, Table
from reflet.lenses import (
    AggregateLens,
    ComputeLens,
    ConstantLens,
    FilterLens,
    MapLens,
    RenameLens,
    SelectLens,
)
from reflet.provenance import Provenance
from reflet.sources import SourceBackend

Validator = tuple[Callable[[Any], bool], "str | None"]


class FieldProxy:
    """A field's current value plus access to its provenance via `.why()`."""

    __slots__ = ("_cell",)

    def __init__(self, cell: Cell) -> None:
        self._cell = cell

    @property
    def value(self) -> object:
        return self._cell.value

    def why(self) -> str:
        """Return a human-readable rendering of this field's lineage."""
        return self._cell.prov.render()

    def __eq__(self, other: object) -> bool:
        if isinstance(other, FieldProxy):
            return bool(self._cell.value == other._cell.value)
        return bool(self._cell.value == other)

    def __hash__(self) -> int:
        return hash(self._cell.value)

    def __repr__(self) -> str:
        return repr(self._cell.value)

    def __str__(self) -> str:
        return str(self._cell.value)

    def __format__(self, spec: str) -> str:
        return format(self._cell.value, spec)


class Row:
    """A single editable row of a View; attribute access reads/writes fields."""

    _view: View
    _index: int

    def __init__(self, view: View, index: int) -> None:
        object.__setattr__(self, "_view", view)
        object.__setattr__(self, "_index", index)

    def __getattr__(self, name: str) -> FieldProxy:
        record = self._view._table[self._index]
        if name not in record.fields:
            raise UnknownFieldError(name)
        return FieldProxy(record.fields[name])

    def __setattr__(self, name: str, value: object) -> None:
        self._view._edit(self._index, name, value)

    def __repr__(self) -> str:
        record    = self._view._table[self._index]
        values    = {k: c.value for k, c in record.fields.items()}
        return f"Row({values!r})"


@dataclass(frozen=True)
class Change:
    """One field write that a sync (real or dry-run) would make to the source."""

    source: str
    rid: RowId
    field: str
    before: object
    after: object

    def __repr__(self) -> str:
        return (
            f"Change({self.source}[{self.rid!r}].{self.field}: "
            f"{self.before!r} -> {self.after!r})"
        )


@dataclass(frozen=True)
class JournalEntry:
    """One field write that was actually committed to the source, for audit."""

    timestamp: datetime
    rid: RowId
    field: str
    before: object
    after: object


@dataclass(frozen=True)
class _EditUndo:
    index: int
    field: str
    cell: Cell


@dataclass(frozen=True)
class _SyncUndo:
    source_table: Table


_UndoAction = _EditUndo | _SyncUndo

# Lenses through which View.insert() has no well-defined inverse: a select()
# hides source fields an insert would need a value for, and an aggregate()'s
# output rows don't correspond to a single source row to invent.
_INSERT_UNSUPPORTED = (SelectLens, AggregateLens)


class View:
    """The result of `Pipeline.run()`: an editable, synchronizable table."""

    def __init__(
        self,
        view_table: Table,
        source_table: Table,
        lens: Lens,
        backend: SourceBackend,
        *,
        lenses: tuple[Lens, ...]                         = (),
        validators: dict[str, list[Validator]] | None    = None,
        tombstone_field: str | None                      = None,
    ) -> None:
        self._table                                   = view_table
        self._source_table                            = source_table
        self._lens                                    = lens
        self._backend                                 = backend
        self._lenses                                  = lenses
        self._validators                              = validators or {}
        self._tombstone_field                         = tombstone_field
        self._dirty: set[RowId]                       = set()
        self._pending_inserts: dict[RowId, Record]    = {}
        self._pending_deletes: set[RowId]             = set()
        self._pending_tombstones: set[RowId]          = set()
        self._undo_stack: list[_UndoAction]           = []
        self._redo_stack: list[_UndoAction]           = []
        self._journal: list[JournalEntry]             = []

    def __len__(self) -> int:
        return len(self._table)

    def __getitem__(self, index: int) -> Row:
        return Row(self, index)

    def __iter__(self) -> Iterator[Row]:
        return (Row(self, i) for i in range(len(self._table)))

    def __repr__(self) -> str:
        fields = list(self._table[0].fields.keys()) if self._table else []
        return f"View({len(self._table)} rows, fields={fields}, source={self._backend.path!r})"

    def __enter__(self) -> View:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        """Calls `sync()` on a clean exit; an exception leaves pending edits untouched."""
        if exc_type is None:
            self.sync()

    @property
    def rows(self) -> tuple[Row, ...]:
        """All rows as a tuple — sugar around iterating/indexing this View."""
        return tuple(Row(self, i) for i in range(len(self._table)))

    def to_dicts(self) -> list[dict[str, object]]:
        """Export the current view as plain `list[dict]` (field name -> value)."""
        return [{k: c.value for k, c in r.fields.items()} for r in self._table]

    @property
    def journal(self) -> tuple[JournalEntry, ...]:
        """The append-only history of every field write actually committed."""
        return tuple(self._journal)

    def _edit(self, index: int, field: str, value: object) -> None:
        record = self._table[index]
        if field not in record.fields:
            raise UnknownFieldError(field)
        cell = record.fields[field]
        cell.require_writable(field)
        for predicate, message in self._validators.get(field, []):
            if not predicate(value):
                raise ValidationError(field, value, message, cell.prov.render())
        new_cell = Cell(
            value,
            cell.prov.step("edit"),
            readonly         = cell.readonly,
            conflict         = cell.conflict,
            conflict_size    = cell.conflict_size,
        )
        new_fields           = dict(record.fields)
        new_fields[field]    = new_cell
        self._undo_stack.append(_EditUndo(index, field, cell))
        self._redo_stack.clear()
        self._table[index] = record.with_fields(new_fields)
        self._dirty.add(record.rid)

    def _has_pending(self) -> bool:
        return bool(
            self._dirty or self._pending_inserts or self._pending_deletes
            or self._pending_tombstones
        )

    def _pending(self) -> tuple[Table, list[Change]]:
        edit_rids    = self._dirty - set(self._pending_inserts)
        edited       = [r for r in self._table if r.rid in edit_rids]
        updated      = self._lens.put(edited, self._source_table) if edited else []

        by_rid_old               = {r.rid: r for r in self._source_table}
        changes: list[Change]    = []
        for record in updated:
            old = by_rid_old.get(record.rid)
            for field, cell in record.fields.items():
                old_cell = old.fields.get(field) if old is not None else None
                if old_cell is None or old_cell.value != cell.value:
                    before = old_cell.value if old_cell is not None else None
                    changes.append(
                        Change(self._backend.path, record.rid, field, before, cell.value)
                    )

        for rid, record in self._pending_inserts.items():
            for field, cell in record.fields.items():
                changes.append(Change(self._backend.path, rid, field, None, cell.value))

        for rid in self._pending_deletes:
            changes.append(Change(self._backend.path, rid, "*", "<row>", None))

        for rid in self._pending_tombstones:
            old_record         = by_rid_old.get(rid)
            tombstone_field    = self._tombstone_field
            assert tombstone_field is not None
            old_value = (
                old_record.fields[tombstone_field].value if old_record is not None else None
            )
            changes.append(Change(self._backend.path, rid, tombstone_field, old_value, True))

        return updated, changes

    def diff(self) -> list[Change]:
        """Preview what `sync()` would write to the source, without touching it."""
        if not self._has_pending():
            return []
        _, changes = self._pending()
        return changes

    def sync(self, *, dry_run: bool = False, force: bool = False) -> list[Change]:
        """Propagate pending edits/inserts/deletes back through the lens chain
        and write the source.

        Only rows touched by an edit are replayed through `put`; untouched rows
        are left exactly as they were read. Returns the changes written (or,
        with `dry_run=True`, the changes that *would* be written).

        Raises `SourceConflictError` if the source file changed on disk since
        it was read, unless `force=True`.
        """
        if not self._has_pending():
            return []
        if dry_run:
            return self.diff()
        if not force and self._backend.changed_since_read():
            raise SourceConflictError(self._backend.path)

        updated, changes = self._pending()

        self._undo_stack.append(_SyncUndo(list(self._source_table)))
        self._redo_stack.clear()

        by_rid = {r.rid: r for r in self._source_table}
        for record in updated:
            by_rid[record.rid] = record
        for rid, record in self._pending_inserts.items():
            by_rid[rid] = record
            self._backend._order.append(rid)
        for rid in self._pending_tombstones:
            tombstone_field = self._tombstone_field
            assert tombstone_field is not None
            target        = by_rid[rid]
            new_fields    = dict(target.fields)
            new_fields[tombstone_field] = Cell(
                True, Provenance(self._backend.path, tombstone_field).step("delete")
            )
            by_rid[rid] = target.with_fields(new_fields)
        for rid in self._pending_deletes:
            by_rid.pop(rid, None)

        self._source_table = list(by_rid.values())
        self._backend.write(self._source_table)

        self._dirty.clear()
        self._pending_inserts.clear()
        self._pending_deletes.clear()
        self._pending_tombstones.clear()

        now = datetime.now()
        self._journal.extend(
            JournalEntry(now, c.rid, c.field, c.before, c.after) for c in changes
        )
        return changes

    def undo(self) -> bool:
        """Undo the most recent edit or sync. Returns False if there's nothing to undo.

        Doesn't (yet) cover `insert()`/`delete()` made since the last sync."""
        if not self._undo_stack:
            return False
        action = self._undo_stack.pop()
        if isinstance(action, _EditUndo):
            record    = self._table[action.index]
            prev      = record.fields[action.field]
            self._redo_stack.append(_EditUndo(action.index, action.field, prev))
            new_fields                   = dict(record.fields)
            new_fields[action.field]     = action.cell
            self._table[action.index]    = record.with_fields(new_fields)
        else:
            self._redo_stack.append(_SyncUndo(list(self._source_table)))
            self._source_table    = action.source_table
            self._table           = self._lens.get(self._source_table)
            self._backend.write(self._source_table)
        return True

    def redo(self) -> bool:
        """Reapply the most recently undone edit or sync. Returns False if none."""
        if not self._redo_stack:
            return False
        action = self._redo_stack.pop()
        if isinstance(action, _EditUndo):
            record    = self._table[action.index]
            prev      = record.fields[action.field]
            self._undo_stack.append(_EditUndo(action.index, action.field, prev))
            new_fields                   = dict(record.fields)
            new_fields[action.field]     = action.cell
            self._table[action.index]    = record.with_fields(new_fields)
            self._dirty.add(record.rid)
        else:
            self._undo_stack.append(_SyncUndo(list(self._source_table)))
            self._source_table    = action.source_table
            self._table           = self._lens.get(self._source_table)
            self._backend.write(self._source_table)
        return True

    def why_not(self, rid: RowId) -> str:
        """Explain why the source row identified by `rid` is absent from the view."""
        matches = [r for r in self._source_table if r.rid == rid]
        if not matches:
            return f"no source row with id {rid!r}"
        table = matches
        for lens in self._lenses:
            table = lens.get(table)
            if not table:
                return f"excluded by {lens.name}"
        return f"row {rid!r} is present in the view (it wasn't filtered out)"

    def impact(self, rid: RowId, field: str) -> list[tuple[RowId, str]]:
        """Which (row, view field) pairs were derived from source[rid][field]."""
        result: list[tuple[RowId, str]] = []
        for r in self._table:
            contributing = r.rid if isinstance(r.rid, tuple) else (r.rid,)
            if rid not in contributing:
                continue
            for name, cell in r.fields.items():
                if cell.prov.source_field == field:
                    result.append((r.rid, name))
        return result

    def insert(self, **values: object) -> Row:
        """Insert a new row, given its view-level field values.

        Fields introduced by `rename`/`map` are un-renamed/un-mapped back to
        their source form; `constant`/`compute` fields can't be supplied (they
        have no inverse); `filter(..., defaults=...)` fills in anything that
        filter requires but wasn't given. Not supported through `select()` or
        `aggregate()` — see `_INSERT_UNSUPPORTED`.
        """
        if any(isinstance(lens, _INSERT_UNSUPPORTED) for lens in self._lenses):
            raise UnsupportedOperationError(
                "insert() isn't supported through select()/aggregate() in this pipeline"
            )

        source_fields: dict[str, object] = dict(values)
        for lens in reversed(self._lenses):
            if isinstance(lens, RenameLens):
                for new_name, old_name in lens.mapping.items():
                    if new_name in source_fields:
                        source_fields[old_name] = source_fields.pop(new_name)
            elif isinstance(lens, MapLens):
                if lens.field in source_fields:
                    source_fields[lens.field] = lens.bwd(source_fields[lens.field])
            elif isinstance(lens, ConstantLens | ComputeLens):
                if lens.field in source_fields:
                    raise ReadOnlyFieldError(lens.field)
            elif isinstance(lens, FilterLens):
                for k, v in lens.defaults.items():
                    source_fields.setdefault(k, v)

        fieldnames    = self._backend.fieldnames
        missing       = [f for f in fieldnames if f not in source_fields]
        if missing:
            raise InsertError(f"insert() missing required field(s): {', '.join(missing)}")
        extra = [f for f in source_fields if f not in fieldnames]
        if extra:
            raise InsertError(f"insert() got unknown field(s): {', '.join(extra)}")

        if self._backend.key is not None:
            rid: RowId = source_fields[self._backend.key]
        else:
            existing    = [r.rid for r in self._source_table if isinstance(r.rid, int)]
            rid         = (max(existing) + 1) if existing else 0
        if rid in {r.rid for r in self._source_table} or rid in self._pending_inserts:
            raise InsertError(f"insert(): a row with id {rid!r} already exists")

        new_record = Record(
            rid,
            {
                k: Cell(v, Provenance(self._backend.path, k).step("insert"))
                for k, v in source_fields.items()
            },
        )
        view_rows = self._lens.get([new_record])
        if not view_rows:
            raise InsertError(
                "insert(): the new row doesn't satisfy the pipeline's filter(s); "
                "check filter(..., defaults=...)"
            )

        self._pending_inserts[rid] = new_record
        self._dirty.add(rid)
        self._table.append(view_rows[0])
        return Row(self, len(self._table) - 1)

    def delete(self, index: int, *, on_delete: str = "delete") -> None:
        """Remove the row at `index` from the view, and on the next `sync()`:

        - `"delete"` (default): remove the matching source row(s) entirely.
        - `"tombstone"`: set `tombstone_field` (from `Source(..., tombstone_field=...)`)
          instead of removing the row; the field must already be a source column.
        - `"ignore"`: remove it from this view only; the source is untouched.
        """
        record          = self._table[index]
        contributing    = record.rid if isinstance(record.rid, tuple) else (record.rid,)

        if on_delete == "ignore":
            del self._table[index]
            return
        if on_delete == "delete":
            self._pending_deletes.update(contributing)
            del self._table[index]
            return
        if on_delete == "tombstone":
            if self._tombstone_field is None:
                raise ValueError("on_delete='tombstone' requires Source(..., tombstone_field=...)")
            if self._tombstone_field not in self._backend.fieldnames:
                raise ValueError(
                    f"tombstone field {self._tombstone_field!r} isn't a column in "
                    f"{self._backend.path!r}; add it to the source first"
                )
            self._pending_tombstones.update(contributing)
            del self._table[index]
            return
        raise ValueError(
            f"unknown on_delete policy: {on_delete!r} (expected 'delete'/'tombstone'/'ignore')"
        )

    def watch(
        self,
        *,
        interval: float                         = 1.0,
        max_iterations: int | None              = None,
        on_change: Callable[[], None] | None    = None,
    ) -> None:
        """Poll for pending edits and external source changes, syncing both ways.

        This is a polling loop (reflet has no OS-level file-watch — zero
        dependencies, and no stdlib cross-platform API for it), so `interval`
        trades responsiveness for how often the source file gets re-hashed.
        Blocks the calling thread; with `max_iterations=None` (the default) it
        runs until interrupted (e.g. Ctrl-C/KeyboardInterrupt).

        Each tick: pending edits are flushed via `sync()`. If that raises
        `SourceConflictError` (or the source simply changed with nothing
        pending), `on_change()` is called instead of silently overwriting or
        ignoring the external change — by default that's a no-op, so pass one
        if you want to reload (e.g. re-run the pipeline and swap this view
        out) or otherwise react.
        """
        import time

        i = 0
        while max_iterations is None or i < max_iterations:
            if self._has_pending():
                try:
                    self.sync()
                except SourceConflictError:
                    if on_change is not None:
                        on_change()
            elif self._backend.changed_since_read() and on_change is not None:
                on_change()
            i += 1
            if max_iterations is None or i < max_iterations:
                time.sleep(interval)
