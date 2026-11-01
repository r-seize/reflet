"""join(): inner join against another pipeline, by key.

Run it directly:

    python examples/join_example.py
"""

from pathlib import Path

import reflet as rf
from reflet.errors import ReadOnlyFieldError

CLIENTS_CSV = str(Path(__file__).parent / "clients.csv")
ORDERS_CSV = str(Path(__file__).parent / "orders.csv")

orders = rf.Source(ORDERS_CSV, key="order_id")

pipeline = rf.Source(CLIENTS_CSV, key="id").join(
    orders, on="id", other_on="client_id", prefix="order_"
)


def main() -> None:
    view = pipeline.run()

    print("-- inner join: only clients with a matching order --")
    for row in view:
        print(f"  {row.name} (country={row.country}): order amount = {row.order_amount}")

    print()
    print("-- left-hand fields stay writable --")
    print(f"  provenance of a left field: {view[0].name.why()}")
    print(f"  provenance of a joined-in field: {view[0].order_amount.why()}")

    print()
    print("-- right-hand fields are read-only (no two-way join yet; see README) --")
    try:
        view[0].order_amount = 999
    except ReadOnlyFieldError as exc:
        print(f"  ReadOnlyFieldError: {exc}")


if __name__ == "__main__":
    main()
