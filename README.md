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

Each application follows the same four-step pipeline: `stage.py` (build the catalog
skeleton from config) → `move.py` (bring source files in) → `update.py` (generate
STAC item metadata) → upload (`run_pipeline.sh --upload`, the only step that needs
the credentials from step 3).

For the full walkthrough of one app — including a runnable, narrated example against
real data, with output already executed and saved — open its notebook:

```
apps/hydroland/run_hydroland.ipynb
apps/hydromet/run_hydromet.ipynb
apps/energy_indicators/run_energy_indicators.ipynb
apps/fwi/run_fwi.ipynb
```

Each notebook stops **before** uploading — no credentials needed to run it. Prefer
a plain shell script instead? Each app also has a `run_example.sh` — the same
steps with no narration, just commands and a `SOURCE`/`TARGET` pair (placeholder
paths like `/path/to/data`) to edit at the top. For an overview of all four apps
and what's different between them, see **[`apps/RUN_GUIDE.md`](apps/RUN_GUIDE.md)**.

### Try it first — dry run with fake data

To confirm an app works without even opening a notebook, run a dry run (stage → move
→ update, no upload). It auto-creates fake input and reports the items:

```bash
conda activate stac-catalog
bash tools/dry_run.sh all          # or: hydroland | hydromet | fwi | energy_indicators
```

## Repository Structure

```
applications-stac-catalog-phase3/
├── stac_dedl_core/          # Shared installable package
│   ├── config.py            # Shared constants (S3 endpoint, STAC version, etc.)
│   ├── generate_item_metadata.py  # ItemGenerator class
│   ├── update.py            # Shared update.py logic (used by every app's staging/update.py)
│   ├── s3_cleanup.py        # Shared delete_s3_collection_prefix.py logic
│   └── usergenerated/       # Utility modules (S3, logging, date, config, item)
├── apps/
│   ├── RUN_GUIDE.md         # Overview of all 4 apps + what's different between them
│   ├── hydroland/           # HydroLand staging + config + run_hydroland.ipynb + run_example.sh
│   ├── hydromet/            # HydroMet staging + config + run_hydromet.ipynb + run_example.sh
│   ├── energy_indicators/   # Energy Indicators staging + config + run_energy_indicators.ipynb + run_example.sh
│   └── fwi/                 # Wildfire FWI staging + config + run_fwi.ipynb + run_example.sh
├── templates/                # Starter kit for adding a new application
├── tools/                    # Dry-run helpers (generate_sample_data.py, dry_run.sh)
├── environment.yml           # Conda environment definition (Python 3.11)
├── pyproject.toml            # stac_dedl_core package definition
└── requirements.txt          # Additional per-app dependencies
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
