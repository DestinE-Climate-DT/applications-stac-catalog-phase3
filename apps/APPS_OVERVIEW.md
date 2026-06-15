# Apps Overview — How Each App Stages and Uploads Data

All four apps follow the same conceptual pipeline:

```
raw application output
  → 1. STAGE     reorganise into  <COLLECTION_ID>/data/YYYY[/MM]/<item_id>/
  → 2. GENERATE  write metadata/collection.json + metadata/items/*.json
  → 3. UPLOAD    push the whole tree to s3://usergenerated-proposal-<collection-id>/
```

…but each app implements the steps differently. This document compares them,
says which approach is strongest for each step, and lists concrete unification
opportunities.

> **Status (updated 2026-06-15):** the shared foundation from the unification design
> (`docs/superpowers/specs/2026-06-11-shared-staging-upload-design.md`) is
> implemented: `apps/_shared/simulations.yaml`, `stac_dedl_core.{appconfig,
> staging,collection_builder,upload}`, and HydroLand has been migrated
> (single `catalog_config.yaml` + thin `staging/stage.py`, standard
> `run_pipeline.sh`, shared upload CLI).
>
> HydroMet, FWI, and Energy Indicators still use their **legacy staging** but were
> made dry-runnable and **verified end-to-end (stage → generate items)** — see
> `docs/RUN_GUIDE.md` and `tools/dry_run.sh`. All four apps now have a
> `catalog_config.yaml` (Energy's is provisional, pending BSC confirmation). Full
> migration to thin `stage.py` + `run_pipeline.sh` remains as follow-up for the three
> legacy apps. The FWI collection id is confirmed as
> `EO.FMI.DAT.DESTINE_CLIMATE_WILDFIRE_FWI`.

---

## 1. How each app organizes its data (the STAGE step)

### Energy Indicators — `organize_output_energy_indicators.py`
Walks a hardcoded `BASE_DIR` for `YYYY/MM/` subfolders. For each month it builds an
item folder name from **constants hardcoded at the top of the script**
(`model="ifs-nemo"`, `experiment="ssp3-7.0"`, `generation="2"`, `realization="1"`,
`activity="projections"`, `resolution="high"`) and **moves** (`os.rename`) all files
into it. Has a `DRY_RUN` boolean toggle. Simple and readable, but: only one
model/experiment combination per script run (you'd edit the constants and re-run for
historical), and moving means the original layout is destroyed.

### FWI — `stac_hda_fwi.py`
The most metadata-driven stager. Reads collection identity from `catalog_config.yaml`,
then reads `model / experiment / generation / realization / resolution / activity`
**from the NetCDF global attributes of each file** (with fallback attribute names, and
a year-rule fallback for experiment). Groups daily files into monthly items, annual
statistics into yearly items, **hard-links** files instead of copying/moving, and
*fails loudly* if required metadata is missing. Also computes the collection bbox from
the data itself.

### HydroMet — `stac_hda_hydromet.py`
Self-contained: organises data *and* writes a rich `collection.json` (datacube
extension inlined in `catalog_config.yaml`, publications, providers) in one script. Metadata
comes from a **year-based if/else** (start ≤ 2014 → baseline/hist, else
projections/ssp3-7.0); resolution and realization are hardcoded. **Copies** files.
(Collection-level metadata — license/providers/keywords/publications/thumbnail/
datacube — is read from `catalog_config.yaml` as of 2026-06-15, not hardcoded.)
One item per 25/35-year experiment period rather than per month
(`item_folder_level: YYYY`). Copies files. (Previously had two syntax errors and a
`create_item_config` scoping bug; these were fixed 2026-06-15 and the script now
stages + generates end-to-end — see `docs/RUN_GUIDE.md`.)

### HydroLand — `hydroland_data_preparation.py` (now `staging/stage.py` — see status note) (+ helpers)
Fully **CLI-driven**: zero hardcoded metadata in the Python; everything comes from
`run_hydroland_data_preparation.sh` arguments and an external **catalogs JSON**
(`hydroland_catalogs.json`) defining each model/experiment/period combination.
Item folders are created per catalog entry, monthly NetCDFs are restructured into
`YYYY/MM/` items via **symlink/hardlink/copy** (configurable), dry-run by default on
all destructive helpers, logging instead of prints, and a stats summary at the end.
Separate single-purpose helpers exist for moving data, scaffolding future projection
items, and cleaning S3.

### Comparison

| | Energy Indicators | FWI | HydroMet | HydroLand |
|---|---|---|---|---|
| Metadata source | hardcoded in script | **NetCDF attributes** | hardcoded year rule | **catalogs JSON + CLI args** |
| Multiple models/experiments per run | no (edit + re-run) | yes | yes (year rule) | yes (catalog entries) |
| File handling | move (`os.rename`) | hard-link | copy | symlink/hardlink/copy (choice) |
| Dry-run support | `DRY_RUN` toggle | no | no | default-on, `--execute` flag |
| Item granularity | monthly (`MM`) | monthly + yearly (`MM`) | per-experiment-period (`YYYY`) | monthly (`MM`) |
| Writes collection.json | no (separate step) | yes | yes | yes |
| Reusable for another app | low | medium | low | **high** (nothing app-specific in the Python except filename regexes) |
| Stage runs as committed | step 1 only¹ | yes | yes (fixed 2026-06-15) | yes |
| Full pipeline (stage→generate) verified | yes¹ | yes | yes | yes |

¹ Energy Indicators' `organize_*.py` reshuffles raw files **in place** into
  `data/YYYY/MM/<item>/` *inside whatever `BASE_DIR` points at* — on BSC that is the
  collection's own `…/EO.BSC.DAT.ENERGY_INDICATORS/data` dir, so the item tree is
  correct. What it does **not** do is write `collection.json` /
  `collection_config.json`. A provisional `apps/energy_indicators/catalog_config.yaml`
  was added 2026-06-15; with it, the shared `collection_builder` generates the
  metadata and **step 2 was verified end-to-end on the real 2016 sample (12 items)**.
  Still to do: fold metadata generation into a script / `run_pipeline.sh` (or migrate
  to a thin `stage.py`), confirm the config values with BSC, and reconcile the
  lowercase `ssp3-7.0` in folder names vs the canonical `SSP3-7.0`. The other three
  were verified end-to-end on fake data — see `docs/RUN_GUIDE.md`.

**Verdict (staging):** **HydroLand has the best *architecture*** — externalised
config, dry-run safety, link-mode choice, logging, reusable builder. **FWI has the
best *metadata* approach** — reading model/experiment/etc. from the NetCDF files
themselves means one source of truth and no drift between data and catalog. The ideal
unified stager combines both: HydroLand's catalogs-JSON/CLI structure, with FWI's
"read from the file, fall back to the catalog entry" metadata resolution.

---

## 2. How each app uploads to the Data Lake (the UPLOAD step)

| App | Upload mechanism | Status |
|---|---|---|
| Energy Indicators | `transfer_to_dedl_energy_indicators.sh`: `s3cmd sync` of `metadata/` once, then `data/<year>/<month>/` per month | **only app with a working, dedicated upload script** |
| FWI | `S3Tools.upload_folder_to_s3()` inside its `generate_item_metadata.py`, gated by `IS_UPLOAD_S3` in `config.py` | integrated but toggle-hidden |
| HydroMet | commented-out `s3cmd sync` line in `run_pipeline.sh` | not implemented |
| HydroLand | commented-out `s3cmd` / core toggle in `run_pipeline.sh`; has `delete_s3_collection_prefix.py` for cleanup | not implemented (but has the only S3 *cleanup* tool) |

All apps target the same convention:
`s3://usergenerated-proposal-<collection-id-lowercase>/<COLLECTION_ID>/...`

**Verdict (upload):** **Energy Indicators does it best in practice.** `s3cmd sync` is
resumable, idempotent, and the year/month loop gives natural restartability for large
transfers — exactly what you want on an HPC with flaky long transfers. Its weakness is
hardcoded paths and bucket name. The `stac_dedl_core.S3Tools` route (boto3) is cleaner
to call programmatically but uploads the whole tree in one go with no per-month
checkpointing, and is hidden behind a config-file edit (`IS_UPLOAD_S3`).

**Recommended unified upload:** one shared script (in `stac_dedl_core` or
`apps/_shared/`) that takes `COLLECTION_ID`, `CATALOG_HOME_DIR`, and an optional
`YEAR` filter, derives the bucket as `usergenerated-proposal-${COLLECTION_ID,,}`
(with dots→dashes as needed), syncs `metadata/` then `data/` (optionally per
year/month like energy_indicators), and reads credentials from `.env` — no
hardcoded paths, no editing `config.py`.

---

## 3. Unification opportunities

### 3.1 A shared catalogs JSON (HydroLand's pattern, adopted by all apps)

What `hydroland_catalogs.json` actually is — and why the names look confusing:

```json
"Catalog_1: ifs-nemo phase 2 historical": {
  "start_catalog_year": 1990,
  "end_catalog_year": 2014,
  "model": "IFS-NEMO",
  "experiment": "hist",
  "generation": 2,
  "activity": "baseline",
  "realization": 1
}
```

The keys (`"Catalog_1: ifs-nemo phase 2 historical"`) are **only human-readable
labels** — they never appear in folder names, item ids, or STAC output. Only the
*values* are used: the staging script derives `additional_property_keys` from them and
builds the item folder suffix `__IFS-NEMO__hist__generation-2__baseline__realization-1`.
So "Catalog" here does **not** mean a STAC Catalog — each entry is really a
**simulation run definition** (model × experiment × generation × period). Renaming the
keys to something self-describing (e.g. `"ifs-nemo_g2_historical"`) would remove the
confusion with zero functional impact.

This is exactly the information the other apps hardcode:

- Energy Indicators' constants block (`model="ifs-nemo"`, `experiment="ssp3-7.0"`, …)
  ≙ one catalog entry. The historical run would just be a second entry instead of
  editing the script.
- HydroMet's year-based if/else ≙ two catalog entries per model
  (`hist 1990–2014`, `ssp3-7.0 2015–2049`).
- FWI's year-rule fallback ≙ the same two entries (FWI would keep preferring NetCDF
  attributes and use the catalog entry only as fallback).

