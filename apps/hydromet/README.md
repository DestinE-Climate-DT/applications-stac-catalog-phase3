# HydroMet

**Collection ID:** `EO.DWD.STAT.HYDROMET_EXTREMES`  
**Owner:** Carl Hartick (DWD)  
**Description:** Catalog of extreme precipitation events from DestinE Climate DT simulations.
Historical (1990–2014) and projection (2015–2049) at ~5 km resolution using ICON, IFS-FESOM, IFS-NEMO models.

## Files

| File | Purpose |
|---|---|
| `staging/stac_hda_hydromet.py` | Creates `collection.json`, organises data into STAC folder structure |
| `catalog_config.yaml` | **All** collection metadata — id, title, description, license, providers, keywords, publications, thumbnail, related link, stac_extensions, and the inlined `datacube:` (cube:dimensions / cube:variables) |

## What the scripts do

**`stac_hda_hydromet.py`** — self-contained staging script that both organises data and
writes the collection metadata:

1. Reads `catalog_config.yaml` (id, title, description, generation, **and all
   collection metadata** — see below) and walks `appdata/<model>/` for `.nc`/`.csv`.
2. For each file it extracts the time range from the filename
   (`YYYY_MM_DD_THH_MM_to_YYYY_MM_DD_THH_MM`), opens it to get the bbox, then assigns
   experiment metadata from a year-based rule: start year ≤ 2014 → `baseline` / `hist`
   / 1990–2014, otherwise `projections` / `ssp3-7.0` / 2015–2049. Resolution (`5km`)
   and realization (`1`) are still hardcoded in the staging loop.
3. **Copies** each file (plus an optional `hydromet_output.pdf`, skipped if absent)
   into one item folder per experiment period:
   `data/<exp_start>/<id>_<start>0101T000000_<end>1231T230000__<model>__...` — i.e.
   items span a whole 25/35-year period, not individual months. It also writes an
   `item_config.json` with the file's bbox into each item folder.
4. Writes `metadata/collection.json` and `metadata/collection_config.json`
   (`item_folder_level: YYYY`). As of 2026-06-15 the collection metadata
   (license, providers, keywords, `sci:publications`, thumbnail, related link,
   `stac_extensions`) is read from `catalog_config.yaml`, **not** hardcoded in the
   Python. The datacube (`cube:dimensions` / `cube:variables`) is also inlined in
   `catalog_config.yaml` under `datacube:` — there is no separate `parameters.json`
   anymore (the stager still falls back to `datacube_parameters_file` if the yaml
   ever omits the `datacube:` block).

⚠️ Known issues (as committed): lines 325 and 382 are missing the trailing `:` on
`if not os.path.exists(file_struct)` — the script does not currently run as-is. Also,
in `create_item_config` the CSV branch references `netcdf_path` (a global) instead of
its `file` parameter, and the `item_config.json` existence check at line 385 is missing
a path separator.

## Pipeline

```bash
# 1. Set up credentials
cp .env.example .env
# Edit .env with AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY

# 2. Edit staging/stac_hda_hydromet.py to point APP_DATA_DIR at your raw output

# 3. Run
bash run_pipeline.sh
```

## Notes

- `item_folder_level` is `YYYY` — items are grouped by year
- Both NetCDF and CSV files are supported
- `catalog_config.yaml` drives collection-level metadata in the staging script
