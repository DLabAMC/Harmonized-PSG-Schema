#!/usr/bin/env python3
"""
Harmonize sleep parameters and demographics from a wide CSV to JSON.

Reads one comma-separated values (CSV) table per cohort (one row per sleep record),
maps dataset-specific column names via examples/config/datasets.yaml and
harmonized/Sleep_schema.xlsx, and writes Sleep Record JSON (JavaScript Object
Notation, JSON) — one object per row with harmonized demographics and
parameter_value fields.

Usage (from repository root):
  python examples/run_harmonize_example.py \\
    --dataset abc \\
    --csv /path/to/your/abc_cohort.csv

Optional: set USER_DATA_DIR to a folder containing {dataset}.csv or
{dataset}_merged.csv, then omit --csv.

If your source is the National Sleep Research Resource (NSRR), merge split tabular
exports first — see merge_nsrr_csv.py and examples/README.md.

Cohort data are not included; provide your own CSV paths.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

EXAMPLES_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(EXAMPLES_DIR))

from harmonized_psg import harmonize_csv_to_json, load_dataset_config

REPO_ROOT = EXAMPLES_DIR.parent
DEFAULT_SCHEMA = REPO_ROOT / "harmonized" / "Sleep_schema.xlsx"
DEFAULT_CONFIG = EXAMPLES_DIR / "config" / "datasets.yaml"


def resolve_csv_path(dataset: str, csv_arg: Path | None) -> Path:
    if csv_arg is not None:
        return csv_arg

    user_data_dir = os.environ.get("USER_DATA_DIR")
    if user_data_dir:
        base = Path(user_data_dir)
        for name in (f"{dataset}.csv", f"{dataset}_merged.csv"):
            candidate = base / name
            if candidate.is_file():
                return candidate
        return base / f"{dataset}.csv"

    raise SystemExit(
        "Cohort CSV is required.\n"
        "  --csv /path/to/your/<cohort>.csv\n"
        "  or USER_DATA_DIR with {dataset}.csv or {dataset}_merged.csv"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Harmonize sleep parameters + demographics (CSV → JSON)"
    )
    parser.add_argument(
        "--dataset",
        default="abc",
        help="Dataset key in examples/config/datasets.yaml (default: abc)",
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=None,
        help="Wide cohort CSV (optional if USER_DATA_DIR is set)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output JSON path (default: output/<dataset>_harmonized.json)",
    )
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()

    csv_path = resolve_csv_path(args.dataset, args.csv)
    if not csv_path.is_file():
        raise SystemExit(f"CSV not found: {csv_path}")

    output_path = args.output or (REPO_ROOT / "output" / f"{args.dataset}_harmonized.json")

    dataset_config = load_dataset_config(args.config, args.dataset)
    records = harmonize_csv_to_json(
        csv_path,
        output_path,
        schema_path=args.schema,
        dataset_config=dataset_config,
    )
    print(f"Wrote {len(records)} records -> {output_path}")


if __name__ == "__main__":
    main()
