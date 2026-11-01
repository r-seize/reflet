"""Provenance, validation, and tracing a view: .why(), .validate(), why_not(), impact().

Run it directly:

    python examples/provenance_and_validation.py
"""

from pathlib import Path

import reflet as rf
from reflet.errors import ValidationError

CLIENTS_CSV = str(Path(__file__).parent / "clients.csv")

pipeline = (
    rf.Source(CLIENTS_CSV, key="id")
    .filter(lambda r: r.country == "FR")
    .rename(customer="name")
    .compute("tax", lambda r: r.price * 0.2)
    .validate("price", lambda x: x > 0, "price must be positive")
)


def main() -> None:
    view = pipeline.run()

    print("-- .why(): where a field's value came from --")
    print(f"  {view[0].customer.why()}")
    print(f"  {view[0].tax.why()}")

    print()
    print("-- .validate(): rejected before it ever reaches the source --")
    try:
        view[0].price = -5
    except ValidationError as exc:
        print(f"  ValidationError: {exc}")

    print()
    print("-- why_not(): why isn't id=2 (Smith, UK) in this FR-only view? --")
    print(f"  {view.why_not(2)}")
    print("-- ...and id=1 (Martin, FR), which is in the view? --")
    print(f"  {view.why_not(1)}")

    print()
    print("-- impact(): what in the view came from source[1]['price']? --")
    print(f"  {view.impact(1, 'price')}")


if __name__ == "__main__":
    main()
