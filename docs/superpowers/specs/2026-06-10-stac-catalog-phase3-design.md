# STAC Catalog Phase 3 — Repository Design & Action Plan

**Date:** 2026-06-10  
**Author:** Jeisson Leal (jeisson-javier.leal-rojas@ufz.de)  
**Repo:** `applications-stac-catalog-phase3`  
**Status:** Approved

---

## 1. Background

Four DestinE Climate DT applications (HydroLand, HydroMet, Energy Indicators, FWI) each maintain
their own fork/copy of the EUMETSAT reference implementation
(`DestinE-DataLake-Lab/HDA/Usergenerated`) in order to upload STAC Catalogs to the DestinE Data
Lake. The shared code (`usergenerated/` package, `generate_item_metadata.py`, `config.py`) is
duplicated across all four repos with only minor differences.

This repo centralises the shared framework while keeping app-specific configuration and staging
scripts isolated and independently maintainable.

**Reference repository:** `DestinE-DataLake-Lab/HDA/Usergenerated` (EUMETSAT)  
**Upstream DEDL docs:** https://destination-earth.github.io/DestinE-DataLake-Lab/HDA/README.html

---

## 2. Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Repo model | Monorepo (all apps in one repo) | Single place for shared code; easy collaboration; no packaging infrastructure |
| Shared code distribution | Installable Python package (`stac_dedl_core`) | Clean imports, no PYTHONPATH hacks, easy to version |
| App isolation | `apps/<name>/` directories | Clear boundary; each team owns their folder |
| Credentials | `.env` file per app (gitignored) | Existing hydroland pattern; no secrets in git |
| Entry point | `run_pipeline.sh` per app | Standardised 3-step workflow |

---

## 3. Repository Structure

```
applications-stac-catalog-phase3/
│
├── .gitignore
├── README.md
├── CONTRIBUTING.md
├── CLAUDE.md
├── pyproject.toml                     # makes stac_dedl_core pip-installable
├── requirements.txt
│
├── stac_dedl_core/                    # shared installable package
│   ├── __init__.py
│   ├── config.py
│   ├── generate_item_metadata.py
│   └── usergenerated/
│       ├── __init__.py
│       ├── s3tools.py
│       ├── s3_mirror.py
│       ├── logging_config.py
│       ├── datetools.py
│       ├── env_utils.py
│       ├── config/
│       │   └── confighelper.py
│       └── item/
│           └── itemhelper.py
│
├── apps/
│   ├── hydroland/
│   │   ├── README.md
│   │   ├── .env.example
│   │   ├── catalog_config.yaml
│   │   ├── run_pipeline.sh
│   │   └── staging/
│   │       └── move_hydroland_monthly_data.py
│   │
│   ├── hydromet/
│   │   ├── README.md
│   │   ├── .env.example
│   │   ├── catalog_config.yaml
│   │   ├── parameters.json
│   │   ├── run_pipeline.sh
│   │   └── staging/
│   │       └── stac_hda_hydromet.py
│   │
│   ├── energy_indicators/
│   │   ├── README.md
│   │   ├── .env.example
│   │   ├── catalog_config.yaml
│   │   ├── run_pipeline.sh
│   │   └── staging/
│   │       ├── check_data.sh
│   │       └── organize_output_energy_indicators.py
│   │
│   └── fwi/
│       ├── README.md
│       ├── .env.example
│       ├── catalog_config.yaml
│       ├── run_pipeline.sh
│       └── staging/
│           └── stac_hda_fwi.py
│
└── templates/
    ├── README.md
    ├── catalog_config.yaml.template
    ├── collection.json.template
    ├── collection_config.json.template
    └── .env.example
```

---

## 4. Standardised Workflow

Every application follows the same 3-step pipeline, encapsulated in `run_pipeline.sh`:

```
Step 1 — Stage data
  apps/<name>/staging/<app>_staging.py
  └── Reorganises raw application output into STAC-compatible folder structure:
      <COLLECTION_ID>/data/YYYY/MM/DD/<item_folder>/

Step 2 — Generate STAC item metadata
  python -m stac_dedl_core.generate_item_metadata
  └── ItemGenerator reads collection.json + collection_config.json,
      walks data/<item_folders>, writes metadata/items/*.json

Step 3 — Upload to DEDL S3
  s3cmd sync <COLLECTION_ID>/ s3://usergenerated-proposal-<collection_id>/
  └── Uploads data + metadata to the DestinE Data Lake bucket
```

### Authentication

Each app has a `.env` file (gitignored) with:
```
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
```
`stac_dedl_core/usergenerated/env_utils.py` validates only the AWS credentials at runtime.
POLYTOPE credentials (`POLYTOPE_USER_EMAIL`, `POLYTOPE_USER_KEY`) are unrelated to the STAC
upload pipeline and are not required here.

---

## 5. Package Design (`stac_dedl_core`)

The package is a direct port of `DestinE-DataLake-Lab/HDA/Usergenerated/` with minimal changes:

- `config.py` — shared constants (S3 endpoint, STAC version, folder level constants)
- `generate_item_metadata.py` — `ItemGenerator` class: the main entry point for step 2
- `usergenerated/` — utility modules unchanged from the reference implementation

**`pyproject.toml`** minimal configuration:
```toml
[build-system]
requires = ["setuptools"]
build-backend = "setuptools.build_meta"

[project]
name = "stac_dedl_core"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
    "pystac",
    "boto3",
    "shapely",
    "python-dotenv",
]
```

