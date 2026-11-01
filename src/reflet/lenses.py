"""Concrete lenses: rename, select, filter, map, constant, compute, aggregate."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING, Any

from reflet.errors import ConflictError, UnknownFieldError
from reflet.lens import Cell, ConflictPolicy, Lens, Record, RowId, RowKey, Table, index_by_rid

if TYPE_CHECKING:
    from reflet.pipeline import Pipeline


class RowView:
    """Read-only attribute access to a record's field values, for predicates/fns."""

    def __init__(self, record: Record) -> None:
        self._record = record

    def __getattr__(self, name: str) -> Any:
        try:
            return self._record.fields[name].value
        except KeyError as exc:
            raise UnknownFieldError(name) from exc


class RenameLens(Lens):
    """Renames fields: `mapping` is {new_name: old_name}."""

    def __init__(self, mapping: dict[str, str]) -> None:
        self.mapping    = mapping
        self.name       = f"rename({mapping})"

    def get(self, s: Table) -> Table:
        out = []
        for r in s:
            fields = dict(r.fields)
            for new_name, old_name in self.mapping.items():
                cell = fields.pop(old_name)
                fields[new_name] = cell.transform(
                    lambda v: v, f"rename {old_name}->{new_name}"
                )
            out.append(r.with_fields(fields))
        return out

    def put(self, a: Table, s: Table) -> Table:
        s_by_rid    = index_by_rid(s)
        out         = []
        for a_row in a:
            fields = dict(a_row.fields)
            for new_name, old_name in self.mapping.items():
                cell = fields.pop(new_name)
                fields[old_name] = cell.transform(
                    lambda v: v, f"rename {new_name}->{old_name}"
                )
            out.append(s_by_rid[a_row.rid].with_fields(fields))
        return out


class SelectLens(Lens):
    """Projects down to a subset of fields; dropped fields pass through untouched."""

    def __init__(self, fields: Iterable[str]) -> None:
        self.fields    = tuple(fields)
        self.name      = f"select({self.fields})"

    def get(self, s: Table) -> Table:
        out = []
        for r in s:
            fields = {k: r.fields[k] for k in self.fields}
            out.append(r.with_fields(fields))
        return out

    def put(self, a: Table, s: Table) -> Table:
        s_by_rid    = index_by_rid(s)
        out         = []
        for a_row in a:
            original    = s_by_rid[a_row.rid]
            fields      = dict(original.fields)
            fields.update(a_row.fields)
            out.append(original.with_fields(fields))
        return out


class FilterLens(Lens):
    """Keeps only rows matching `predicate`; dropped rows pass through unchanged.

    `defaults`, when given, are the field values that make a freshly
    `View.insert()`-ed row satisfy `predicate` (e.g. `{"country": "FR"}` for a
    `country == "FR"` filter) — they're never checked against `predicate`
    itself, just applied so the new row has a value for every such field.
    """

    def __init__(
        self, predicate: Callable[[RowView], bool], defaults: dict[str, Any] | None = None
    ) -> None:
        self.predicate    = predicate
        self.defaults     = defaults or {}
        self.name         = "filter(...)"

    def get(self, s: Table) -> Table:
        return [r for r in s if self.predicate(RowView(r))]

    def put(self, a: Table, s: Table) -> Table:
        a_by_rid = index_by_rid(a)
        return [a_by_rid.get(r.rid, r) for r in s]


class SortLens(Lens):
    """Orders the view by a field; write-back ignores order and merges by rid."""

    def __init__(self, field: str, reverse: bool = False) -> None:
        self.field      = field
        self.reverse    = reverse
        self.name       = f"sort({field})"

    def get(self, s: Table) -> Table:
        return sorted(s, key=lambda r: r.fields[self.field].value, reverse=self.reverse)

    def put(self, a: Table, s: Table) -> Table:
        a_by_rid = index_by_rid(a)
        return [a_by_rid.get(r.rid, r) for r in s]


class MapLens(Lens):
    """Transforms one field with an explicit forward/backward function pair."""

    def __init__(self, field: str, fwd: Callable[[Any], Any], bwd: Callable[[Any], Any]) -> None:
        self.field    = field
        self.fwd      = fwd
        self.bwd      = bwd
        self.name     = f"map({field})"

    def get(self, s: Table) -> Table:
        out = []
        for r in s:
            fields                = dict(r.fields)
            fields[self.field]    = fields[self.field].transform(self.fwd, f"map({self.field})")
            out.append(r.with_fields(fields))
        return out

    def put(self, a: Table, s: Table) -> Table:
        s_by_rid    = index_by_rid(s)
        out         = []
        for a_row in a:
            fields = dict(a_row.fields)
            fields[self.field] = fields[self.field].transform(
                self.bwd, f"map({self.field}) [inverse]"
            )
            out.append(s_by_rid[a_row.rid].with_fields(fields))
        return out


