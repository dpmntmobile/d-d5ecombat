"""Portable result records captured from the inputs used by a simulation."""

import csv
import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path

from . import __version__


def result_metadata(settings, characters, monsters, sections):
    """Snapshot effective profiles, including resource pools and overrides.

    Entries are (label, profile) pairs; labels identify rows in roster tables.
    These snapshots describe simulation models, not importable profile files.
    """
    return {
        "application_version": __version__,
        "settings": asdict(settings),
        "sections": list(sections),
        "characters": [
            {"label": label, "profile": asdict(profile)}
            for label, profile in characters
        ],
        "monsters": [
            {"label": label, "profile": asdict(profile)}
            for label, profile in monsters
        ],
        "seed_policy": "Each pair and independent scenario starts with the recorded seed.",
    }


def save_results(tables, path):
    """Write named tables and their run metadata as one atomic JSON document."""
    document = {"result_format_version": 1, "tables": {
        name: asdict(table) for name, table in tables.items() if table is not None
    }}
    content = json.dumps(document, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    path = Path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False,
        ) as output:
            temporary = Path(output.name)
            output.write(content)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return path


def save_table_csv(table, section, path):
    """Write raw CSV values and a complete .csv.json companion record."""
    path = Path(path)
    # Write metadata first so a metadata failure never reports a successful CSV.
    save_results({section: table}, path.with_suffix(path.suffix + ".json"))
    with path.open("w", encoding="utf-8-sig", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(column.title for column in table.columns)
        writer.writerows(table.rows)
    return path
