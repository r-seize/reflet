from __future__ import annotations

from pathlib import Path

import pytest

import reflet as rf
from reflet.errors import ConflictError, ReadOnlyFieldError


def test_why_reports_source_and_steps(clients_csv: Path) -> None:
    pipeline = rf.Source(str(clients_csv)).rename(customer="name").map(
        "price", fwd=lambda x: x * 1.2, bwd=lambda x: x / 1.2
    )
    view    = pipeline.run()
    why     = view[0].customer.why()
    assert str(clients_csv) in why
    assert "name" in why
    assert "rename" in why

    price_why = view[0].price.why()
    assert "map(price)" in price_why


def test_why_reflects_edit_step(clients_csv: Path) -> None:
    pipeline       = rf.Source(str(clients_csv)).rename(customer="name")
    view           = pipeline.run()
    view[0].customer    = "Changed"
    assert "edit" in view[0].customer.why()


def test_constant_field_raises_on_edit(clients_csv: Path) -> None:
    pipeline    = rf.Source(str(clients_csv)).constant("currency", "EUR")
    view        = pipeline.run()
    with pytest.raises(ReadOnlyFieldError):
        view[0].currency = "USD"


def test_compute_field_raises_on_edit(clients_csv: Path) -> None:
    pipeline    = rf.Source(str(clients_csv)).compute("tax", lambda r: r.price * 0.2)
    view        = pipeline.run()
    with pytest.raises(ReadOnlyFieldError):
        view[0].tax = 100


def test_aggregate_default_error_policy_raises_on_ambiguous_edit(clients_csv: Path) -> None:
    pipeline = rf.Source(str(clients_csv)).aggregate(
        "country", "total_price", sum, source_field="price"
    )
    view      = pipeline.run()
    fr_row    = next(row for row in view if str(row.country) == "FR")
    with pytest.raises(ConflictError):
        fr_row.country = "BE"


def test_aggregate_first_policy_allows_edit_and_syncs(clients_csv: Path) -> None:
    pipeline = rf.Source(str(clients_csv)).aggregate(
        "country", "total_price", sum, source_field="price", policy=rf.ConflictPolicy.FIRST
    )
    view              = pipeline.run()
    fr_row            = next(row for row in view if str(row.country) == "FR")
    fr_row.country    = "BE"
    view.sync()
    content = clients_csv.read_text()
    assert "BE" in content