class SplitLens(Lens):
    """Splits one source field into several view fields (e.g. a full name
    into first/last). `fwd` takes the source value, returns a tuple matching
    `into`; `bwd` takes that tuple back, returns the source value."""

    def __init__(
        self,
        field: str,
        into: tuple[str, ...],
        fwd: Callable[[Any], tuple[Any, ...]],
        bwd: Callable[[tuple[Any, ...]], Any],
    ) -> None:
        self.field    = field
        self.into     = into
        self.fwd      = fwd
        self.bwd      = bwd
        self.name     = f"split({field}->{into})"

    def get(self, s: Table) -> Table:
        out = []
        for r in s:
            fields    = dict(r.fields)
            cell      = fields.pop(self.field)
            parts     = self.fwd(cell.value)
            for name, value in zip(self.into, parts, strict=True):
                fields[name] = Cell(value, cell.prov.step(f"split({self.field}->{name})"))
            out.append(r.with_fields(fields))
        return out

    def put(self, a: Table, s: Table) -> Table:
        s_by_rid    = index_by_rid(s)
        out         = []
        for a_row in a:
            fields    = dict(a_row.fields)
            parts     = tuple(fields.pop(name) for name in self.into)
            value     = self.bwd(tuple(c.value for c in parts))
            fields[self.field] = parts[0].transform(
                lambda _v, value=value: value, f"split({self.field}->{self.into}) [inverse]"
            )
            out.append(s_by_rid[a_row.rid].with_fields(fields))
        return out


class MergeLens(Lens):
    """Merges several source fields into one view field (e.g. first/last into
    a full name). The dual of `SplitLens`: `fwd` takes a tuple of the source
    values, returns the merged value; `bwd` takes that value back, returns a
    tuple matching `fields`."""

    def __init__(
        self,
        fields: tuple[str, ...],
        into: str,
        fwd: Callable[[tuple[Any, ...]], Any],
        bwd: Callable[[Any], tuple[Any, ...]],
    ) -> None:
        self.fields    = fields
        self.into      = into
        self.fwd       = fwd
        self.bwd       = bwd
        self.name      = f"merge({fields}->{into})"

    def get(self, s: Table) -> Table:
        out = []
        for r in s:
            fields               = dict(r.fields)
            cells                = [fields.pop(name) for name in self.fields]
            value                = self.fwd(tuple(c.value for c in cells))
            step                 = f"merge({self.fields}->{self.into})"
            fields[self.into]    = Cell(value, cells[0].prov.step(step))
            out.append(r.with_fields(fields))
        return out

    def put(self, a: Table, s: Table) -> Table:
        s_by_rid    = index_by_rid(s)
        out         = []
        for a_row in a:
            fields    = dict(a_row.fields)
            cell      = fields.pop(self.into)
            parts     = self.bwd(cell.value)
            for name, value in zip(self.fields, parts, strict=True):
                fields[name] = cell.transform(
                    lambda _v, value=value: value, f"merge({self.into}) [inverse] ->{name}"
                )
            out.append(s_by_rid[a_row.rid].with_fields(fields))
        return out


class ConstantLens(Lens):
    """Adds a fixed, read-only field."""

    def __init__(self, field: str, value: Any) -> None:
        self.field    = field
        self.value    = value
        self.name     = f"constant({field}={value!r})"

    def get(self, s: Table) -> Table:
        from reflet.provenance import Provenance

        out = []
        for r in s:
            fields = dict(r.fields)
            fields[self.field] = Cell(
                self.value, Provenance("constant", self.field), readonly=True
            )
            out.append(r.with_fields(fields))
        return out

    def put(self, a: Table, s: Table) -> Table:
        s_by_rid    = index_by_rid(s)
        out         = []
        for a_row in a:
            fields = {k: v for k, v in a_row.fields.items() if k != self.field}
            out.append(s_by_rid[a_row.rid].with_fields(fields))
        return out


class ComputeLens(Lens):
    """Adds a read-only field derived from the other fields of the same row."""

    def __init__(self, field: str, fn: Callable[[RowView], Any]) -> None:
        self.field    = field
        self.fn       = fn
        self.name     = f"compute({field})"

    def get(self, s: Table) -> Table:
        from reflet.provenance import Provenance

        out = []
        for r in s:
            fields = dict(r.fields)
            fields[self.field] = Cell(
                self.fn(RowView(r)), Provenance("compute", self.field), readonly=True
            )
            out.append(r.with_fields(fields))
        return out

    def put(self, a: Table, s: Table) -> Table:
        s_by_rid    = index_by_rid(s)
        out         = []
        for a_row in a:
            fields = {k: v for k, v in a_row.fields.items() if k != self.field}
            out.append(s_by_rid[a_row.rid].with_fields(fields))
        return out


