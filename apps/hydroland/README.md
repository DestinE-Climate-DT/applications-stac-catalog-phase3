# HydroLand

**Collection ID:** `EO.UFZ.DAT.HYDROLAND`  
**Responsible:** Jeisson Leal (UFZ)  
**Description:** Land Surface Hydrology Simulations from the Mesoscale Hydrologic Model (mHM).
Covers historical (1990–2014) and projection (2015–2049) periods at 5 km resolution.

## Files

| File | Purpose |
|---|---|
| `catalog_config.yaml` | All HydroLand input: collection metadata, paths, simulation keys, indicator config |
| `staging/stage.py` | Writes collection files, creates STAC folder skeleton, stages indicator files |
| `staging/move.py` | Links/copies/moves monthly mHM and mRM NetCDF files into `data/YYYY/MM/<item>/` |
| `staging/update.py` | Generates one `metadata/items/<item>.json` per data folder |
| `staging/check_data.sh` | Pre-staging quality check — counts files per year/month |
| `staging/delete_s3_collection_prefix.py` | Maintenance utility: deletes the collection prefix from S3 |

## What the scripts do

**`stage.py`** — loads `catalog_config.yaml` via `stac_dedl_core.load_app_config`
(simulation keys resolved against `apps/_shared/simulations.yaml`), writes
`metadata/collection.json` + `collection_config.json`, creates one item folder skeleton
per simulation month under `data/YYYY/MM/`. If an `indicators:` block is present in
`catalog_config.yaml`, also stages decadal indicator files (aridity index, discharge
percentiles, soil-moisture deficit) as additional items. Dry run by default; `--execute` applies.

**`move.py`** — links or moves monthly mHM/mRM NetCDF files into the staged
`data/YYYY/MM/<item>/` layout. Accepts `--source-flux-dir` and `--target-collection-dir`,
plus `--model/--experiment/--generation/--activity/--realization` to tag the items.
Modes: `--link` (symlink), `--copy`, or `--move`. Dry run by default; `--execute` applies.

**`update.py`** — runs `stac_dedl_core.ItemGenerator` to write a STAC item JSON for every
folder under `data/` that contains assets. Empty-asset folders are removed afterwards.

**`delete_s3_collection_prefix.py`** — maintenance utility: lists all S3 objects under
`<collection_id>/` in the collection bucket and deletes them in batches of 1000.
Dry run by default; `--execute` to delete.

### Decadal indicators (floods / droughts / soil-moisture)

Beyond the monthly mHM/mRM fluxes, HydroLand publishes period-level **indicators**
(aridity index, discharge percentiles, soil-moisture deficit). Enable them by adding an
`indicators:` block to `catalog_config.yaml`:

```yaml
indicators:
  source_dir: /path/to/indicator/files
  reference_simulation: ifs-nemo_generation-2_historical
  scenario_simulation:  ifs-nemo_generation-2_projection
  scenario_markers: [scen, percent_change]
```

The trailing token (e.g. `aridity_index`, `95th_percentile_discharge_indicators`) becomes
the item's `data_type`. Tokens containing any `scenario_markers` substring map to the
scenario simulation; everything else maps to the reference simulation.

## Pipeline

```bash
# 1. Set up credentials
cp .env.example .env       # add AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY

# 2. Set machine-specific paths (from repo root)
source ../../local_paths.sh hydroland   # sets APP_DATA_DIR and CATALOG_HOME_DIR

# 3. Run
bash run_pipeline.sh                    # dry run — shows the staging plan
bash run_pipeline.sh --execute          # stage + generate items
bash run_pipeline.sh --execute --upload # + upload to DEDL S3 (add --year YYYY to resume)
```

## Notes

- `item_folder_level` is `MM` — items are grouped by month
- Data uses symlinks to avoid duplication of large NetCDF files
- `catalog_config.yaml` holds all collection metadata; simulation keys are resolved against `apps/_shared/simulations.yaml`
