"""Copy an existing database into a new data folder without replacing files."""

import argparse
import sqlite3
from pathlib import Path

import db


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--destination", type=Path, default=db.DB_PATH)
    args = parser.parse_args()
    source = args.source.resolve(strict=True)
    target = args.destination.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        parser.error("The destination already exists. Choose a new data folder.")
    with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as existing:
        if existing.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            parser.error("The source database did not pass its integrity check.")
        columns = {row[1] for row in existing.execute("PRAGMA table_info(tasks)")}
        if not {"id", "title", "pillar", "status"}.issubset(columns):
            parser.error("This is not an ADHD HQ task database.")
        with target.open("xb"):
            pass
        with sqlite3.connect(target) as destination:
            existing.backup(destination)
    print(f"Copied database to {target}. The original was left in place.")


if __name__ == "__main__":
    main()
