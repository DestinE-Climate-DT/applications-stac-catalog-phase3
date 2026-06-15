#!/usr/bin/env bash
# Wildfire FWI STAC Catalog pipeline — 3 steps: stage → generate → upload
# Run from this directory: bash run_pipeline.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load credentials from .env
if [ -f "${SCRIPT_DIR}/.env" ]; then
  export $(grep -v '^#' "${SCRIPT_DIR}/.env" | xargs)
fi

# ── Configure these paths for your HPC environment ────────────────────────────
COLLECTION_ID="EO.FMI.DAT.DESTINE_CLIMATE_WILDFIRE_FWI"  # confirmed by Suraj Polade (FMI), 2026-06-11
FWI_DATA_DIR="/path/to/fwi/output"   # root dir with daily/annual FWI NetCDF files
CATALOG_HOME_DIR="${SCRIPT_DIR}"
# ──────────────────────────────────────────────────────────────────────────────

cd "${CATALOG_HOME_DIR}"

echo "=== Step 1: Stage data (create STAC folder structure + symlinks) ==="
# stac_hda_fwi.py stages data using hard-links/symlinks to avoid duplication.
# Edit the paths inside staging/stac_hda_fwi.py for your environment.
python "${SCRIPT_DIR}/staging/stac_hda_fwi.py"

echo "=== Step 2: Generate STAC item metadata ==="
# FWI has a customised generate_item_metadata.py in staging/ that handles
# daily + annual + regional products. Use it instead of the shared one.
python "${SCRIPT_DIR}/staging/generate_item_metadata.py"

echo "=== Step 3: Upload to DEDL S3 ==="
# s3cmd --config ~/.s3cfg sync ${COLLECTION_ID}/ s3://usergenerated-proposal-$(echo ${COLLECTION_ID} | tr '[:upper:]' '[:lower:]')/
echo "Upload step — edit run_pipeline.sh to enable"

echo "=== Pipeline complete ==="
