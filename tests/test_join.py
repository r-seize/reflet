"""join(): inner join with read-only right-hand fields."""

from __future__ import annotations

from pathlib import Path

import pytest

import reflet as rf
from reflet.errors import ReadOnlyFieldError


@pytest.fixture
def orders_csv(tmp_path: Path) -> Path:
    path = tmp_path / "orders.csv"
    path.write_text("order_id,client_id,amount\n100,1,50\n101,3,75\n")
    return path


def test_join_merges_matching_rows(clients_csv: Path, orders_csv: Path) -> None:
    orders = rf.Source(str(orders_csv), key="order_id")
    view = (
        rf.Source(str(clients_csv), key="id")
        .join(orders, on="id", other_on="client_id", prefix="order_")
        .run()
    )
    # only ids 1 and 3 have a matching order; this is an inner join
    ids = sorted(int(str(r.id)) for r in view)
    assert ids == [1, 3]
    row = next(r for r in view if str(r.id) == "1")
    assert int(str(row.order_amount)) == 50


def test_join_right_fields_are_read_only(clients_csv: Path, orders_csv: Path) -> None:
    orders = rf.Source(str(orders_csv), key="order_id")
    view = (
        rf.Source(str(clients_csv), key="id")
        .join(orders, on="id", other_on="client_id", prefix="order_")
        .run()
    )
    with pytest.raises(ReadOnlyFieldError):
        view[0].order_amount = 999


def test_join_left_fields_remain_writable(clients_csv: Path, orders_csv: Path) -> None:
    orders = rf.Source(str(orders_csv), key="order_id")
    view = (
        rf.Source(str(clients_csv), key="id")
        .join(orders, on="id", other_on="client_id", prefix="order_")
        .run()
    )
    view[0].name = "Changed"
    view.sync()
    assert "Changed" in clients_csv.read_text()
    assert orders_csv.read_text() == "order_id,client_id,amount\n100,1,50\n101,3,75\n"


def test_join_name_collision_without_prefix_raises(clients_csv: Path, tmp_path: Path) -> None:
    other = tmp_path / "other.csv"
    other.write_text("id,country\n1,DE\n")  # "country" collides with clients_csv's own field
    other_pipeline    = rf.Source(str(other), key="id")
    view              = rf.Source(str(clients_csv), key="id").join(other_pipeline, on="id")
    with pytest.raises(ValueError, match="collides"):
        view.run()
