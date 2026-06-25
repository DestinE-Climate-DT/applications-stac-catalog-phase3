# Wildfire FWI

**Collection ID:** `EO.FMI.DAT.DESTINE_CLIMATE_WILDFIRE_FWI`  
**Responsible:** Suraj Polade (FMI)  
**Description:** Fire Weather Index outputs from DestinE Climate DT simulations.
Covers daily FWI files, annual statistics, and regional average time series.

## Files

| File | Purpose |
|---|---|
| `catalog_config.yaml` | All FWI input: collection metadata, paths, simulation keys |
| `staging/stage.py` | Writes `collection.json` + `collection_config.json`, creates STAC folder skeleton for monthly + yearly items |
| `staging/move.py` | Links/copies/moves daily, annual, and regional NetCDF files into `data/YYYY/MM/<item>/` |
| `staging/update.py` | Generates one `metadata/items/<item>.json` per data folder |
| `staging/check_data.sh` | Pre-staging quality check — counts files per model directory |
| `staging/delete_s3_collection_prefix.py` | Maintenance utility: deletes the collection prefix from S3 |

## What the scripts do

**`stage.py`** — loads `catalog_config.yaml` via `stac_dedl_core.load_app_config`
(simulation keys resolved against `apps/_shared/simulations.yaml`), writes
`metadata/collection.json` and `metadata/collection_config.json`, and creates item folder
skeletons for both monthly (one per year/month) and yearly (one per year, under `YYYY/01/`)
items. Model directories under `APP_DATA_DIR` are auto-discovered. Dry run by default;
`--execute` applies.

**`move.py`** — links or moves FWI NetCDF files into the staged layout. Handles three product
types: daily files (`YYYY_MM_DD_THH_MM_fwi.nc`) grouped per month, annual statistics
(`Annual_Stat/`) staged under `YYYY/01/`, and regional climatology files. Accepts
`--source-dir` and `--target-collection-dir`; model is auto-discovered from the directory
structure. Modes: `--link` (symlink), `--copy`, or `--move`. Dry run by default; `--execute` applies.

**`update.py`** — runs `stac_dedl_core.ItemGenerator` to write a STAC item JSON for every
folder under `data/` that contains assets. Empty-asset folders are removed afterwards.
FWI items carry `data_type: monthly` or `data_type: yearly` inferred from the item folder name.

**`delete_s3_collection_prefix.py`** — maintenance utility: lists all S3 objects under
`<collection_id>/` in the collection bucket and deletes them in batches of 1000.
Dry run by default; `--execute` to delete.

## Pipeline

```bash
# 1. Set up credentials
cp .env.example .env
# Edit .env with AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY

# 2. Set machine-specific paths (from repo root)
source ../../local_paths.sh fwi   # sets APP_DATA_DIR and CATALOG_HOME_DIR

# 3. Run
bash run_pipeline.sh                    # dry run — shows the staging plan
bash run_pipeline.sh --execute          # stage + generate items
bash run_pipeline.sh --execute --upload # + upload to DEDL S3
```

## Notes

- `item_folder_level` is `MM` — both daily and yearly items live under `data/YYYY/MM/`; yearly items use month `01`
- `split_data_type_items: true` — monthly and yearly files for the same period land in separate item folders
- Data uses symlinks to avoid copying large NetCDF files
- FMI production path: `/scratch/project_465000454/poladesu/ReRuns_FWI`
