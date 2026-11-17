# HydroMet

**Collection ID:** `EO.DWD.STAT.HYDROMET_EXTREMES`  
**Collection root folder:** `EO.DWD.STAT.HYDROMET` (`collection_root_dir`)  
**Bucket:** `s3://usergenerated-proposal-eo.dwd.stat.hydromet-extremes/` with `data/` and `metadata/` at its root (confirmed)  
**Responsible:** Carl Hartick (DWD)  
**Description:** Catalog of extreme precipitation events from DestinE Climate DT simulations,
produced by the HydroMet application of the Climate DT workflow.

## Input: the Climate DT workflow output

The workflow already writes the STAC layout, and this app takes it as it is. With
`HYDROMET.UPLOAD_READY: true`, the last HydroMet job of an experiment moves its upload
files to (`get_stac_structure` in the workflow's `lib/common/utils/app_utils.sh`):

```
<HPCROOTDIR>/output/hydromet/<DATELIST>/<memberNN>/
└── EO.DWD.STAT.HYDROMET/                         bucket root
    └── data/<YYYY>/                              start year of the experiment
        └── EO.DWD.STAT.HYDROMET_EXTREMES_<start>T000000_<end>T230000__<model>__<experiment>__<generation>__<realization>__<activity>__<resolution>/
            ├── <start>_to_<end>_KO_params.nc
            ├── <start>_to_<end>_DDF.nc
            └── <start>_to_<end>_events_T5_<REGION>.csv      one per region
```

- `EO.DWD.STAT.HYDROMET` is the root of the bucket, not an extra folder level: its
  `metadata/` and `data/` land at the root of
  `s3://usergenerated-proposal-eo.dwd.stat.hydromet-extremes/` on upload. Locally it is the
  collection root (`collection_root_dir` in `catalog_config.yaml`). Item and collection
  ids still use `EO.DWD.STAT.HYDROMET_EXTREMES`.
- One item per experiment. Its period (`<start>`/`<end>`) is the experiment's own,
  from its `DATELIST` and length, so it is not tied to 1990–2014 or 2015–2049.
- The `__` suffix values are the workflow's `REQUEST` values, kept as they are
  (e.g. `resolution` is `high`/`standard`).

## Files

| File | Purpose |
|---|---|
| `catalog_config.yaml` | All collection metadata — id, `collection_root_dir`, title, description, license, providers, keywords, datacube |
| `staging/workflow_items.py` | The workflow's item folder naming scheme, shared by `stage.py` and `move.py` |
| `staging/check_data.sh` | Pre-staging QC of workflow output: item names, year folders, KO_params/DDF files, event CSVs |
| `staging/stage.py` | Writes `collection.json` + `collection_config.json`; lists the item folders and flags invalid names |
| `staging/move.py` | Gathers the item folders of several workflow outputs into one collection root, names unchanged |
| `staging/update.py` | Generates one `metadata/items/<item>.json` per item folder |
| `staging/delete_s3_collection_prefix.py` | Maintenance utility: deletes the collection prefix from S3 |

## What the scripts do

**`stage.py`** — loads `catalog_config.yaml` via `stac_dedl_core.load_app_config` and
writes `metadata/collection.json` and `metadata/collection_config.json` into
`<CATALOG_HOME_DIR>/EO.DWD.STAT.HYDROMET/`. It creates no item folders; it only lists
the ones under `data/` and exits non zero if a name does not follow the workflow
scheme. Dry run by default; `--execute` applies.

**`move.py`** — only needed to combine several experiments into one catalog. Takes one
`--source-dir` per workflow output (member folder, its `EO.DWD.STAT.HYDROMET` folder, or
`data/`) and links/copies/moves the item folders into the collection root, keeping year
folder, item folder and file names. Invalid item folders and unrecognized files are
reported and skipped. Modes: `--link`, `--copy`, or `--move`. Dry run by default;
`--execute` applies.

**`update.py`** — runs `stac_dedl_core.ItemGenerator` to write a STAC item JSON for every
item folder under `data/`. Empty-asset items are removed afterwards.

**`delete_s3_collection_prefix.py`** — maintenance utility: lists all S3 objects under
`<collection_id>/` in the collection bucket and deletes them in batches of 1000.
Dry run by default; `--execute` to delete.

## Pipeline

```bash
# 1. Set up credentials
cp .env.example .env
# Edit .env with AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY

# 2a. One experiment: build the catalog in place on the workflow output
export CATALOG_HOME_DIR=<HPCROOTDIR>/output/hydromet/<DATELIST>/<memberNN>
bash staging/check_data.sh "${CATALOG_HOME_DIR}"

# 2b. Or several experiments: gather them first (see run_example.sh)
export CATALOG_HOME_DIR=/path/to/catalog
python staging/stage.py --execute
python staging/move.py --source-dir <member1> --source-dir <member2> --link --execute

# 3. Run
bash run_pipeline.sh                    # dry run — shows the plan
bash run_pipeline.sh --execute          # stage + generate items
bash run_pipeline.sh --execute --upload # + upload <CATALOG_HOME_DIR>/EO.DWD.STAT.HYDROMET to DEDL S3
bash run_pipeline.sh --execute --upload --replace   # a re-run of an already published experiment
```

Each workflow run can be uploaded on its own, in any order: the upload compares
every item with the bucket and needs nothing from earlier uploads. Items already
published and identical are skipped. An item that is published but differs, i.e.
the same experiment run again, stops the upload before anything is sent; add
`--replace` to replace it, which also deletes files the new run no longer has.
See "Upload" in [`apps/RUN_GUIDE.md`](../RUN_GUIDE.md).

## Notes

- `item_folder_level` is `YYYY` — one item per experiment, in the folder of its start year
- `property_order` matches the workflow's suffix: model, experiment, generation, realization, activity, resolution
- The collection's temporal extent is set explicitly to 1990-01-01 – 2049-12-31 (`temporal_start`/`temporal_end`); `simulations:` is unused, item folders come from the workflow
