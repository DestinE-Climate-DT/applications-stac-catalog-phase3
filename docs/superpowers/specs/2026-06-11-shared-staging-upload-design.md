# Design: Shared Staging + Upload for the Four STAC Apps

**Date:** 2026-06-11
**Status:** Approved approach (Approach B — shared config + shared staging helpers + shared upload)
**Apps affected:** hydroland, energy_indicators, hydromet, fwi

> **Correction (2026-06-15):** this spec predates the FWI collection-id confirmation.
> Anywhere below that says `EO.FMI.DAT.FWI` is **outdated** — the confirmed id is
> `EO.FMI.DAT.DESTINE_CLIMATE_WILDFIRE_FWI` (Suraj Polade, FMI). It is already used in
> `apps/fwi/run_pipeline.sh`, `apps/fwi/catalog_config.yaml`, and the FWI generator.

## Goal

Eliminate the duplication between the four apps' staging/upload code while keeping the
apps separate. After this work:

- All simulation definitions (model/experiment/generation/realization/activity/period)
  live in **one shared YAML file**.
- All per-app input lives in **one `catalog_config.yaml` per app** — running a pipeline
  never requires editing a `.py` or `.sh` file.
- All apps upload through **one shared boto3-based upload command**.
- The item-folder naming convention has **exactly one implementation**.

## 1. Shared simulations file — `apps/_shared/simulations.yaml`

