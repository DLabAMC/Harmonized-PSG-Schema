"""CSV -> harmonized sleep-record JSON (sleep parameters + demographics)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import yaml

from .schema import (
    apply_derived_columns,
    build_parameter_mapping,
    load_sleep_schema,
)


def _inches_to_cm(value: float) -> float:
    return value * 2.54


def _pounds_to_kg(value: float) -> float:
    return value * 0.45359237


def _try_cast_numeric(val: Any) -> Any:
    if isinstance(val, str):
        try:
            return float(val) if "." in val else int(val)
        except ValueError:
            return val
    return val


def _try_cast_numeric_or_none(val: Any) -> Any:
    if isinstance(val, str):
        try:
            return float(val) if "." in val else int(val)
        except ValueError:
            return None
    return val


def _add_edf_path(filename: str, db_name: str) -> str:
    if db_name == "apple":
        return f"{db_name}/{filename}.edf"
    return f"{db_name}/{filename}"


@dataclass
class HarmonizeConfig:
    """Per-dataset column names for demographics and file linkage."""

    db_name: str
    edf_path_column: str
    subject_id_column: str
    visit_column: str = ""
    age_column: str = ""
    sex_column: str = ""
    weight_column: str = ""
    height_column: str = ""
    bmi_column: str = ""
    fill_visit_level_demographics: bool = False
    height_inches_to_cm: bool = False
    weight_pounds_to_kg: bool = False


def load_dataset_config(config_path: Path, dataset: str) -> HarmonizeConfig:
    path = Path(config_path)
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if dataset not in data:
        raise KeyError(f"Dataset '{dataset}' not defined in {path}")
    return HarmonizeConfig(**data[dataset])


def harmonize_csv_to_json(
    csv_path: Path,
    output_json_path: Path,
    *,
    schema_path: Path,
    dataset_config: HarmonizeConfig,
    low_memory: bool = False,
) -> List[Dict[str, Any]]:
    """
    Harmonize one dataset CSV into sleep-record JSON objects.

    Each record contains harmonized demographics and a ``parameter_value`` dict.
    """
    schema_df = load_sleep_schema(schema_path)
    rename_mapping, derived = build_parameter_mapping(schema_df, dataset_config.db_name)

    full_df = pd.read_csv(csv_path, low_memory=low_memory)
    full_df.columns = [c.strip() for c in full_df.columns]
    full_df = full_df.loc[:, ~full_df.columns.duplicated()]

    cfg = dataset_config
    if cfg.fill_visit_level_demographics:
        for col in (cfg.bmi_column, cfg.weight_column, cfg.height_column):
            if col:
                full_df[col] = full_df.groupby(cfg.subject_id_column)[col].transform("first")

    working = full_df.dropna(subset=[cfg.edf_path_column]).copy()
    working[cfg.edf_path_column] = working[cfg.edf_path_column].apply(
        _add_edf_path, args=(cfg.db_name,)
    )

    working, rename_mapping = apply_derived_columns(working, derived, rename_mapping)

    meta_cols = [
        c
        for c in [
            cfg.edf_path_column,
            cfg.subject_id_column,
            cfg.visit_column,
            cfg.age_column,
            cfg.sex_column,
            cfg.weight_column,
            cfg.height_column,
            cfg.bmi_column,
        ]
        if c
    ]
    param_sources = [c for c in rename_mapping.keys() if c in working.columns]
    subset_cols = meta_cols + param_sources
    subset = working[subset_cols]
    if param_sources:
        subset = subset.dropna(subset=param_sources, how="all")

    if cfg.height_inches_to_cm and cfg.height_column:
        subset[cfg.height_column] = subset[cfg.height_column].apply(_inches_to_cm)
    if cfg.weight_pounds_to_kg and cfg.weight_column:
        subset[cfg.weight_column] = subset[cfg.weight_column].apply(_pounds_to_kg)

    if cfg.visit_column:
        rename_dict = {
            cfg.subject_id_column: "subject_id",
            cfg.visit_column: "visit_num",
            cfg.age_column: "age",
            cfg.sex_column: "sex",
            cfg.weight_column: "weight",
            cfg.height_column: "height",
            cfg.bmi_column: "bmi",
            cfg.edf_path_column: "edf_path",
        }
    else:
        rename_dict = {
            cfg.subject_id_column: "subject_id",
            cfg.age_column: "age",
            cfg.sex_column: "sex",
            cfg.weight_column: "weight",
            cfg.height_column: "height",
            cfg.bmi_column: "bmi",
            cfg.edf_path_column: "edf_path",
        }
    rename_dict = {k: v for k, v in rename_dict.items() if k}
    info_cols = list(rename_dict.values())
    harmonized_param_names = list(rename_mapping.values())

    rename_dict.update(rename_mapping)
    final_df = subset.rename(columns=rename_dict)

    records: List[Dict[str, Any]] = []
    for _, row in final_df.iterrows():
        record: Dict[str, Any] = {"db_name": cfg.db_name}

        if not row[info_cols].isna().all():
            info = row[info_cols].dropna().apply(_try_cast_numeric)
            record.update(info.to_dict())

        param_cols = [c for c in harmonized_param_names if c in final_df.columns]
        if param_cols and not row[param_cols].isna().all():
            params = row[param_cols].dropna().apply(_try_cast_numeric_or_none).dropna()
            record["parameter_value"] = params.to_dict()

        records.append(record)

    output_json_path = Path(output_json_path)
    output_json_path.parent.mkdir(parents=True, exist_ok=True)
    with output_json_path.open("w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    return records
