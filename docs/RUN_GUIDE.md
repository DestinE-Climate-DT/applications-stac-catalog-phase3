# Dry-Run Guide — test every app with fake data, step by step

This guide runs each application's STAC pipeline **with auto-generated fake data**, so
you can confirm the code works before pointing it at real HPC output. Nothing is
uploaded and no credentials are used. Verified 2026-06-15.

The pipeline is always three steps:

```
STAGE    → reorganise raw output into <COLLECTION_ID>/data/YYYY[/MM]/<item>/  (+ collection.json)
GENERATE → write metadata/items/*.json from the staged tree   (stac_dedl_core.ItemGenerator)
UPLOAD   → push the tree to s3://usergenerated-proposal-<id>/  (only step that needs credentials)
```

**A "dry run" = steps 1–2 only.** Step 3 (upload) is the only step that touches the
network or needs AWS keys, so leaving it out gives a safe, fully-local test.

---

## Step 0 — Create the environment (one time)

```bash
cd applications-stac-catalog-phase3
conda env create -f environment.yml      # creates env "stac-catalog" (Python 3.11)
conda activate stac-catalog
```

Verify:

```bash
python -c "from stac_dedl_core import ItemGenerator; print('ok')"
python -m pytest -q          # expect: 59 passed
```

---

## Step 0.5 — Review (and tweak) the config first

Each app's collection metadata lives in **`apps/<app>/catalog_config.yaml`**. Open it
before running and adjust as needed:

```bash
$EDITOR apps/hydroland/catalog_config.yaml
$EDITOR apps/hydromet/catalog_config.yaml          # datacube is inlined in this file too
$EDITOR apps/energy_indicators/catalog_config.yaml
$EDITOR apps/fwi/catalog_config.yaml
```

**Yes — the dry run uses these exact files.** HydroLand and Energy read
`catalog_config.yaml` directly; for HydroMet and FWI, `dry_run.sh` copies the app's
`catalog_config.yaml` into the sandbox and the stager reads it there (FWI also gets
its `daily_data_dir` pointed at the fake data).

### What you can override, and where

| Want to change… | Edit this |
|---|---|
| Collection metadata (title, description, **license**, providers, keywords, bbox, thumbnail, publications, …) | `apps/<app>/catalog_config.yaml` — HydroMet now reads **all** of these from the yaml too (previously hardcoded in its Python) |
| **Which simulations are published** | the `simulations:` list in `catalog_config.yaml` (keys reference `apps/_shared/simulations.yaml`) |
| A per-app tweak to a shared simulation (e.g. resolution) | the `overrides:` block in `catalog_config.yaml` (e.g. energy: `overrides: {resolution: high}`) |
| Add an item sub-dimension (e.g. indicators → `__river_discharge_indicators`) | `data_type_rules:` in `catalog_config.yaml` (needs `split_data_type_items: true`) — a shared, all-apps feature; first matching `match` substring wins |
| Machine paths (raw data in / collection out) | env vars **`CATALOG_HOME_DIR`** and **`APP_DATA_DIR`** (override the yaml's `catalog_home_dir` / `app_data_dir`); FWI uses `daily_data_dir` in the yaml |
| The shared simulations file location | env var **`SIMULATIONS_FILE`** |

> **What actually gets generated = config × data present.** For HydroLand the
> `simulations:` list has all six runs (3 models × hist/proj), so `stage.py` creates
> six period *catalog folders* — but item JSONs are only produced for runs that have
> **data on disk**. The dry run's fake-data generator only creates **IFS-NEMO
> historical 1990**, which is why you see IFS-NEMO/hist items and nothing else. Point
> it at real data (or add more simulations to the fake generator) to get the rest.

---

## Step 1 — Run a dry run (the easy way)

One command stages + generates an app against fresh fake data, in a throwaway
sandbox, and reports how many STAC items it produced:

```bash
bash tools/dry_run.sh all          # all four apps
# or one at a time:
bash tools/dry_run.sh hydroland
bash tools/dry_run.sh hydromet
bash tools/dry_run.sh fwi
bash tools/dry_run.sh energy_indicators
```

Expected result (the sandbox path will differ each run):

```
HydroLand          -> generated 3 item JSON(s)
HydroMet           -> generated 4 item JSON(s)
FWI                -> generated 3 item JSON(s)
Energy Indicators  -> generated 2 item JSON(s)   (provisional config — see Step 4)
```

By default the sandbox is a fresh `mktemp` dir (printed at the end). To choose your
own and keep it for inspection:

```bash
bash tools/dry_run.sh all /tmp/my_dryrun
ls /tmp/my_dryrun/hydromet/EO.DWD.STAT.HYDROMET_EXTREMES/metadata/items/
rm -rf /tmp/my_dryrun        # clean up when done
```

That's the whole dry run. The rest of this guide explains what those steps do
manually, what's still missing for a *real* run, and where `.env` goes.

---

## Step 2 — The same thing by hand (what `dry_run.sh` does)

First generate fake input for an app (`tools/generate_sample_data.py` lays out tiny
NetCDF/CSV files exactly how each stager expects them):

```bash
SB=/tmp/dryrun
python tools/generate_sample_data.py all "$SB"     # or: hydromet "$SB", fwi "$SB", ...
```

Then, per app:

### HydroLand (fully migrated — the only app with a native dry-run mode)

```bash
export CATALOG_HOME_DIR="$SB/hydroland" APP_DATA_DIR="$SB/hydroland/appdata"
cd apps/hydroland

python staging/stage.py --restructure                              # DRY RUN: prints the plan
python staging/stage.py --restructure --execute --link-mode copy   # STAGE: writes files
cd "$CATALOG_HOME_DIR"
python -c "from stac_dedl_core import ItemGenerator; ItemGenerator('EO.UFZ.DAT.HYDROLAND').run()"  # GENERATE
ls EO.UFZ.DAT.HYDROLAND/metadata/items/
```

`apps/hydroland/run_pipeline.sh` wraps this: `bash run_pipeline.sh` (dry run) /
`bash run_pipeline.sh --execute` (stage+generate) / `... --execute --upload`.

### HydroMet  (run from a sandbox — it copies files for real, no dry-run toggle)

```bash
cp apps/hydromet/catalog_config.yaml "$SB/hydromet/"   # datacube is inside the yaml now
cd "$SB/hydromet"
python /ABS/PATH/apps/hydromet/staging/stac_hda_hydromet.py        # STAGE
python -c "from stac_dedl_core import ItemGenerator; ItemGenerator('EO.DWD.STAT.HYDROMET_EXTREMES').run()"  # GENERATE
ls EO.DWD.STAT.HYDROMET_EXTREMES/metadata/items/
```

### FWI  (run from a sandbox — hard-links data, no dry-run toggle)

```bash
# point daily_data_dir at the fake appdata:
python -c "import yaml;c=yaml.safe_load(open('apps/fwi/catalog_config.yaml'));c['daily_data_dir']='$SB/fwi/appdata';yaml.safe_dump(c,open('$SB/fwi/catalog_config.yaml','w'),sort_keys=False)"
cd "$SB/fwi"
python /ABS/PATH/apps/fwi/staging/stac_hda_fwi.py                  # STAGE (daily→monthly, annual→yearly)
python /ABS/PATH/apps/fwi/staging/generate_item_metadata.py       # GENERATE (FWI's own forked generator)
ls EO.FMI.DAT.DESTINE_CLIMATE_WILDFIRE_FWI/metadata/items/
```

### Energy Indicators  (provisional config — see Step 4)

The fake data is already in the staged collection layout
(`EO.BSC.DAT.ENERGY_INDICATORS/data/YYYY/MM/<item>/`), which is what BSC's organize
step produces. Generate the collection metadata with the shared builder, then run
step 2:

```bash
export CATALOG_HOME_DIR="$SB/energy_indicators"
python -c "from stac_dedl_core.appconfig import load_app_config; from stac_dedl_core.collection_builder import write_collection_files; write_collection_files(load_app_config('apps/energy_indicators'), overwrite=True)"   # STAGE metadata
cd "$CATALOG_HOME_DIR"
python -c "from stac_dedl_core import ItemGenerator; ItemGenerator('EO.BSC.DAT.ENERGY_INDICATORS').run()"   # GENERATE
ls EO.BSC.DAT.ENERGY_INDICATORS/metadata/items/
```

> The raw→staged reshuffle is Energy's own stage step
> (`staging/organize_output_energy_indicators.py`, `BASE_DIR` + `DRY_RUN=True`
> hardcoded). On BSC, `BASE_DIR` points at the collection's `data/` dir, so it
> produces the layout above in place. It does **not** write collection metadata —
> that's why the dry run uses the shared builder for that part (and why a small
> `run_pipeline.sh`/`stage.py` is the remaining migration work — Step 4).

