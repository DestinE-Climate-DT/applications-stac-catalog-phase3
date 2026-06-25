# Energy Indicators

**Collection ID:** `EO.BSC.DAT.ENERGY_INDICATORS`  
**Responsible:** Francesc Roura Adserias (BSC)  
**Description:** Energy sector indicators derived from DestinE Climate DT simulations.
Historical (1990–2014) and projection (2015–2049) at ~5 km resolution.

## Files

| File | Purpose |
|---|---|
| `catalog_config.yaml` | Collection metadata (id, title, bbox, simulations, datacube). See note below. |
| `staging/stage.py` | Writes `collection.json` + `collection_config.json`, creates STAC folder skeleton |
| `staging/move.py` | Links/copies/moves source NetCDF files from `YYYY/MM/` into `data/YYYY/MM/<item>/` |
| `staging/update.py` | Generates one `metadata/items/<item>.json` per data folder |
| `staging/delete_s3_collection_prefix.py` | Maintenance utility: deletes the collection prefix from S3 |

> ⚠️ **`catalog_config.yaml` is provisional.** Its values were inferred from a sample of
> the staged data. Fields marked `# TODO confirm` (license, title, description, providers,
> the simulation list) need confirmation from BSC before publishing.

## What the scripts do

**`stage.py`** — loads `catalog_config.yaml` via `stac_dedl_core.load_app_config`
(simulation keys resolved against `apps/_shared/simulations.yaml`), writes
`metadata/collection.json` and `metadata/collection_config.json`, and creates one item
folder skeleton per simulation month under `data/YYYY/MM/`. Dry run by default; `--execute` applies.

**`move.py`** — links or moves source NetCDF files from the raw `YYYY/MM/` layout into
the staged `data/YYYY/MM/<item>/` layout. Accepts `--source-dir` and
`--target-collection-dir`, plus simulation metadata flags. Modes: `--link` (symlink),
`--copy`, or `--move`. Dry run by default; `--execute` applies.

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
source ../../local_paths.sh energy_indicators   # sets APP_DATA_DIR and CATALOG_HOME_DIR

# 3. Run
bash run_pipeline.sh                    # dry run — shows the staging plan
bash run_pipeline.sh --execute          # stage + generate items
bash run_pipeline.sh --execute --upload # + upload to DEDL S3
```

## Notes

- `item_folder_level` is `MM` — items are grouped by month
- The folder/item suffix order is `model__experiment__generation__realization__activity__resolution`; `catalog_config.yaml` pins `property_order` to match so item properties are not mislabeled
- Source data layout expected: `<APP_DATA_DIR>/YYYY/MM/*.nc`
- Folder names use lowercase `ssp3-7.0` to match BSC's published naming convention
