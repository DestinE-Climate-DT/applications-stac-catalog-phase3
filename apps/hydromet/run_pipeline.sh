#!/usr/bin/env bash
# HydroMet STAC Catalog pipeline — 3 steps: stage → generate → upload
# Run from this directory: bash run_pipeline.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load credentials from .env
if [ -f "${SCRIPT_DIR}/.env" ]; then
  export $(grep -v '^#' "${SCRIPT_DIR}/.env" | xargs)
fi

# ── Configure these paths for your HPC environment ────────────────────────────
COLLECTION_ID="EO.DWD.STAT.HYDROMET_EXTREMES"
APP_DATA_DIR="/path/to/hydromet/output"  # raw application output directory
CATALOG_HOME_DIR="${SCRIPT_DIR}"
# ──────────────────────────────────────────────────────────────────────────────

cd "${CATALOG_HOME_DIR}"

echo "=== Step 1: Stage data (organise into STAC folder structure) ==="
python "${SCRIPT_DIR}/staging/stac_hda_hydromet.py"

echo "=== Step 2: Generate STAC item metadata ==="
python -c "
from stac_dedl_core import ItemGenerator
gen = ItemGenerator('${COLLECTION_ID}')
gen.run()
"

echo "=== Step 3: Upload to DEDL S3 ==="
# s3cmd --config ~/.s3cfg sync ${COLLECTION_ID}/ s3://usergenerated-proposal-$(echo ${COLLECTION_ID} | tr '[:upper:]' '[:lower:]')/
echo "Upload step — edit run_pipeline.sh to enable (set IS_UPLOAD_S3=True in config.py)"

echo "=== Pipeline complete ==="