Install once at the repo root: `pip install -e .`

Only `generate_item_metadata.py` needs its imports updated (it imports from `config` and
`usergenerated`). The app-specific staging scripts (HydroMet, Energy Indicators, FWI) are
self-contained and do not import from `usergenerated/` directly — no import changes needed there.

```python
# Before (in generate_item_metadata.py)
from config import APP_LOGGER_NAME, ...
from usergenerated.s3tools import S3Tools

# After
from stac_dedl_core.config import APP_LOGGER_NAME, ...
from stac_dedl_core.usergenerated.s3tools import S3Tools
```

---

## 6. Application Migration Guide

For each application, migration consists of:

1. Copy staging script(s) into `apps/<name>/staging/`
2. Extract collection metadata into `apps/<name>/catalog_config.yaml`
3. Update imports in staging script: `from stac_dedl_core...` instead of local `usergenerated`
4. Add `.env.example` with required credential keys (no values)
5. Write `apps/<name>/run_pipeline.sh` with the 3-step workflow
6. Write `apps/<name>/README.md` with app-specific notes

---

## 7. Action Plan

### Phase 1 — Repo Scaffold (Priority: High)
- [ ] Create `.gitignore` (Python, `.env`, `__pycache__`, log files, data directories)
- [ ] Create `pyproject.toml`
- [ ] Create `requirements.txt`
- [ ] Create skeleton `README.md`
- [ ] Create skeleton `CONTRIBUTING.md`
- [ ] Create `CLAUDE.md`

### Phase 2 — Shared Core Package (Priority: High)
- [ ] Copy `usergenerated/` from `DestinE-DataLake-Lab/HDA/Usergenerated/` into `stac_dedl_core/usergenerated/`
- [ ] Copy `config.py` into `stac_dedl_core/`
- [ ] Copy `generate_item_metadata.py` into `stac_dedl_core/`
- [ ] Add `__init__.py` files to make it a proper package
- [ ] Update internal imports to use `stac_dedl_core.*` namespace
- [ ] Verify `pip install -e .` works

### Phase 3 — Migrate Applications (Priority: High)
- [ ] **HydroLand**: migrate `move_hydroland_monthly_data.py`, `hydroland_data_preparation.py`, `scaffold_hydroland_projection.py`, `delete_s3_collection_prefix.py`, `run_hydroland_data_preparation.sh`, `catalog_config.yaml`, `.env.example`, `run_pipeline.sh`
- [ ] **HydroMet**: migrate `stac_hda_hydromet.py`, `catalog_config.yaml`, `parameters.json`, `.env.example`, `run_pipeline.sh`
- [ ] **Energy Indicators**: migrate `organize_output_energy_indicators.py`, `check_data.sh`, `catalog_config.yaml`, `.env.example`, `run_pipeline.sh`
- [ ] **FWI**: migrate `stac_hda_fwi.py`, `catalog_config.yaml`, `.env.example`, `run_pipeline.sh`
- [ ] Update imports in `stac_dedl_core/generate_item_metadata.py` to use `stac_dedl_core.*` namespace (staging scripts are self-contained — no changes needed there)

### Phase 4 — Templates (Priority: Medium)
- [ ] Create `templates/catalog_config.yaml.template`
- [ ] Create `templates/collection.json.template`
- [ ] Create `templates/collection_config.json.template`
- [ ] Create `templates/.env.example`
- [ ] Create `templates/README.md` (step-by-step onboarding guide)

### Phase 5 — Documentation (Priority: Medium)
- [ ] Write `README.md`: overview, quickstart (`pip install -e .`), workflow diagram, app list with links
- [ ] Write `CONTRIBUTING.md`: branching strategy, how to add a new app, PR checklist
- [ ] Write `CLAUDE.md`: project context, repo structure, key files, common workflows

### Phase 6 — Validation (Priority: Medium)
- [ ] Run `generate_item_metadata.py` dry-run against existing HydroLand test data
- [ ] Confirm imports resolve correctly after `pip install -e .`
- [ ] Confirm `.env` loading works for each app

---

## 8. Related Repositories

| Repo | Role | Status after migration |
|---|---|---|
| `DestinE-DataLake-Lab` | Reference/upstream (EUMETSAT) | Read-only reference; `stac_dedl_core` tracks it |
| `destine-datalake-lab-hydroland` | HydroLand STAC scripts | Superseded by `apps/hydroland/` |
| `destine-datalake-lab-hydromet` | HydroMet STAC scripts | Superseded by `apps/hydromet/` |
| `stac_energy_indicators` | Energy Indicators STAC scripts | Superseded by `apps/energy_indicators/` |
| `Data-Lake-Transfer-of-FWI-Output` | FWI STAC scripts | Superseded by `apps/fwi/` |

---

## 9. Authors & References

- **Jeisson Leal** (UFZ) — HydroLand, framework lead
- **Carl Hartick** (DWD) — HydroMet
- **Francesc Roura Adserias** (BSC) — Energy Indicators
- **Suraj Polade** (FMI) — Wildfire FWI

**References:**
- DEDL HDA Documentation: https://destination-earth.github.io/DestinE-DataLake-Lab/HDA/README.html
- PySTAC: https://pystac.readthedocs.io/
- DestinE Data Lake: https://data.destination-earth.eu/
- GitLab issue: Standardisation of STAC Catalog between applications during Phase 3
