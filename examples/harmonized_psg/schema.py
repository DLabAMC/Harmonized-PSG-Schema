"""Load rename mappings from harmonized/Sleep_schema.xlsx."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Tuple

import pandas as pd

_IDENTIFIER = re.compile(r"^[a-zA-Z0-9_]+$")
_FORMULA = re.compile(r"[*/+]")


def load_sleep_schema(schema_path: Path) -> pd.DataFrame:
    path = Path(schema_path)
    if not path.is_file():
        raise FileNotFoundError(f"Sleep schema not found: {path}")
    return pd.read_excel(path)


def build_parameter_mapping(
    schema_df: pd.DataFrame,
    dataset: str,
    *,
    harmonized_col: str = "Harmonized name",
) -> Tuple[Dict[str, str], Dict[str, str]]:
    """
    Build mappings for one open PSG dataset.

    Returns
    -------
    rename_mapping : dict
        Source CSV column name -> harmonized parameter name.
    derived_formulas : dict
        Harmonized parameter name -> pandas-eval expression using source columns.
    """
    dataset_key = dataset.upper()
    columns = {c.upper(): c for c in schema_df.columns}
    if dataset_key not in columns:
        known = [c for c in schema_df.columns if c not in (harmonized_col, "Event type")]
        raise KeyError(f"Dataset '{dataset}' not in schema columns: {known}")
    dataset_col = columns[dataset_key]

    rename_mapping: Dict[str, str] = {}
    derived_formulas: Dict[str, str] = {}

    for _, row in schema_df.iterrows():
        harm = row.get(harmonized_col)
        raw = row.get(dataset_col)
        if pd.isna(harm) or pd.isna(raw):
            continue

        harm_name = str(harm).strip()
        value = str(raw).strip()

        if _IDENTIFIER.match(value):
            rename_mapping[value] = harm_name
        elif _FORMULA.search(value):
            derived_formulas[harm_name] = value

    return rename_mapping, derived_formulas


def apply_derived_columns(
    df: pd.DataFrame,
    derived_formulas: Dict[str, str],
    rename_mapping: Dict[str, str],
) -> Tuple[pd.DataFrame, Dict[str, str]]:
    """Evaluate schema formulas, then register harmonized columns in rename_mapping."""
    if not derived_formulas:
        return df, rename_mapping

    out = df.copy()
    mapping = dict(rename_mapping)
    for harm_name, expr in derived_formulas.items():
        try:
            out[harm_name] = out.eval(expr)
        except Exception as exc:
            raise ValueError(
                f"Failed to evaluate derived parameter '{harm_name}' with expression '{expr}'"
            ) from exc
        mapping[harm_name] = harm_name

    return out, mapping
