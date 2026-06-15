# applications-stac-catalog-phase3

Centralised STAC Catalog framework for uploading DestinE Climate DT application data to the
[DestinE Data Lake (DEDL)](https://data.destination-earth.eu/).

This repository replaces the per-application copies of the
[DestinE-DataLake-Lab](https://github.com/destination-earth/DestinE-DataLake-Lab) reference
implementation. Shared logic lives in `stac_dedl_core/`; application-specific staging scripts
and configuration live in `apps/<app-name>/`.

## Applications

| Application | Collection ID | Folder |
|---|---|---|
| HydroLand | `EO.UFZ.DAT.HYDROLAND` | `apps/hydroland/` |
| HydroMet | `EO.DWD.STAT.HYDROMET_EXTREMES` | `apps/hydromet/` |
| Energy Indicators | `EO.BSC.DAT.ENERGY_INDICATORS` | `apps/energy_indicators/` |
| Wildfire FWI | `EO.FMI.DAT.DESTINE_CLIMATE_WILDFIRE_FWI` | `apps/fwi/` |

## Quickstart

### 1. Clone the repository

```bash
git clone <repo-url>
cd applications-stac-catalog-phase3
```

### 2. Set up the environment

**Option A — conda (recommended)**

```bash
conda env create -f environment.yml
conda activate stac-catalog
```

> **Note:** `environment.yml` calls `pip install -e .` automatically, which installs
> `stac_dedl_core` in editable mode. If you update the package code you do not need
> to reinstall.

**Option B — pip only**

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
pip install xarray pandas PyYAML
```

### 3. Configure credentials

Each application folder contains a `.env.example` file. Copy it and fill in your S3 credentials:

```bash
cp apps/<app-name>/.env.example apps/<app-name>/.env
# Edit .env and set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY
```

> Credentials are for the DEDL S3-compatible object storage (Islet Service).
> `.env` files are gitignored — never commit them.

### 4. Run an application pipeline

Each application provides a `run_pipeline.sh` that executes the standard 3-step workflow:

```
Step 1 — Stage data      : reorganise raw app output into STAC folder structure
Step 2 — Generate items  : create STAC item metadata JSON files
Step 3 — Upload to S3    : sync data + metadata to the DEDL bucket
```

```bash
cd apps/<app-name>
# Edit run_pipeline.sh to set your data paths
bash run_pipeline.sh
```

See each application's `README.md` for app-specific instructions.

### Try it first — dry run with fake data

To confirm an app works **before** touching real data or credentials, run a dry run
(stage + generate, no upload). It auto-creates fake input and reports the items:

```bash
conda activate stac-catalog
bash tools/dry_run.sh all          # or: hydroland | hydromet | fwi | energy_indicators
```

Full walk-through (including the manual step-by-step): **`docs/RUN_GUIDE.md`**.

## Repository Structure

```
applications-stac-catalog-phase3/
├── stac_dedl_core/          # Shared installable package
│   ├── config.py            # Shared constants (S3 endpoint, STAC version, etc.)
│   ├── generate_item_metadata.py  # ItemGenerator class
│   └── usergenerated/       # Utility modules (S3, logging, date, config, item)
├── apps/
│   ├── hydroland/           # HydroLand staging + config
│   ├── hydromet/            # HydroMet staging + config
│   ├── energy_indicators/   # Energy Indicators staging + config
│   └── fwi/                 # Wildfire FWI staging + config
├── templates/               # Starter kit for adding a new application
├── tools/                   # Dry-run helpers (generate_sample_data.py, dry_run.sh)
├── docs/                    # RUN_GUIDE.md + design specs/plans
├── environment.yml          # Conda environment definition (Python 3.11)
├── pyproject.toml           # stac_dedl_core package definition
└── requirements.txt         # Additional per-app dependencies
```

## Adding a New Application

See `templates/README.md` for a step-by-step guide, and copy `templates/` as a starting point.

## References

- DEDL HDA Documentation: https://destination-earth.github.io/DestinE-DataLake-Lab/HDA/README.html
- PySTAC: https://pystac.readthedocs.io/
- DestinE Data Lake: https://data.destination-earth.eu/
- Upstream reference: [DestinE-DataLake-Lab/HDA/Usergenerated](https://github.com/destination-earth/DestinE-DataLake-Lab/tree/main/HDA/Usergenerated)

## Authors

- **Jeisson Leal** (UFZ) — HydroLand, framework lead
- **Carl Hartick** (DWD) — HydroMet
- **Francesc Roura Adserias** (BSC) — Energy Indicators
- **Suraj Polade** (FMI) — Wildfire FWI
