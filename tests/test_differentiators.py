"""validate(), why_not()/impact(), sort(), insert(), delete()."""

from __future__ import annotations

from pathlib import Path

import pytest

import reflet as rf
from reflet.errors import InsertError, UnsupportedOperationError, ValidationError


def test_validate_rejects_bad_edit_before_touching_source(clients_csv: Path) -> None:
    pipeline = rf.Source(str(clients_csv)).validate(
        "price", lambda x: x > 0, "price must be positive"
    )
    view      = pipeline.run()
    before    = clients_csv.read_text()

    with pytest.raises(ValidationError, match="price must be positive"):
        view[0].price = -5
    assert clients_csv.read_text() == before
    assert view.diff() == []  # the rejected edit never became pending


def test_validate_allows_passing_edit(clients_csv: Path) -> None:
    view             = rf.Source(str(clients_csv)).validate("price", lambda x: x > 0).run()
    view[0].price    = 500
    view.sync()
    assert "500" in clients_csv.read_text()


def test_why_not_explains_filtered_out_row(clients_csv: Path) -> None:
    view = rf.Source(str(clients_csv), key="id").filter(lambda r: r.country == "FR").run()
    assert "filter" in view.why_not(2)  # id=2 is Smith, UK


def test_why_not_for_present_row(clients_csv: Path) -> None:
    view = rf.Source(str(clients_csv), key="id").filter(lambda r: r.country == "FR").run()
    assert "present" in view.why_not(1)  # id=1 is Martin, FR


def test_why_not_for_unknown_id(clients_csv: Path) -> None:
    view = rf.Source(str(clients_csv), key="id").run()
    assert "no source row" in view.why_not(999)


def test_impact_traces_view_fields_back_to_a_source_field(clients_csv: Path) -> None:
    view = rf.Source(str(clients_csv), key="id").rename(customer="name").run()
    assert view.impact(1, "name") == [(1, "customer")]
    assert view.impact(1, "country") == [(1, "country")]
    assert view.impact(1, "price") == [(1, "price")]


def test_sort_orders_view_but_preserves_source_order_on_writeback(clients_csv: Path) -> None:
    view     = rf.Source(str(clients_csv), key="id").sort("name").run()
    names    = [str(r.name) for r in view]
    assert names == sorted(names)

    view[0].name = "Changed"  # alphabetically first: Dupont
    view.sync()
    content = clients_csv.read_text()
    # original file order (by id) is preserved; only the targeted row changed
    assert content.splitlines()[1].startswith("1,Martin")
    assert "Changed" in content


def test_insert_adds_a_row_and_syncs(clients_csv: Path) -> None:
    view    = rf.Source(str(clients_csv), key="id").rename(customer="name").run()
    row     = view.insert(id=99, customer="Nouveau", country="BE", price=5)
    assert str(row.customer) == "Nouveau"
    assert len(view) == 5

    changes = view.diff()
    assert all(c.before is None for c in changes)  # a pure insert: nothing pre-existed

    view.sync()
    assert "99,Nouveau,BE,5" in clients_csv.read_text()


def test_insert_applies_filter_defaults(clients_csv: Path) -> None:
    view = (
        rf.Source(str(clients_csv), key="id")
        .filter(lambda r: r.country == "FR", defaults={"country": "FR"})
        .run()
    )
    row = view.insert(id=99, name="Nouveau", price=5)
    assert str(row.country) == "FR"
    view.sync()
    assert "99,Nouveau,FR,5" in clients_csv.read_text()


def test_insert_rejects_readonly_field(clients_csv: Path) -> None:
    view = rf.Source(str(clients_csv), key="id").compute("tax", lambda r: r.price * 0.2).run()
    from reflet.errors import ReadOnlyFieldError

    with pytest.raises(ReadOnlyFieldError):
        view.insert(id=99, name="Nouveau", country="BE", price=5, tax=1)


def test_insert_missing_field_raises(clients_csv: Path) -> None:
    view = rf.Source(str(clients_csv), key="id").run()
    with pytest.raises(InsertError, match="missing required field"):
        view.insert(id=99, name="Nouveau")


def test_insert_unsupported_through_select(clients_csv: Path) -> None:
    view = rf.Source(str(clients_csv), key="id").select("name", "price").run()
    with pytest.raises(UnsupportedOperationError):
        view.insert(name="Nouveau", price=5)


def test_insert_unsupported_through_aggregate(clients_csv: Path) -> None:
    view = rf.Source(str(clients_csv), key="id").aggregate(
        "country", "total", sum, source_field="price"
    ).run()
    with pytest.raises(UnsupportedOperationError):
        view.insert(country="BE", total=0)


def test_delete_default_policy_removes_row(clients_csv: Path) -> None:
    view = rf.Source(str(clients_csv), key="id").run()
    view.delete(0)  # id=1, Martin
    assert len(view) == 3
    view.sync()
    assert "Martin" not in clients_csv.read_text()


def test_delete_ignore_policy_only_affects_view(clients_csv: Path) -> None:
    view      = rf.Source(str(clients_csv), key="id").run()
    before    = clients_csv.read_text()
    view.delete(0, on_delete="ignore")
    assert len(view) == 3
    view.sync()
    assert clients_csv.read_text() == before  # source untouched


def test_delete_tombstone_policy_marks_instead_of_removing(tmp_path: Path) -> None:
    path = tmp_path / "clients.csv"
    path.write_text("id,name,deleted\n1,Martin,\n2,Smith,\n")
    view = rf.Source(str(path), key="id", tombstone_field="deleted").run()
    view.delete(0, on_delete="tombstone")
    view.sync()
    content = path.read_text()
    assert "1,Martin,True" in content
    assert "2,Smith," in content


def test_delete_tombstone_without_field_configured_raises(clients_csv: Path) -> None:
    view = rf.Source(str(clients_csv), key="id").run()
    with pytest.raises(ValueError, match="tombstone_field"):
        view.delete(0, on_delete="tombstone")


def test_delete_tombstone_field_not_a_column_raises(tmp_path: Path) -> None:
    path = tmp_path / "clients.csv"
    path.write_text("id,name\n1,Martin\n")
    view = rf.Source(str(path), key="id", tombstone_field="deleted").run()
    with pytest.raises(ValueError, match="isn't a column"):
        view.delete(0, on_delete="tombstone")


def test_delete_unknown_policy_raises(clients_csv: Path) -> None:
    view = rf.Source(str(clients_csv), key="id").run()
    with pytest.raises(ValueError, match="unknown on_delete policy"):
        view.delete(0, on_delete="bogus")
