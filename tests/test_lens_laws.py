"""Property-style round-trip law tests: get(put(a, s)) == a and put(get(s), s) == s."""

from __future__ import annotations

import random
import string

import pytest

from reflet.lens import Cell, Record, Table
from reflet.lenses import FilterLens, MapLens, RenameLens, SelectLens
from reflet.provenance import Provenance

TRIALS = 25


def _rand_str(rng: random.Random, n: int = 6) -> str:
    return "".join(rng.choices(string.ascii_letters, k=n))


def random_table(rng: random.Random, size: int) -> Table:
    table = []
    for i in range(size):
        fields = {
            "id": Cell(i, Provenance("src", "id")),
            "name": Cell(_rand_str(rng), Provenance("src", "name")),
            "country": Cell(rng.choice(["FR", "UK", "DE"]), Provenance("src", "country")),
            "price": Cell(round(rng.uniform(1, 100), 2), Provenance("src", "price")),
        }
        table.append(Record(i, fields))
    return table


def values_of(table: Table) -> dict:
    return {r.rid: {k: c.value for k, c in r.fields.items()} for r in table}


@pytest.mark.parametrize("trial", range(TRIALS))
def test_rename_roundtrip(trial: int) -> None:
    rng     = random.Random(trial)
    s       = random_table(rng, rng.randint(1, 8))
    lens    = RenameLens({"customer": "name"})

    a = lens.get(s)
    assert values_of(lens.put(a, s)) == values_of(s)  # no-edit identity

    idx                     = rng.randrange(len(a))
    edited_fields           = dict(a[idx].fields)
    edited_fields["customer"]    = Cell(_rand_str(rng), edited_fields["customer"].prov)
    a_edited                = list(a)
    a_edited[idx]           = a[idx].with_fields(edited_fields)

    s2    = lens.put(a_edited, s)
    a2    = lens.get(s2)
    assert a2[idx].fields["customer"].value == edited_fields["customer"].value


@pytest.mark.parametrize("trial", range(TRIALS))
def test_select_roundtrip(trial: int) -> None:
    rng     = random.Random(trial + 1000)
    s       = random_table(rng, rng.randint(1, 8))
    lens    = SelectLens(["name", "price"])

    a = lens.get(s)
    assert values_of(lens.put(a, s)) == values_of(s)

    idx                       = rng.randrange(len(a))
    edited_fields             = dict(a[idx].fields)
    edited_fields["price"]    = Cell(rng.uniform(1, 100), edited_fields["price"].prov)
    a_edited                  = list(a)
    a_edited[idx]             = a[idx].with_fields(edited_fields)

    s2    = lens.put(a_edited, s)
    a2    = lens.get(s2)
    assert a2[idx].fields["price"].value == edited_fields["price"].value
    # dropped field ("id"/"country") survives untouched in the reconstructed source
    assert s2[idx].fields["country"].value == s[idx].fields["country"].value


@pytest.mark.parametrize("trial", range(TRIALS))
def test_filter_roundtrip(trial: int) -> None:
    rng     = random.Random(trial + 2000)
    s       = random_table(rng, rng.randint(2, 10))
    lens    = FilterLens(lambda r: bool(r.country == "FR"))

    a     = lens.get(s)
    s2    = lens.put(a, s)
    assert values_of(s2) == values_of(s)  # no-edit identity

    if a:
        idx                      = rng.randrange(len(a))
        edited_fields            = dict(a[idx].fields)
        edited_fields["name"]    = Cell(_rand_str(rng), edited_fields["name"].prov)
        a_edited                 = list(a)
        a_edited[idx]            = a[idx].with_fields(edited_fields)

        s3          = lens.put(a_edited, s)
        a3          = lens.get(s3)
        matching    = [r for r in a3 if r.rid == a_edited[idx].rid]
        assert matching and matching[0].fields["name"].value == edited_fields["name"].value

    # rows that don't match the predicate are never touched by put
    s_by_rid        = {r.rid: r for r in s}
    dropped_rids    = set(s_by_rid) - {r.rid for r in a}
    s2_by_rid       = {r.rid: r for r in s2}
    for rid in dropped_rids:
        assert s2_by_rid[rid].fields == s_by_rid[rid].fields


@pytest.mark.parametrize("trial", range(TRIALS))
def test_map_roundtrip(trial: int) -> None:
    rng     = random.Random(trial + 3000)
    s       = random_table(rng, rng.randint(1, 8))
    lens    = MapLens("price", fwd=lambda x: x * 1.2, bwd=lambda x: x / 1.2)

    a     = lens.get(s)
    s2    = lens.put(a, s)
    for r, r2 in zip(s, s2, strict=True):
        assert r.fields["price"].value == pytest.approx(r2.fields["price"].value)

    idx                       = rng.randrange(len(a))
    new_value                 = rng.uniform(1, 500)
    edited_fields             = dict(a[idx].fields)
    edited_fields["price"]    = Cell(new_value, edited_fields["price"].prov)
    a_edited                  = list(a)
    a_edited[idx]             = a[idx].with_fields(edited_fields)

    s3    = lens.put(a_edited, s)
    a3    = lens.get(s3)
    assert a3[idx].fields["price"].value == pytest.approx(new_value)