class AggregateLens(Lens):
    """Groups rows by `group_by` into one output row per group.

    Each output row carries the (writable, conflict-policed) group key and a
    read-only `agg_field` computed by `agg_fn` over the group's values of
    `source_field`.
    """

    def __init__(
        self,
        group_by: str,
        agg_field: str,
        agg_fn: Callable[[list[Any]], Any],
        source_field: str | None    = None,
        policy: ConflictPolicy      = ConflictPolicy.ERROR,
    ) -> None:
        self.group_by        = group_by
        self.agg_field       = agg_field
        self.agg_fn          = agg_fn
        self.source_field    = source_field or group_by
        self.policy          = policy
        self.name            = f"aggregate(by={group_by}, {agg_field})"

    def get(self, s: Table) -> Table:
        from reflet.provenance import Provenance

        groups: dict[Any, list[Record]] = defaultdict(list)
        for r in s:
            groups[r.fields[self.group_by].value].append(r)

        out = []
        for key, rows in groups.items():
            rids: tuple[RowKey, ...] = tuple(
                r.rid[0] if isinstance(r.rid, tuple) else r.rid for r in rows
            )
            values    = [r.fields[self.source_field].value for r in rows]
            fields = {
                self.group_by: Cell(
                    key,
                    Provenance("aggregate", self.group_by),
                    conflict         = self.policy if len(rows) > 1 else None,
                    conflict_size    = len(rows),
                ),
                self.agg_field: Cell(
                    self.agg_fn(values), Provenance("aggregate", self.agg_field), readonly=True
                ),
            }
            rid: RowId = rids if len(rids) > 1 else list(rids)[0]
            out.append(Record(rid, fields))
        return out

    def put(self, a: Table, s: Table) -> Table:
        s_by_rid    = index_by_rid(s)
        result      = dict(s_by_rid)
        for a_row in a:
            new_key                           = a_row.fields[self.group_by].value
            rid                               = a_row.rid
            group_rids: tuple[RowKey, ...]    = rid if isinstance(rid, tuple) else (rid,)
            if all(s_by_rid[r].fields[self.group_by].value == new_key for r in group_rids):
                continue  # unchanged: nothing to write back
            if len(group_rids) > 1 and self.policy == ConflictPolicy.ERROR:
                raise ConflictError(len(group_rids))
            group_rids_list = list(group_rids)
            target = (
                group_rids_list[0]
                if len(group_rids) == 1 or self.policy == ConflictPolicy.FIRST
                else group_rids_list[-1]
            )
            original    = s_by_rid[target]
            fields      = dict(original.fields)
            fields[self.group_by] = a_row.fields[self.group_by].transform(
                lambda v: v, "aggregate [inverse]"
            )
            result[target] = original.with_fields(fields)
        return list(result.values())


class JoinLens(Lens):
    """Inner-joins each row against another pipeline's rows, by key.

    Right-hand fields are **read-only** for now: a true two-way join would
    need a View spanning two backends, which reflet doesn't support yet (see
    the README's Join section). Rows with no match on the right are dropped,
    same as `filter`. `other` is re-read on every `get()`, so edits made to
    its file between reads are picked up.
    """

    def __init__(
        self,
        other: Pipeline,
        on: str,
        other_on: str | None    = None,
        prefix: str | None      = None,
    ) -> None:
        self.other       = other
        self.on          = on
        self.other_on    = other_on or on
        self.prefix      = prefix
        self.name        = f"join(on={on})"

    def get(self, s: Table) -> Table:
        right_table                        = self.other.run()._table
        right_by_key: dict[Any, Record]    = {}
        for r in right_table:
            right_by_key.setdefault(r.fields[self.other_on].value, r)

        out = []
        for r in s:
            match = right_by_key.get(r.fields[self.on].value)
            if match is None:
                continue
            fields = dict(r.fields)
            for name, cell in match.fields.items():
                out_name = f"{self.prefix}{name}" if self.prefix else name
                if out_name in fields:
                    raise ValueError(
                        f"join(): right-hand field {name!r} collides with a left "
                        "field of the same name; pass prefix=..."
                    )
                fields[out_name] = Cell(cell.value, cell.prov, readonly=True)
            out.append(r.with_fields(fields))
        return out

    def put(self, a: Table, s: Table) -> Table:
        s_by_rid    = index_by_rid(s)
        out         = []
        for a_row in a:
            original    = s_by_rid[a_row.rid]
            fields      = {k: v for k, v in a_row.fields.items() if k in original.fields}
            out.append(original.with_fields(fields))
        return out
