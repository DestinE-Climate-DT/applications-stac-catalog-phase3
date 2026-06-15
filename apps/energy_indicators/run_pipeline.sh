#!/usr/bin/env bash
# Energy Indicators STAC Catalog pipeline — 3 steps: stage → generate → upload
# Run from this directory: bash run_pipeline.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load credentials from .env
if [ -f "${SCRIPT_DIR}/.env" ]; then
  export $(grep -v '^#' "${SCRIPT_DIR}/.env" | xargs)
fi

# ── Configure these paths for your HPC environment ────────────────────────────
COLLECTION_ID="EO.BSC.DAT.ENERGY_INDICATORS"
CATALOG_HOME_DIR="${SCRIPT_DIR}"
YEAR="${1:-}"  # optional year argument passed to upload script
# ──────────────────────────────────────────────────────────────────────────────

cd "${CATALOG_HOME_DIR}"

echo "=== Step 0 (optional): Check data completeness ==="
# bash "${SCRIPT_DIR}/staging/check_data.sh"

echo "=== Step 1: Stage data (organise into STAC folder structure) ==="
python "${SCRIPT_DIR}/staging/organize_output_energy_indicators.py"

echo "=== Step 2: Generate STAC item metadata ==="
python -c "
from stac_dedl_core import ItemGenerator
gen = ItemGenerator('${COLLECTION_ID}')
gen.run()
"

echo "=== Step 3: Upload to DEDL S3 ==="
# Option A — use the app's own upload script (uses s3cmd):
# bash "${SCRIPT_DIR}/staging/transfer_to_dedl_energy_indicators.py" ${YEAR}
# Option B — use stac_dedl_core (set IS_UPLOAD_S3=True in config.py)
echo "Upload step — edit run_pipeline.sh to enable"

echo "=== Pipeline complete ==="
