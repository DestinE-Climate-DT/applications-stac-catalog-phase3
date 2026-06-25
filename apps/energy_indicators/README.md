# Energy Indicators

**Collection ID:** `EO.BSC.DAT.ENERGY_INDICATORS`  
**Owner:** Francesc Roura Adserias (BSC)  
**Description:** Energy sector indicators derived from DestinE Climate DT simulations.
Historical (1990–2014) and projection (2015–2049) at ~5 km resolution.

## Files

| File | Purpose |
|---|---|
| `catalog_config.yaml` | Collection metadata (id, title, bbox, simulations, …). **Provisional** — see note below. |
| `staging/check_data.sh` | Validates that all expected output files are present (rudimentary DQC) |
| `staging/organize_output_energy_indicators.py` | Reorganises raw output into STAC-compatible `YYYY/MM/item/` folder structure |
| `staging/transfer_to_dedl_energy_indicators.sh` | Uploads collection data to DEDL S3 via s3cmd |

> ⚠️ **`catalog_config.yaml` is provisional (2026-06-15).** Its values were inferred
> from a sample of the staged data, not supplied by BSC. Fields marked
> `# TODO confirm` (license, title, description, providers, the simulation list, HPC
> paths) need confirmation before publishing. The collection metadata is generated
> from this file by the shared `stac_dedl_core.collection_builder`.

## What the scripts do

**`organize_output_energy_indicators.py`** — walks `BASE_DIR` (hardcoded BSC scratch
path) looking for `YYYY/MM/` subfolders. For each year/month it computes the first and
last day of the month, builds an item folder name of the form
`EO.BSC.DAT.ENERGY_INDICATORS_<start>T000000_<end>T230000__<model>__<experiment>__<generation>__<realization>__<activity>__<resolution>`
(metadata values are hardcoded constants at the top of the script: `model="ifs-nemo"`,
`experiment="ssp3-7.0"`, etc.), creates that folder inside the month folder, and **moves**
all existing files into it with `os.rename`. A `DRY_RUN = True` toggle at the top must be
flipped to `False` to actually execute; existing item folders are skipped.

**`check_data.sh`** — pre-staging quality check. For each year 1990–2015 it counts files
per statistic: daily stats (`lwe`, `hwe`, `pvp`, `cdd`, `hdd`) must have 365/366 files,
monthly stats (percentiles, capacity-factor counts, wind-speed histograms) must have 12.
Prints a `DATA MISSING!` line for anything that doesn't match.

**`transfer_to_dedl_energy_indicators.sh`** — upload script. Takes a single `<year>`
argument, loads the `s3cmd` module on the BSC HPC, syncs the `metadata/` folder once,
then loops over months 01–12 running `s3cmd sync` for `data/<year>/<month>/` to
`s3://usergenerated-proposal-eo.bsc.dat.energy-indicators/...`. Paths are hardcoded;
credentials come from `~/.config-s3cmd`.

## Pipeline

```bash
# 1. Set up credentials
cp .env.example .env
# Edit .env with AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY

# 2. Edit staging/organize_output_energy_indicators.py to set BASE_DIR
#    to your raw output directory

# 3. Run
bash run_pipeline.sh

# Or step by step:
bash staging/check_data.sh               # optional DQC
python staging/organize_output_energy_indicators.py
# then generate_item_metadata + upload
```

## Generating STAC metadata + items (verified)

`organize_output_energy_indicators.py` builds the `data/YYYY/MM/<item>/` tree but does
**not** write `collection.json` / `collection_config.json`. Those come from
`catalog_config.yaml` via the shared builder. This was verified end-to-end on the real
2016 sample (12 items):

```bash
# from a dir whose CATALOG_HOME_DIR holds EO.BSC.DAT.ENERGY_INDICATORS/data/...
python -c "from stac_dedl_core.appconfig import load_app_config; from stac_dedl_core.collection_builder import write_collection_files; write_collection_files(load_app_config('apps/energy_indicators'), overwrite=True)"
python -c "from stac_dedl_core import ItemGenerator; ItemGenerator('EO.BSC.DAT.ENERGY_INDICATORS').run()"
```

Or just dry-run it with fake data: `bash tools/dry_run.sh energy_indicators`
(see `docs/RUN_GUIDE.md`).

## Notes

- `item_folder_level` is `MM` — items are grouped by month
- The folder/item suffix order is `model__experiment__generation__realization__activity__resolution`;
  `catalog_config.yaml` pins `property_order` to match so item properties aren't mislabeled.
- Folder names use lowercase `ssp3-7.0` while the NetCDF attribute / canonical spelling
  is `SSP3-7.0` — reconcile with BSC.
- `transfer_to_dedl_energy_indicators.sh` uses `s3cmd` directly; requires `s3cmd` in PATH and `~/.config-s3cmd`
- Step 0 (check_data.sh) is optional but recommended before staging
- Indicators in the data include daily stats (`cdd`, `hdd`, `lwe`, `hwe`, `pvp`) plus
  monthly stats (percentiles, capacity-factor counts, wind-speed histograms) — per
  `check_data.sh`.
