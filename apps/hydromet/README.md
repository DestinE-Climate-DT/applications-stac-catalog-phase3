# HydroMet

**Collection ID:** `EO.DWD.STAT.HYDROMET_EXTREMES`  
**Responsible:** Carl Hartick (DWD)  
**Description:** Catalog of extreme precipitation events from DestinE Climate DT simulations.
Historical (1990–2014) and projection (2015–2049) at ~5 km resolution using ICON, IFS-FESOM, IFS-NEMO models.

## Files

| File | Purpose |
|---|---|
| `catalog_config.yaml` | All collection metadata — id, title, description, license, providers, keywords, simulations, datacube |
| `staging/stage.py` | Writes `collection.json` + `collection_config.json`, creates STAC folder skeleton |
| `staging/move.py` | Copies/links/moves source NetCDF and CSV files into the STAC `data/YYYY/<item>/` layout |
| `staging/update.py` | Generates one `metadata/items/<item>.json` per data folder |
| `staging/check_data.sh` | Pre-staging quality check — counts files per model directory |
| `staging/delete_s3_collection_prefix.py` | Maintenance utility: deletes the collection prefix from S3 |

## What the scripts do

**`stage.py`** — loads `catalog_config.yaml` via `stac_dedl_core.load_app_config` (simulation
keys resolved against `apps/_shared/simulations.yaml`), writes `metadata/collection.json`
and `metadata/collection_config.json`, and creates one item folder skeleton per simulation
under `data/YYYY/`. Dry run by default; `--execute` applies.

**`move.py`** — moves source NetCDF and CSV files into the staged `data/YYYY/<item>/` layout.
Accepts `--source-dir`, `--target-collection-dir`, plus `--model/--experiment/--generation/
--realization/--resolution` to tag the items. A year-based rule assigns experiment: years
≤ 2014 → `baseline`/`hist`/1990–2014, otherwise `projections`/`SSP3-7.0`/2015–2049.
Modes: `--link` (symlink), `--copy`, or `--move`. Dry run by default; `--execute` applies.

**`update.py`** — runs `stac_dedl_core.ItemGenerator` to write a STAC item JSON for every
folder under `data/` that contains assets. Empty-asset folders are removed afterwards.

**`delete_s3_collection_prefix.py`** — maintenance utility: lists all S3 objects under
`<collection_id>/` in the collection bucket and deletes them in batches of 1000.
Dry run by default; `--execute` to delete.

## Pipeline

```bash
# 1. Set up credentials
cp .env.example .env
# Edit .env with AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY

# 2. Set machine-specific paths (from repo root)
source ../../local_paths.sh hydromet   # sets APP_DATA_DIR and CATALOG_HOME_DIR

# 3. Run
bash run_pipeline.sh                    # dry run — shows the staging plan
bash run_pipeline.sh --execute          # stage + generate items
bash run_pipeline.sh --execute --upload # + upload to DEDL S3
```

## Notes

- `item_folder_level` is `YYYY` — items span a full 25/35-year experiment period, not individual months
- Both NetCDF and CSV files are supported; `hydromet_output.pdf` is skipped if absent
- `catalog_config.yaml` drives all collection-level metadata; simulation keys are resolved against `apps/_shared/simulations.yaml`
- No production data path is currently known for DWD — set `APP_DATA_DIR` to your local HydroMet output directory
