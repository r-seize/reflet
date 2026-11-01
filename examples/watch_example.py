"""View.watch(): a polling loop that auto-syncs edits and flags external changes.

Run it directly:

    python examples/watch_example.py
"""

import shutil
import tempfile
from pathlib import Path

import reflet as rf

CLIENTS_CSV = str(Path(__file__).parent / "clients.csv")


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        scratch_csv = Path(tmp) / "clients.csv"
        shutil.copy(CLIENTS_CSV, scratch_csv)

        view = rf.Source(str(scratch_csv), key="id").run()

        print("-- watch() flushes a pending edit on its first tick --")
        view[0].name = "Watched"
        # max_iterations bounds the loop for this demo; omit it to watch forever
        # (interrupt with Ctrl-C) in a real long-running process.
        view.watch(interval=0.01, max_iterations=1)
        print(f"  synced: {'Watched' in scratch_csv.read_text()}")

        print()
        print("-- watch() calls on_change() for an external edit, instead of ignoring it --")
        with open(scratch_csv, "a") as fh:
            fh.write("5,External,BE,1\n")

        changes_seen = []
        view.watch(interval=0.01, max_iterations=1, on_change=lambda: changes_seen.append(1))
        print(f"  on_change called: {bool(changes_seen)}")


if __name__ == "__main__":
    main()
