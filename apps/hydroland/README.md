# HydroLand

**Collection ID:** `EO.UFZ.DAT.HYDROLAND`  
**Owner:** Jeisson Leal (UFZ)  
**Description:** Land Surface Hydrology Simulations from the Mesoscale Hydrologic Model (mHM).
Covers historical (1990–2014) and projection (2015–2049) periods at 5 km resolution.

## Files

| File | Purpose |
|---|---|
| `catalog_config.yaml` | ALL HydroLand input: collection metadata, paths, simulation keys |
| `staging/stage.py` | Stages data: writes collection files, creates catalog folders, restructures monthly files (uses `stac_dedl_core`) |
| `staging/move_hydroland_monthly_data.py` | Moves monthly NetCDF files into the STAC-ready `YYYY/MM/item/` layout |
| `staging/scaffold_hydroland_projection.py` | Scaffolds the projection data folder structure |
| `staging/delete_s3_collection_prefix.py` | Utility to delete a collection prefix from the S3 bucket |

## What the scripts do

**`stage.py`** — loads `catalog_config.yaml` via `stac_dedl_core.load_app_config`
(simulation keys resolved against `apps/_shared/simulations.yaml`), writes
`metadata/collection.json` + `collection_config.json`, creates one period-level
catalog folder per simulation, and with `--restructure` materialises monthly
mHM/mRM files into `data/YYYY/MM/<item>/` (symlink/hardlink/copy/move via
`--link-mode`). Dry run by default; `--execute` applies.

**`move_hydroland_monthly_data.py`** — moves monthly mHM/mRM NetCDF files into the final
`data/YYYY/MM/<item>/` layout. Two source modes: a legacy item folder (metadata suffix
parsed from the folder name) or a flat flux directory (metadata passed via
`--model/--experiment/...` flags, defaulting to IFS-NEMO / SSP3-7.0 / generation 2).
Dry run by default; `--execute` to actually move, plus `--overwrite` and
`--remove-empty-source-dirs` options. Prints a moved/skipped/ignored summary.

**`scaffold_hydroland_projection.py`** — pre-creates projection (2015–2049) item folders
and item JSON metadata *before* the NetCDF files exist, so the catalog structure and
expected asset hrefs are in place ahead of data arrival. Dry run by default.

**`delete_s3_collection_prefix.py`** — maintenance utility: lists all S3 objects under
`<collection_id>/` in the collection bucket and deletes them in batches of 1000.
Dry run by default; `--execute` to delete.

### Decadal indicators (floods / droughts / soil-moisture)

Beyond the monthly mHM/mRM fluxes, HydroLand publishes period-level **indicators**
(aridity index, discharge percentiles, soil-moisture deficit). These are separate
files with their own naming (`YYYY_MM_YYYY_MM_<token>.nc` or `YYYY_YYYY_<token>.nc`),
each staged as **one item per file** under `data/<start_year>/01/`. Enable them by
adding an `indicators:` block to `catalog_config.yaml` (commented example included):

```yaml
indicators:
  source_dir: /path/to/indicator/files
  reference_simulation: ifs-nemo_generation-2_historical   # ref / aridity / discharge
  scenario_simulation:  ifs-nemo_generation-2_projection   # scen / percent_change
  scenario_markers: [scen, percent_change]                 # token → scenario; else reference
```

The trailing `<token>` (e.g. `aridity_index`, `95th_percentile_discharge_indicators`,
`soil_moisture_deficit_ref_SWC_L01`) becomes the item's `data_type`. A token containing
any `scenario_markers` substring maps to `scenario_simulation` (projection); everything
else maps to `reference_simulation` (historical). `stage.py` runs this automatically
when the `indicators:` block is present.

## Pipeline

```bash
# 1. Set up credentials
cp .env.example .env       # add AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY

# 2. Check catalog_config.yaml (paths can be overridden with
#    APP_DATA_DIR / CATALOG_HOME_DIR env vars)

# 3. Run
bash run_pipeline.sh                    # dry run — shows the staging plan
bash run_pipeline.sh --execute          # stage + generate items
bash run_pipeline.sh --execute --upload # + upload to DEDL S3 (add --year YYYY to resume)
```

## Notes

- `item_folder_level` is `MM` — items are grouped by month
- Data uses symlinks to avoid duplication of large NetCDF files
- `catalog_config.yaml` now holds all collection metadata (title, description, DOI, etc.) — simulation keys are resolved against `apps/_shared/simulations.yaml`
