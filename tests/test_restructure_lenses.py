"""cast(), split(), merge(), round-trip laws included."""

from __future__ import annotations

import random
from pathlib import Path

import pytest

import reflet as rf
from reflet.lens import Cell, Record
from reflet.lenses import SplitLens
from reflet.provenance import Provenance


def test_cast_round_trips(clients_csv: Path) -> None:
    view = rf.Source(str(clients_csv)).cast("price", to=float, back=str).run()
    assert isinstance(view[0].price.value, float)
    view[0].price = 999.5
    view.sync()
    assert "999.5" in clients_csv.read_text()


def test_split_exposes_two_fields_and_writes_back(tmp_path: Path) -> None:
    path = tmp_path / "people.csv"
    path.write_text("id,full_name\n1,Jean Martin\n2,Anna Smith\n")
    view = (
        rf.Source(str(path), key="id")
        .split(
            "full_name",
            into    = ("first", "last"),
            fwd     = lambda v: tuple(v.split(" ", 1)),
            bwd     = lambda parts: " ".join(parts),
        )
        .run()
    )
    assert str(view[0].first) == "Jean"
    assert str(view[0].last) == "Martin"

    view[0].last = "Dupont"
    view.sync()
    assert "1,Jean Dupont" in path.read_text()


def test_merge_exposes_one_field_and_writes_back(tmp_path: Path) -> None:
    path = tmp_path / "people.csv"
    path.write_text("id,first,last\n1,Jean,Martin\n2,Anna,Smith\n")
    view = (
        rf.Source(str(path), key="id")
        .merge(
            fields    = ("first", "last"),
            into      = "full_name",
            fwd       = lambda parts: " ".join(parts),
            bwd       = lambda v: tuple(v.split(" ", 1)),
        )
        .run()
    )
    assert str(view[0].full_name) == "Jean Martin"

    view[0].full_name = "Jean Dupont"
    view.sync()
    content = path.read_text()
    assert "1,Jean,Dupont" in content


@pytest.mark.parametrize("trial", range(20))
def test_split_lens_roundtrip_law(trial: int) -> None:
    """get(put(a, s)) == a and put(get(s), s) == s for SplitLens."""
    rng      = random.Random(trial)
    names    = ["Jean Martin", "Anna Smith", "Marie Durand"]
    s = [
        Record(i, {"full_name": Cell(rng.choice(names), Provenance("src", "full_name"))})
        for i in range(3)
    ]
    lens = SplitLens(
        "full_name",
        into    = ("first", "last"),
        fwd     = lambda v: tuple(v.split(" ", 1)),
        bwd     = lambda parts: " ".join(parts),
    )

    a     = lens.get(s)
    s2    = lens.put(a, s)
    assert [r.fields["full_name"].value for r in s2] == [
        r.fields["full_name"].value for r in s
    ]

    idx                      = rng.randrange(len(a))
    edited_fields            = dict(a[idx].fields)
    edited_fields["last"]    = Cell("Dupont", edited_fields["last"].prov)
    a_edited                 = list(a)
    a_edited[idx]            = a[idx].with_fields(edited_fields)

    s3    = lens.put(a_edited, s)
    a3    = lens.get(s3)
    assert str(a3[idx].fields["last"].value) == "Dupont"
