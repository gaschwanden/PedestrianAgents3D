"""CSV tables with a units row, so no numeric column is left unlabelled (X-08)."""
from __future__ import annotations

import csv
import os
from typing import Dict, Iterable, List, Sequence


def write_table(path: str, columns: Sequence[str], rows: Iterable[Sequence],
                units: Dict[str, str]) -> str:
    """Write UTF-8 CSV: header, a ``unit`` row, then the data.

    Every column must have an entry in ``units``. Use ``""`` for text.
    """
    missing = [c for c in columns if c not in units]
    if missing:
        raise ValueError(f"columns without units: {', '.join(missing)}")
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(list(columns))
        writer.writerow(["unit"] + [units[c] for c in columns[1:]] if columns[:1] == ["unit"]
                        else [units[c] for c in columns])
        for row in rows:
            writer.writerow(list(row))
    return path


def read_table(path: str) -> List[Dict[str, str]]:
    """Read a table written by :func:`write_table`, skipping the units row."""
    with open(path, "r", encoding="utf-8", newline="") as fh:
        reader = csv.reader(fh)
        header = next(reader)
        units = next(reader)
        if units and units[0] not in ("unit", "") and not _looks_like_units(units):
            # A file that is not one of ours: treat the second row as data.
            rows = [units]
        else:
            rows = []
        rows.extend(reader)
    out = []
    for row in rows:
        if row and row[0] == "unit":
            continue
        padded = row + [""] * (len(header) - len(row))
        out.append({header[i]: padded[i] for i in range(len(header))})
    return out


def _looks_like_units(row: Sequence[str]) -> bool:
    tokens = {"", "unit", "min", "h", "km", "m", "persons", "1", "ratio",
              "trips/cell/day", "probability", "kg", "count", "m2", "ha"}
    return all(cell in tokens or cell.endswith("/day") or cell.startswith("unit")
               for cell in row)
