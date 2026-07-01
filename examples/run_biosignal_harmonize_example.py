#!/usr/bin/env python3
"""
Harmonize biosignals in a polysomnography (PSG) European Data Format (EDF) file.

Loads channel mappings from harmonized/Biosignal_schema.xlsx, renames labels to
harmonized names, resamples to harmonization sampling rates, and writes a new EDF
containing schema-mapped channels only.

Usage (single file, from repository root):
  python examples/run_biosignal_harmonize_example.py \\
    --dataset abc \\
    --input /path/to/source.edf \\
    --output /path/to/abc_harmonized.edf

Usage (batch):
  python examples/run_biosignal_harmonize_example.py \\
    --dataset abc \\
    --input-dir /path/to/edf_in \\
    --output-dir /path/to/edf_out

Cohort EDF files are not included; provide your own paths.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

EXAMPLES_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(EXAMPLES_DIR))

from harmonized_psg.biosignal_schema import (  # noqa: E402
    DATASET_KEYS,
    build_biosignal_mappings,
    load_biosignal_schema,
)
from harmonized_psg.biosignal_transform import harmonize_edf  # noqa: E402

REPO_ROOT = EXAMPLES_DIR.parent
DEFAULT_SCHEMA = REPO_ROOT / "harmonized" / "Biosignal_schema.xlsx"


def _harmonize_one(
    input_path: Path,
    output_path: Path,
    signals: dict,
    max_duration_h: float | None,
) -> tuple[bool, list]:
    ok, log = harmonize_edf(
        input_path,
        output_path,
        signals,
        max_duration_h=max_duration_h,
    )
    return ok, log


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Harmonize biosignals in a PSG EDF (rename + resample to harmonization sampling rates)"
    )
    parser.add_argument(
        "--dataset",
        required=True,
        choices=DATASET_KEYS,
        help="Cohort key matching Biosignal_schema.xlsx columns",
    )
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--input", type=Path, help="Input EDF path")
    parser.add_argument("--output", type=Path, help="Output harmonized EDF path")
    parser.add_argument(
        "--input-dir",
        type=Path,
        help="Directory of input EDF files (batch mode)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Directory for harmonized EDF outputs (batch mode)",
    )
    parser.add_argument(
        "--log-json",
        type=Path,
        help="Optional path to write per-channel transform log (single-file mode)",
    )
    parser.add_argument(
        "--max-duration-h",
        type=float,
        default=None,
        help="Skip files longer than this many hours",
    )
    args = parser.parse_args()

    schema_df = load_biosignal_schema(args.schema)
    signals = build_biosignal_mappings(schema_df, args.dataset)
    if not signals:
        raise SystemExit(f"No biosignal mappings found for dataset '{args.dataset}'")

    if args.input and args.output:
        ok, log = _harmonize_one(args.input, args.output, signals, args.max_duration_h)
        if not ok:
            raise SystemExit(f"Harmonization failed for {args.input}")
        print(f"Wrote {len(log)} channels -> {args.output}")
        if args.log_json:
            args.log_json.parent.mkdir(parents=True, exist_ok=True)
            args.log_json.write_text(json.dumps(log, indent=2), encoding="utf-8")
        return

    if args.input_dir and args.output_dir:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        edf_files = sorted(args.input_dir.glob("*.edf"))
        if not edf_files:
            raise SystemExit(f"No .edf files in {args.input_dir}")

        n_ok = 0
        for src in edf_files:
            dst = args.output_dir / f"{src.stem}_harmonized.edf"
            ok, log = _harmonize_one(src, dst, signals, args.max_duration_h)
            if ok:
                n_ok += 1
                print(f"{src.name}: {len(log)} channels -> {dst.name}")
            else:
                print(f"{src.name}: skipped or failed")
        print(f"Done: {n_ok}/{len(edf_files)} files")
        return

    raise SystemExit(
        "Provide either:\n"
        "  --input PATH --output PATH\n"
        "  --input-dir DIR --output-dir DIR"
    )


if __name__ == "__main__":
    main()
