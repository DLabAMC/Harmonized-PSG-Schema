"""Load biosignal channel mappings from harmonized/Biosignal_schema.xlsx."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

import pandas as pd

HARMONIZED_COL = "Harmonized Name"
HARMONIZATION_SAMPLING_RATE_COL = "Harmonization sampling rate (Hz)"
_LEGACY_HARMONIZATION_SAMPLING_RATE_COL = "Harmonization target rate (Hz)"

DATASET_KEYS = ("abc", "apple", "cfs", "mesa", "mros", "shhs", "sof", "wsc")
SCHEMA_COLUMNS = {
    "abc": "ABC",
    "apple": "APPLE",
    "cfs": "CFS",
    "mesa": "MESA",
    "mros": "MrOS",
    "shhs": "SHHS",
    "sof": "SOF",
    "wsc": "WSC",
}

_AIRFLOW_PRIMARY_LABELS = frozenset({"NEW AIR", "NEWAIR"})
_AIRFLOW_ALTERNATE_LABEL = "AIRFLOW"


def load_biosignal_schema(schema_path: Path) -> pd.DataFrame:
    path = Path(schema_path)
    if not path.is_file():
        raise FileNotFoundError(f"Biosignal schema not found: {path}")
    return pd.read_excel(path)


def _sampling_rate_column(schema_df: pd.DataFrame) -> str:
    for col in (
        HARMONIZATION_SAMPLING_RATE_COL,
        _LEGACY_HARMONIZATION_SAMPLING_RATE_COL,
    ):
        if col in schema_df.columns:
            return col
    raise KeyError(
        "Biosignal schema must include a harmonization sampling rate column "
        f"({HARMONIZATION_SAMPLING_RATE_COL!r} or "
        f"{_LEGACY_HARMONIZATION_SAMPLING_RATE_COL!r}). "
        f"Found columns: {list(schema_df.columns)}"
    )


def build_biosignal_mappings(
    schema_df: pd.DataFrame,
    dataset: str,
) -> dict[str, dict[str, object]]:
    """
    Build original EDF label -> {new_rate, new_name} for one cohort.

    Multiple original labels (comma-separated in the schema) may map to the
    same harmonized name; the transform step keeps the first matching channel
    in the source EDF.
    """
    key = dataset.lower()
    if key not in SCHEMA_COLUMNS:
        raise KeyError(f"Unknown dataset '{dataset}'. Expected one of {DATASET_KEYS}")
    column = SCHEMA_COLUMNS[key]
    if column not in schema_df.columns:
        raise KeyError(
            f"Biosignal schema is missing cohort column {column!r} for dataset {dataset!r}. "
            f"Found columns: {list(schema_df.columns)}"
        )
    if HARMONIZED_COL not in schema_df.columns:
        raise KeyError(
            f"Biosignal schema is missing {HARMONIZED_COL!r}. "
            f"Found columns: {list(schema_df.columns)}"
        )
    rate_col = _sampling_rate_column(schema_df)

    mappings: dict[str, dict[str, object]] = {}
    for _, row in schema_df.iterrows():
        harm = row.get(HARMONIZED_COL)
        rate = row.get(rate_col)
        raw = row.get(column)
        if pd.isna(harm) or pd.isna(rate) or pd.isna(raw):
            continue

        harm_name = str(harm).strip()
        harmonization_sampling_rate = int(rate)
        for part in str(raw).split(","):
            label = part.strip()
            if label:
                mappings[label] = {
                    "new_rate": harmonization_sampling_rate,
                    "new_name": harm_name,
                }
    return mappings


def build_name_map(signals: Mapping[str, Mapping[str, object]]) -> dict[str, str]:
    return {label: str(spec["new_name"]) for label, spec in signals.items()}


def resolve_signals_for_file(
    labels: list[str] | tuple[str, ...],
    signals_to_modify: Mapping[str, Mapping[str, object]],
) -> dict[str, dict]:
    """SHHS: when NEW AIR and AIRFLOW coexist, keep primary airflow mapping only."""
    out = dict(signals_to_modify)
    label_set = {lbl.strip() for lbl in labels}
    has_primary = bool(label_set & _AIRFLOW_PRIMARY_LABELS)
    alt = _AIRFLOW_ALTERNATE_LABEL
    if not has_primary or alt not in label_set or alt not in out:
        return out
    primary_name = None
    for pl in _AIRFLOW_PRIMARY_LABELS:
        if pl in out:
            primary_name = out[pl].get("new_name")
            break
    if primary_name and out[alt].get("new_name") == primary_name:
        del out[alt]
    return out
