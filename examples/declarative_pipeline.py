"""A pipeline described as JSON instead of Python: reflet.declarative.

Run it directly (the spec's "path" is relative to the current directory,
so run this from the repo root):

    python examples/declarative_pipeline.py

The CLI can run the spec directly too, without this wrapper script:

    python -m reflet show examples/declarative_pipeline.json
    python -m reflet why examples/declarative_pipeline.json 0 customer
"""

from reflet.declarative import pipeline_from_json


def main() -> None:
    pipeline = pipeline_from_json("examples/declarative_pipeline.json")
    view = pipeline.run()

    print("-- view produced by the declarative spec (filter + rename + map + sort) --")
    for row in view:
        print(f"  {row.customer}: {row.price}")


if __name__ == "__main__":
    main()