**Proposal:** since all apps describe the *same* Climate DT simulations, keep **one
shared `simulations.json`** (apps repo root or `apps/_shared/`) with the common
fields (model, experiment, generation, realization, activity, period), and let each
app add app-specific fields (e.g. resolution `high` vs `5km`, region) either inline
per app section or in a small per-app override file. Each app's stager then takes
`--catalogs-data` like HydroLand already does. The link between the JSON and an app is
simply: *the app's staging script loops over the entries and creates one item-folder
family per entry* — no naming magic required.

### 3.2 Shared pipeline variables (HydroMet's pattern)

`run_pipeline.sh` in every app already declares the same block:

```bash
COLLECTION_ID="EO.XXX.YYY.ZZZZ"
APP_DATA_DIR="/path/to/raw/output"
CATALOG_HOME_DIR="${SCRIPT_DIR}"
```

But Energy Indicators ignores it (paths hardcoded in the Python/shell), and FWI reads
paths from `catalog_config.yaml` instead. Standardise on: **`.env` / `run_pipeline.sh`
variables for paths and credentials** (machine-specific), **`catalog_config.yaml` for
collection metadata** (id, title, description, license, DOI, thumbnail — what
HydroLand currently puts in shell variables), and pass both into the staging scripts
as arguments instead of editing source files. Rule of thumb: *if you have to edit a
`.py` file to run the pipeline on a new machine or period, that value is in the wrong
place.*

