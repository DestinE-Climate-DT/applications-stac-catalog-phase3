# Wildfire FWI

**Collection ID:** `EO.FMI.DAT.DESTINE_CLIMATE_WILDFIRE_FWI`  
**Owner:** Suraj Polade (FMI)  
**Description:** Fire Weather Index outputs from DestinE Climate DT simulations.
Covers daily FWI files, annual statistics, and regional average time series.

## Files

| File | Purpose |
|---|---|
| `staging/stac_hda_fwi.py` | Stages FWI data using hard-links/symlinks; handles daily + annual + regional products |
| `staging/generate_item_metadata.py` | FWI-specific item metadata generator (extended to support daily + annual statistics) |

## What the scripts do

**`stac_hda_fwi.py`** — full staging script driven by `catalog_config.yaml` (collection
id, title, descriptions, source data dir). It does three things:

1. *Monthly items*: scans `<appdata_dir>/<model>/*/member01/` for daily files matching
   `YYYY_MM_DD_THH_MM_fwi.nc`, opens each NetCDF and reads bbox + global attributes
   (`model`, `experiment`, `generation`, `realization`, `resolution`, `activity` — with
   fallback attribute names and a year-based experiment fallback: 1990–2014 →
   `historical`, 2015–2049 → `ssp3-7.0`). Files are grouped per (metadata, year, month)
   and **hard-linked** (copy fallback) into `data/YYYY/MM/<item_id>/`. Missing required
   metadata raises an error instead of silently producing incomplete items.
2. *Yearly items*: scans each model's `Annual_Stat/` dir for annual statistics
   (`*_fwi_basic_and_days.nc`, `*_fwi_quantiles.nc`, `*_fwi_dailyclim_<domain>.nc`),
   takes metadata from a representative *daily* file of the same model/year, and stages
   them under `data/YYYY/01/<item_id>/` (yearly items live in month `01` to keep the
   `MM` folder level uniform).
3. *Collection metadata*: computes the union bbox of everything staged, writes
   `metadata/collection.json` (pystac) and `metadata/collection_config.json` (including
   `additional_property_keys` and the bbox, so item generation doesn't reopen NetCDFs
   for the bbox).

**`generate_item_metadata.py`** — FWI's own copy of the core `ItemGenerator`, extended to:
read `model/experiment/...` properties from one representative NetCDF per item folder,
infer `data_type` (`monthly`/`yearly`) from the item id, take bbox from
`collection_config.json` with NetCDF fallback, and handle the mixed monthly/yearly layout.
Uploads to S3 at the end if `IS_UPLOAD_S3 = True` in `config.py` (via `S3Tools`).

## Pipeline

```bash
# 1. Set up credentials
cp .env.example .env
# Edit .env with AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY

# 2. Edit staging/stac_hda_fwi.py to set the source data paths for your environment

# 3. Run
bash run_pipeline.sh
```

## Notes

- FWI uses a **customised** `generate_item_metadata.py` (in `staging/`) rather than the shared
  `stac_dedl_core` version. This is because FWI manages three distinct product types (daily,
  annual stats, regional climatology) that require specialised item generation logic.
- Model data is **not duplicated** — the staging script creates symbolic links to avoid copying
  large NetCDF files.
- `item_folder_level` is `MM` — daily items are grouped by month.