YAML, not JSON: the file is read only by our own code (never by DEDL), and YAML is
easier for humans to maintain. STAC output (collection.json, items/*.json) remains JSON.

Canonical experiment spellings (decision): `hist`, `cont`, `SSP3-7.0` — following
hydroland's existing published spellings. Storyline experiment `Tplus2.0K` keeps its
mixed case as provided.

Field names: `start_year` / `end_year` (renamed from hydroland's
`start_catalog_year` / `end_catalog_year` — the "catalog" wording was misleading).

`realization` accepts a **scalar or a list**. A list is expanded by the config loader
into one resolved simulation per realization (used by storylines, which have 5).

```yaml
# ── Generation 2 baseline / projection runs ──────────────────────────
ifs-nemo_generation-2_historical:
  model: IFS-NEMO
  experiment: hist
  generation: 2
  realization: 1
  activity: baseline
  start_year: 1990
  end_year: 2014

ifs-nemo_generation-2_control:
  model: IFS-NEMO                    
  experiment: cont                     
  generation: 2
  realization: 1
  activity: baseline
  start_year: 1990
  end_year: 2014

ifs-nemo_generation-2_projection:
  model: IFS-NEMO
  experiment: SSP3-7.0
  generation: 2
  realization: 1
  activity: projections
  start_year: 2015
  end_year: 2049

# Same three entries (historical / control / projection) repeated for
# IFS-FESOM and ICON — 9 entries total for generation 2.

# ── Storyline runs (IFS-FESOM, story nudging, 5 realizations) ────────
storylines-hist:
  model: IFS-FESOM
  experiment: hist
  generation: 2
  realization: [1, 2, 3, 4, 5]
  activity: story-nudging
  resolution: standard
  start_year: 2017
  end_year: 2026

storylines-cont:
  model: IFS-FESOM
  experiment: cont
  generation: 2
  realization: [1, 2, 3, 4, 5]
  activity: story-nudging
  resolution: standard
  start_year: 2017
  end_year: 2026

storylines-plus2K:
  model: IFS-FESOM
  experiment: Tplus2.0K
  generation: 2
  realization: [1, 2, 3, 4, 5]
  activity: story-nudging
  resolution: standard
  start_year: 2017
  end_year: 2026
```

Rules:

- Entries contain only fields that are identical wherever the simulation is used.
  `resolution` is normally a per-app override (energy: `high`, hydromet/hydroland:
  `5km`), but MAY appear in a shared entry when it is intrinsic to the run (storylines:
  `standard`). Per-app `overrides:` always win over shared values.
- Unknown keys in an entry are allowed and flow through to `additional_property_keys`
  (this is how hydroland's `region` / `simulation_id` survive).

## 2. Per-app `catalog_config.yaml`

Single input file per app. Hydroland's metadata moves here from
`run_hydroland_data_preparation.sh`. Schema (energy_indicators example):

```yaml
# Identity
id: EO.BSC.DAT.ENERGY_INDICATORS
title: Energy Indicators – ...
description: ...
short_description: ...
license: CC-BY-4.0
keywords: [NetCDF, Climate, Energy]
providers:
  - name: Barcelona Supercomputing Center (BSC)
    roles: [producer, licensor]
    url: https://www.bsc.es
thumbnail_url: https://...
thumbnail_mime: image/png
doi:                       # optional block
  url: https://doi.org/...
  code: 10.xxxx/...
  citation: ...

# Extents
bbox: [-12, 34.05, 45, 71.95]
# temporal extent is DERIVED from the selected simulations:
#   start = min(start_year)-01-01T00:00:00Z
#   end   = max(end_year)-12-31T23:00:00Z
# temporal_start / temporal_end may be set explicitly to override the derivation.

# Layout
item_folder_level: MM      # YYYY for hydromet

# Machine paths — env vars APP_DATA_DIR / CATALOG_HOME_DIR override these
app_data_dir: /gpfs/scratch/.../energy_indicators/20150101/member01
catalog_home_dir: .

# Simulations this app publishes (keys into _shared/simulations.yaml)
simulations:
  - ifs-nemo_generation-2_projection
overrides:
  resolution: high         # merged into every selected simulation
```

FWI's yaml keeps `id: EO.FMI.DAT.FWI` with a comment:
`# TODO(jeisson): confirm with the FWI app owner (Suraj Polade, FMI) — their generate script used EO.FMI.DAT.DESTINE_CLIMATE_WILDFIRE_FWI`.

Credentials stay in `.env` (unchanged). Rule: **you never edit a `.py`/`.sh` file to
run a pipeline** — only yaml and `.env`.

## 3. New shared code in `stac_dedl_core`

| Module | Contents |
|---|---|
| `appconfig.py` | `load_app_config(app_dir) -> AppConfig` dataclass. Reads the app yaml, resolves `simulations:` keys against `_shared/simulations.yaml` (path via `SIMULATIONS_FILE` env var, default `../_shared/simulations.yaml` relative to the app dir), merges `overrides:`, expands realization lists, applies env-var path overrides, derives the temporal extent. Fails loudly on unknown simulation keys. |
| `staging.py` | `build_item_folder_name(collection_id, start_ts, end_ts, properties)` — the ONE implementation of `<ID>_<start>_<end>__v1__v2__...`; `materialize_file(src, dst, mode)` with modes symlink/hardlink/copy/move, dry-run aware; `safe_slug()`, `format_catalog_property()` (promoted from hydroland). |
| `collection_builder.py` | `write_collection_files(cfg)` — writes `metadata/collection.json` + `metadata/collection_config.json` from an AppConfig (generalised from hydroland's builders). Optional `parameters.json` hook preserves hydromet's datacube extension and sci:publications. `additional_property_keys` derived from the union of resolved simulation fields. |
| `upload.py` | Shared upload command, see §4. |

**ItemGenerator merge:** FWI's three extensions move into the core `ItemGenerator`,
**off by default**, enabled per app via `collection_config.json` flags:

- `"read_nc_properties": true` — read model/experiment/… from a representative NetCDF
- `data_type` inference from item id (`__monthly` / `__yearly`)
- bbox from config with NetCDF fallback

Only FWI enables them initially; the other apps' behavior is unchanged. FWI's forked
`staging/generate_item_metadata.py` is deleted afterwards.

## 4. Shared upload

```
python -m stac_dedl_core.upload <COLLECTION_ID> [--year YYYY] [--bucket NAME] [--execute]
```

- boto3 via existing `S3Tools`; credentials from `.env`; endpoint from `config.py`.
- Bucket default: `usergenerated-proposal-<collection-id lowercased>` — for energy
  indicators that is `...eo.bsc.dat.energy_indicators` (**underscore**, confirmed).
  `--bucket` overrides.
- Order: `metadata/` first, then `data/` year by year, month by month → interrupted
  transfers resume at the year/month where they stopped.
- Skips objects already present with the same size unless `IS_OVERWRITE_S3`.
- Dry-run by default (prints object counts + sample keys); `--execute` uploads.
- Replaces both the `IS_UPLOAD_S3` config-file toggle and
  `transfer_to_dedl_energy_indicators.sh` (which is deleted; its `.py` reference in
  energy's run_pipeline.sh was a typo for `.sh`).

## 5. Per-app changes

| App | Change |
|---|---|
| **hydroland** | Metadata → `catalog_config.yaml`; `hydroland_data_preparation.py` shrinks to filename parsing + restructuring on top of shared builders; `hydroland_catalogs.json` retired — `region`/`simulation_id` become `overrides:`. |
| **energy_indicators** | `organize_output_energy_indicators.py` → `staging/stage.py` (~60 lines): same YYYY/MM walk, names from shared builder, metadata from config, `--execute` flag replaces `DRY_RUN` boolean. Upload script deleted. |
| **hydromet** | Rewritten on shared helpers; the year-based if/else is replaced by simulation entries; the committed syntax errors (missing `:` lines 325/382) and the `netcdf_path` scoping bug die in the rewrite; keeps per-period items, PDF bundling, `parameters.json`. |
| **fwi** | Keeps NetCDF-attribute scanning; adopts shared naming/materialize/collection-builder; fork deleted after core merge; collection id kept as `EO.FMI.DAT.FWI` + TODO comment. |

`run_pipeline.sh` becomes byte-identical in all four apps:

```bash
bash run_pipeline.sh                    # stage (dry run) → show plan
bash run_pipeline.sh --execute          # stage → generate items
bash run_pipeline.sh --execute --upload # stage → generate → upload
```

## 6. Error handling & testing

- All destructive steps dry-run by default; loud failures on unknown simulation keys,
  missing required metadata (FWI's `require_metadata_fields` adopted everywhere),
  dashes in collection ids, and bucket-name mismatches.
- `pytest` for shared modules: config loading + override merge + realization-list
  expansion, folder-name round-trip (build ↔ ItemGenerator parse), materialize modes
  on tmp dirs, upload key mapping with a stubbed S3 client.
- Per-app smoke test: small fixture tree of fake `.nc` files → stage + generate →
  assert expected folder names and item JSON.

## 7. Migration order

1. Shared modules + tests in `stac_dedl_core` (purely additive)
2. `apps/_shared/simulations.yaml`
3. hydroland (validates the design end to end)
4. energy_indicators
5. hydromet (bug fixes land here)
6. fwi (ItemGenerator merge last — deepest change)
7. Update all READMEs + `APPS_OVERVIEW.md`

## Open items (non-blocking, tracked as TODOs in code/config)

- ~~Confirm control-run period and activity~~ — **confirmed 2026-06-11**: 1990–2014 /
  `baseline`.
- ~~Ask the FWI app owner which collection id is correct~~ — **confirmed by Suraj
  Polade 2026-06-11**: `EO.FMI.DAT.DESTINE_CLIMATE_WILDFIRE_FWI`. The FWI
  migration plan must use this id (the `EO.FMI.DAT.FWI` in `run_pipeline.sh`
  is the stale one).
- Canonical spellings follow hydroland's published ones (`hist`/`SSP3-7.0`) for now;
  whether DEDL-indexed items tolerate a future spelling change remains unverified.
