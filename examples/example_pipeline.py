"""Runnable example matching the README's target API.

Run it directly:

    python examples/example_pipeline.py

Or inspect it with the CLI:

    python -m reflet show examples/example_pipeline.py
    python -m reflet show examples/example_pipeline.py --json
    python -m reflet why examples/example_pipeline.py 0 customer
    python -m reflet fields examples/example_pipeline.py
"""

import shutil
import tempfile
from pathlib import Path

import reflet as rf

CLIENTS_CSV = str(Path(__file__).parent / "clients.csv")

pipeline = (
    rf.Source(CLIENTS_CSV)
    .filter(lambda r: r.country == "FR")
    .rename(customer="name")
    .map("price", fwd=lambda x: x * 1.2, bwd=lambda x: x / 1.2)
)


def main() -> None:
    # `show`/`why` just read the source; running the demo end-to-end also
    # syncs an edit back, so do that against a scratch copy to keep
    # examples/clients.csv pristine for repeat runs.
    with tempfile.TemporaryDirectory() as tmp:
        scratch_csv = Path(tmp) / "clients.csv"
        shutil.copy(CLIENTS_CSV, scratch_csv)
        demo_pipeline = (
            rf.Source(str(scratch_csv))
            .filter(lambda r: r.country == "FR")
            .rename(customer="name")
            .map("price", fwd=lambda x: x * 1.2, bwd=lambda x: x / 1.2)
        )
        _run_demo(demo_pipeline, str(scratch_csv))


def _run_demo(demo_pipeline: rf.Pipeline, scratch_csv: str) -> None:
    view = demo_pipeline.run()

    print("-- view (FR clients, price with 20% markup) --")
    for row in view:
        print(f"  {row.customer}: {row.price}")

    print()
    print("-- editing row 0's name and syncing back to the CSV --")
    view[0].customer = "Dupont"
    view.sync()
    print(f"  wrote back to {scratch_csv}")

    print()
    print("-- provenance of that edited cell --")
    print(f"  {view[0].customer.why()}")

    print()
    print("-- ergonomics: repr(), .rows, .to_dicts(), and the context manager --")
    print(f"  {demo_pipeline!r}")
    print(f"  {view!r}")
    print(f"  view.rows[0] -> {view.rows[0]}")
    print(f"  view.to_dicts()[0] -> {view.to_dicts()[0]}")
    with rf.Source(scratch_csv).filter(lambda r: r.country == "FR").run() as ctx_view:
        ctx_view[0].name = "Lefevre"
    print("  `with ...run() as view:` synced automatically on exit")


if __name__ == "__main__":
    main()