### 3.3 One ItemGenerator

FWI maintains a fork of `generate_item_metadata.py` for its NetCDF-attribute reading
and monthly/yearly mixed layout. Those features (read properties from a representative
`.nc`, `data_type` inference, bbox-from-config-with-nc-fallback) are generally useful —
they belong in `stac_dedl_core.ItemGenerator` behind `collection_config.json` flags, so
the fork can be deleted and all four apps call the same class.

### 3.4 Naming/consistency nits found while reviewing

- `energy_indicators/run_pipeline.sh` references
  `transfer_to_dedl_energy_indicators.py` — the actual file is `.sh`. (Still open.)
- ~~`fwi/run_pipeline.sh` sets `COLLECTION_ID="EO.FMI.DAT.FWI"`…~~ Resolved:
  `run_pipeline.sh`, `generate_item_metadata.py`, and the new
  `apps/fwi/catalog_config.yaml` all use the confirmed
  `EO.FMI.DAT.DESTINE_CLIMATE_WILDFIRE_FWI`. (The FWI README still showed the old
  id; fixed 2026-06-15.)
- ~~`hydromet/staging/stac_hda_hydromet.py` does not parse…~~ Fixed 2026-06-15
  (colons, the `create_item_config` scoping bug, a dead `os.path.exists` guard that
  skipped copying the data file, and the nc-branch year threshold `2019` → `2014`).
- Energy Indicators' upload bucket uses a **dash** inside the collection part
  (`eo.bsc.dat.energy-indicators`) while the collection id uses an underscore
  (`ENERGY_INDICATORS`) — worth double-checking which one the bucket really is before
  unifying bucket-name derivation.
- **Shared `ItemGenerator` (step 2) bugs found + fixed 2026-06-15** while wiring up
  dry runs: `get_item()` referenced an undefined `collection_id` (NameError, silently
  swallowed by the `try/except` → **zero items** generated for every app), and the
  module-level `logger` was only defined under `if __name__ == "__main__"` (NameError
  when imported, which is how every `run_pipeline.sh` calls it). FWI's forked
  `generate_item_metadata.py` also still imported `from config import …` /
  `from usergenerated import …` (pre-monorepo paths) and never set
  `stac_version=1.0.0` / `stac_extensions` on its collection, so it failed DEDL
  validation. All fixed.
- **Fixed 2026-06-15:** `stac_dedl_core.collection_builder` used to write the
  `stac_extensions` field only when a `doi` was set, but step-2 validation
  (`confighelper.check_collection_fields`) *requires* the field. This surfaced as
  soon as Energy Indicators (no `doi`) used the shared builder. `build_collection_dict`
  now **always** emits `stac_extensions` (scientific ext when a `doi` is present,
  otherwise `[]`).

---

## 4. Suggested target layout (keeping apps separate)

```
apps/
  _shared/
    simulations.json          # shared Climate DT run definitions (3.1)
    upload_to_dedl.sh         # parameterised s3cmd sync (2)
  <app>/
    .env                      # credentials + machine paths
    catalog_config.yaml       # collection metadata (all apps, incl. hydroland)
    run_pipeline.sh           # stage → generate → upload, no edits needed
    staging/                  # app-specific staging only (filename regexes etc.)
```

Apps stay independent — each keeps its own staging logic for its own file naming —
but the simulation definitions, the collection-metadata format, the ItemGenerator,
and the upload script become shared.
