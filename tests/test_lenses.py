from __future__ import annotations

import pytest

from reflet.errors import ReadOnlyFieldError
from reflet.lens import Cell, ConflictPolicy, Record
from reflet.lenses import AggregateLens, ComputeLens, ConstantLens
from reflet.provenance import Provenance


def make_record(rid: int, **values: object) -> Record:
    return Record(rid, {k: Cell(v, Provenance("src", k)) for k, v in values.items()})


def test_constant_adds_readonly_field_and_put_strips_it() -> None:
    s       = [make_record(0, name="Martin")]
    lens    = ConstantLens("currency", "EUR")

    a = lens.get(s)
    assert a[0].fields["currency"].value == "EUR"
    assert a[0].fields["currency"].readonly is True
    with pytest.raises(ReadOnlyFieldError):
        a[0].fields["currency"].require_writable("currency")

    s2 = lens.put(a, s)
    assert "currency" not in s2[0].fields
    assert s2[0].fields["name"].value == "Martin"


def test_compute_field_is_readonly_and_derived() -> None:
    s       = [make_record(0, price=10, qty=3)]
    lens    = ComputeLens("total", lambda r: r.price * r.qty)

    a = lens.get(s)
    assert a[0].fields["total"].value == 30
    assert a[0].fields["total"].readonly is True

    s2 = lens.put(a, s)
    assert "total" not in s2[0].fields


def test_aggregate_default_policy_blocks_ambiguous_edit() -> None:
    s       = [make_record(0, team="A", score=10), make_record(1, team="A", score=20)]
    lens    = AggregateLens("team", "total_score", sum, source_field="score")

    a = lens.get(s)
    assert len(a) == 1
    assert a[0].fields["total_score"].value == 30

    cell = a[0].fields["team"]
    assert cell.conflict == ConflictPolicy.ERROR
    from reflet.errors import ConflictError

    with pytest.raises(ConflictError):
        cell.require_writable("team")


def test_aggregate_first_policy_targets_first_row() -> None:
    s = [make_record(0, team="A", score=10), make_record(1, team="A", score=20)]
    lens = AggregateLens(
        "team", "total_score", sum, source_field="score", policy=ConflictPolicy.FIRST
    )

    a                        = lens.get(s)
    group_record             = a[0]
    edited_fields            = dict(group_record.fields)
    edited_fields["team"]    = Cell("B", edited_fields["team"].prov)
    a_edited                 = [group_record.with_fields(edited_fields)]

    s2        = lens.put(a_edited, s)
    by_rid    = {r.rid: r for r in s2}
    assert by_rid[0].fields["team"].value == "B"
    assert by_rid[1].fields["team"].value == "A"  # untouched


def test_aggregate_unchanged_key_is_a_noop_even_under_error_policy() -> None:
    s       = [make_record(0, team="A", score=10), make_record(1, team="A", score=20)]
    lens    = AggregateLens("team", "total_score", sum, source_field="score")

    a     = lens.get(s)
    s2    = lens.put(a, s)  # no edits at all
    assert {r.rid: r.fields["team"].value for r in s2} == {0: "A", 1: "A"}
