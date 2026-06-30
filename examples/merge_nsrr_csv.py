#!/usr/bin/env python3
"""
Optional: merge National Sleep Research Resource (NSRR) split CSV exports.

NSRR often provides tabular data as two files per cohort — a harmonized summary CSV
and a study-specific dataset CSV. This script combines them into one wide CSV for
run_harmonize_example.py. Skip this step if you already have a single cohort table.

Usage (ABC-style column bind, from repository root):
  python examples/merge_nsrr_csv.py \\
    --harmonized /path/to/abc-baseline-harmonized-0.4.0.csv \\
    --dataset-csv /path/to/abc-baseline-dataset-0.4.0.csv \\
    --output /path/to/work/abc_merged.csv

  python examples/run_harmonize_example.py \\
    --dataset abc --csv /path/to/work/abc_merged.csv

For SHHS/MrOS key-based merges, use --merge-on and/or multiple --dataset-csv.
Example filenames: config/nsrr_csv_sources.yaml
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def read_csv(path: Path, encoding: str | None) -> pd.DataFrame:
    kwargs = {}
    if encoding:
        kwargs["encoding"] = encoding
    return pd.read_csv(path, **kwargs)


def merge_concat(harmonized: pd.DataFrame, dataset: pd.DataFrame) -> pd.DataFrame:
    if len(harmonized) != len(dataset):
        raise ValueError(
            f"Row count mismatch: harmonized={len(harmonized)}, dataset={len(dataset)}. "
            "Use --merge-on if tables must be joined by keys (e.g. SHHS, MrOS)."
        )
    merged = pd.concat([harmonized, dataset], axis=1)
    return merged.loc[:, ~merged.columns.duplicated()]


def merge_on_keys(
    harmonized: pd.DataFrame,
    dataset: pd.DataFrame,
    keys: list[str],
    how: str,
) -> pd.DataFrame:
    missing = [k for k in keys if k not in harmonized.columns or k not in dataset.columns]
    if missing:
        raise KeyError(f"Merge keys not found in both CSVs: {missing}")
    return pd.merge(harmonized, dataset, on=keys, how=how)


def stack_dataset_csvs(paths: list[Path], encoding: str | None) -> pd.DataFrame:
    frames = [read_csv(p, encoding) for p in paths]
    return pd.concat(frames, ignore_index=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Merge NSRR harmonized + dataset CSV files into one wide table"
    )
    parser.add_argument(
        "--harmonized",
        type=Path,
        required=True,
        help="Path to NSRR *-harmonized-*.csv from your download",
    )
    parser.add_argument(
        "--dataset-csv",
        type=Path,
        action="append",
        required=True,
        help="Path to NSRR *-dataset-*.csv (repeat for multi-file cohorts, e.g. SHHS)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Merged wide CSV to pass to run_harmonize_example.py --csv",
    )
    parser.add_argument(
        "--merge-on",
        nargs="+",
        default=None,
        help="Join keys (e.g. nsrrid visitnumber). Default: column-wise concat (same row order)",
    )
    parser.add_argument(
        "--how",
        default="outer",
        choices=["inner", "outer", "left", "right"],
        help="pandas merge how= (only with --merge-on)",
    )
    parser.add_argument(
        "--encoding",
        default=None,
        help="Optional encoding for dataset CSV (e.g. cp1252 for some SHHS exports)",
    )
    parser.add_argument(
        "--visitnumber",
        type=int,
        nargs="+",
        default=None,
        help="When stacking multiple --dataset-csv files, assign visitnumber per file (SHHS: 1 2)",
    )
    args = parser.parse_args()

    harmonized = read_csv(args.harmonized, None)

    if len(args.dataset_csv) == 1:
        dataset = read_csv(args.dataset_csv[0], args.encoding)
    else:
        frames = []
        for i, path in enumerate(args.dataset_csv):
            df = read_csv(path, args.encoding)
            if args.visitnumber and i < len(args.visitnumber):
                df = df.copy()
                df["visitnumber"] = args.visitnumber[i]
            frames.append(df)
        dataset = pd.concat(frames, ignore_index=True)

    if args.merge_on:
        merged = merge_on_keys(harmonized, dataset, args.merge_on, args.how)
    else:
        merged = merge_concat(harmonized, dataset)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(args.output, index=False)
    print(f"Wrote {merged.shape[0]} rows x {merged.shape[1]} cols -> {args.output}")


if __name__ == "__main__":
    main()
