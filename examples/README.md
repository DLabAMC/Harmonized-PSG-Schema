# Harmonization examples (biosignals, sleep parameters, demographics)

This folder shows how to apply the harmonized schema in [`../harmonized/`](../harmonized/) to multi-cohort polysomnography (PSG) data. The schema and `datasets.yaml` column mappings were derived from eight publicly available cohorts (ABC, APPLE, CFS, MESA, MrOS, SHHS, SOF, WSC); the same scripts apply to any source that exposes the required columns.

Commands below are run from the **repository root** (the directory that contains `examples/` and `harmonized/`).

## What this repository provides

| Included | Not included |
|----------|----------------|
| Schema workbooks (`Biosignal_schema.xlsx`, `Sleep_schema.xlsx`, `Demographic_schema.xlsx`, …) | Cohort comma-separated values (CSV) or European Data Format (EDF) files |
| Python mapping code (`harmonized_psg/`) | Cohort-specific data cleaning beyond a simple template |
| Example harmonize scripts | Guaranteed filenames/versions (repository releases change) |

## Pipeline overview

Biosignals and tabular fields are harmonized on **separate paths**:

```
Your data                         This repository
─────────                         ─────────────────
PSG EDF (one file per record) ──► harmonized EDF
                                  ↑ Step 1 · Biosignal_schema.xlsx

Wide CSV (one row per record) ──► Sleep Record JSON (JavaScript Object Notation, JSON)
  sleep parameters + demographics ↑ Step 2 · Sleep_schema.xlsx + datasets.yaml
```