---

## Step 3 — What's missing for a *real* run?

A dry run proves staging + item generation work. To actually publish you also need:

| Missing piece | Needed for | Notes |
|---|---|---|
| **Real input data** | all | Replace the fake `appdata/` with actual HPC output. |
| **`.env` with real AWS keys** | step 3 (upload) only | `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY`. Not needed for stage/generate. |
| **Run the upload** | publishing to DEDL | `python -m stac_dedl_core.upload <ID> --root <dir> --execute` (dry-run by default). The legacy `run_pipeline.sh` upload lines are still commented out for hydromet/fwi/energy. |
| **Real bbox / extents** | accurate metadata | Fake data uses a placeholder Europe-ish grid. |
| **`hydromet_output.pdf`** | hydromet (optional) | A real overview PDF, if you want it attached as an asset. |

---

## Step 4 — Energy Indicators: status & remaining work

Energy now stages + generates end-to-end. **Verified on the real 2016 sample (12
items)** and on fake data (above). What changed: it gained a **provisional**
`apps/energy_indicators/catalog_config.yaml`, and the shared `collection_builder`
generates the collection metadata from it.

`catalog_config.yaml` is **provisional** — values were inferred from the sample data
and are marked `# TODO confirm with BSC`. Confirm before publishing:

- **license** (left as `proprietary` — not guessed), title, description, providers
- the full **simulation list** (only the projection run is enabled; historical is
  commented out)
- the **`app_data_dir` / `catalog_home_dir`** HPC paths

Remaining engineering work (not blocking a dry run):

1. **Wire it into a pipeline** — fold the metadata generation into `run_pipeline.sh`
   (or a thin `staging/stage.py` like HydroLand), so `bash tools/dry_run.sh
   energy_indicators` mirrors a real run. Today the dry run calls the shared builder
   directly.
2. **De-hardcode** `BASE_DIR` / `DRY_RUN` in `organize_output_energy_indicators.py`
   (move to config/CLI).
3. **Naming:** folder names use lowercase `ssp3-7.0`, but the NetCDF attribute and the
   canonical spelling are `SSP3-7.0`. Decide whether to re-stage or accept.

---

## Where does `.env` go?

**In each app's own folder** — e.g. `apps/hydroland/.env`, `apps/fwi/.env` — copied
from that app's `.env.example`. Each `run_pipeline.sh` loads `./.env` from its own
directory. Do **not** put your real `.env` in `templates/`; `templates/.env.example`
is only the starter for *new* apps. `.env` is gitignored everywhere, so it's safe in
any app folder. You only need it for the **upload** step.