- **Step 1** — harmonize biosignals in EDF files ([below](#step-1--harmonize-biosignals-in-edf-schema-driven)).
- **Step 2** — harmonize sleep parameters and demographics from **one wide CSV per cohort** ([below](#step-2--harmonize-to-sleep-record-json-schema-driven)). Use your table as-is when it is already a single file. If your source splits tabular exports into multiple files (e.g. the National Sleep Research Resource (NSRR)), combine them into one wide CSV first ([Optional — NSRR](#optional--nsrr-merging-split-csv-exports)).

![Application overview](../images/userguide_overview.svg)

---

## Step 1 — Harmonize biosignals in European Data Format (EDF) files (schema-driven)

Channel mappings and **harmonization sampling rates (Hz)** are loaded from [`Biosignal_schema.xlsx`](../harmonized/Biosignal_schema.xlsx). For each cohort column (e.g. `ABC`), original EDF labels map to harmonized names; comma-separated labels in a cell are alternate names for the same signal.

The script:

1. Reads your PSG EDF
2. Renames mapped channels to harmonized names
3. Resamples each channel to its harmonization sampling rate from the schema
4. Writes a **new EDF containing schema-mapped channels only** (unmapped channels are dropped)

### Single file

```bash
pip install -r requirements.txt

python examples/run_biosignal_harmonize_example.py \
  --dataset abc \
  --input /path/to/source.edf \
  --output /path/to/work/abc_harmonized.edf
```

### Batch mode

```bash
python examples/run_biosignal_harmonize_example.py \
  --dataset abc \
  --input-dir /path/to/edf_in \
  --output-dir /path/to/edf_out
```

Outputs are named `{stem}_harmonized.edf`. Use `--max-duration-h` to skip recordings longer than a threshold.

### Python API

```python
from pathlib import Path
from harmonized_psg import build_biosignal_mappings, harmonize_edf, load_biosignal_schema

schema = load_biosignal_schema(Path("../harmonized/Biosignal_schema.xlsx"))
signals = build_biosignal_mappings(schema, "abc")
ok, log = harmonize_edf("in.edf", "out.edf", signals)
```

---

## Step 2 — Harmonize to Sleep Record JSON (schema-driven)

**Input:** one wide CSV per cohort — one row per sleep record, with dataset-specific column names for sleep analysis parameters and demographics. Column names for each cohort are listed in [`config/datasets.yaml`](config/datasets.yaml); harmonized field names come from [`Sleep_schema.xlsx`](../harmonized/Sleep_schema.xlsx) and [`Demographic_schema.xlsx`](../harmonized/Demographic_schema.xlsx).

`--dataset` must match a key in `datasets.yaml` (`abc`, `apple`, `cfs`, `mesa`, `shhs`, `sof`, `wsc`, `mros`).

```bash
python examples/run_harmonize_example.py \
  --dataset abc \
  --csv /path/to/your/abc_cohort.csv

python examples/run_harmonize_example.py \
  --dataset mesa \
  --csv /path/to/your/mesa_cohort.csv
```

Optional: if cohort CSVs are named `{dataset}.csv` or `{dataset}_merged.csv` in one folder:

```bash
# Windows
set USER_DATA_DIR=C:\path\to\work
# Linux / macOS
export USER_DATA_DIR=/path/to/work

python examples/run_harmonize_example.py --dataset abc
python examples/run_harmonize_example.py --dataset apple
```

Default JSON output: `output/<dataset>_harmonized.json`

---

## Optional — NSRR: merging split CSV exports

The eight schema cohorts were accessed via NSRR. **NSRR distributes tabular data as separate exports** — typically a harmonized summary CSV and a study-specific dataset CSV — rather than one combined file. This is an NSRR-specific layout; most other sources provide a single table.

If you download from NSRR, register, accept each study’s terms, and merge split exports into one wide CSV before running Step 2. Illustrative filenames: [`config/nsrr_csv_sources.yaml`](config/nsrr_csv_sources.yaml). PSG EDFs are downloaded separately from each study’s data browser.

### ABC and most cohorts (column bind, same row order)

```bash
python examples/merge_nsrr_csv.py \
  --harmonized /path/to/abc-baseline-harmonized-0.4.0.csv \
  --dataset-csv /path/to/abc-baseline-dataset-0.4.0.csv \
  --output /path/to/work/abc_merged.csv

python examples/run_harmonize_example.py \
  --dataset abc \
  --csv /path/to/work/abc_merged.csv
```

The same merge pattern applies to APPLE, CFS, MESA, SOF, and WSC with that cohort’s harmonized/dataset pair.

### SHHS / MrOS (multiple dataset files or key merge)

- **SHHS**: stack `shhs1-` and `shhs2-` dataset CSVs (assign `visitnumber`), merge with harmonized CSV on `nsrrid` + `visitnumber`, then add `weight_all` / `height_all` before harmonization (`datasets.yaml` expects those columns).
- **MrOS**: stack visit1/visit2 dataset CSVs, merge harmonized visit1 file on `nsrrid` + `visit`.

Example (SHHS):

```bash
python examples/merge_nsrr_csv.py \
  --harmonized /path/to/shhs-harmonized-dataset-0.20.0.csv \
  --dataset-csv /path/to/shhs1-dataset-0.20.0.csv \
  --dataset-csv /path/to/shhs2-dataset-0.20.0.csv \
  --visitnumber 1 2 \
  --merge-on nsrrid visitnumber \
  --encoding cp1252 \
  --output /path/to/work/shhs_merged.csv
```

Cohort-specific cleaning beyond this template is **your responsibility** (the published example only documents the common NSRR structure).

---

## Configuration (user)

| File | Role |
|------|------|
| [`../harmonized/Biosignal_schema.xlsx`](../harmonized/Biosignal_schema.xlsx) | **Required for biosignal harmonize** — channel labels and harmonization sampling rates |
| [`../harmonized/Sleep_schema.xlsx`](../harmonized/Sleep_schema.xlsx) | **Required for tabular harmonize** — sleep parameter name mapping |
| [`../harmonized/Demographic_schema.xlsx`](../harmonized/Demographic_schema.xlsx) | Documentation of harmonized demographic fields |
| [`config/datasets.yaml`](config/datasets.yaml) | **Required for tabular harmonize** — which CSV columns hold demographics / `edf_path` per cohort |
| [`config/nsrr_csv_sources.yaml`](config/nsrr_csv_sources.yaml) | **Reference only (NSRR)** — example split export names per cohort |
