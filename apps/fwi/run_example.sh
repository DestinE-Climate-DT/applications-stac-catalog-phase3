#!/usr/bin/env bash
# Minimal command-line example: stage -> move -> update for FWI, no Jupyter
# required. Stops before upload (use run_pipeline.sh --upload for that). For
# a narrated, cell-by-cell walkthrough with output already captured, see
# run_fwi.ipynb instead.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

# --- Change these to point at your own data --------------------------------
SOURCE=/path/to/data/fwi                # top-level dir, one subfolder per model (auto-discovered)
TARGET=/path/to/output/fwi              # where the staged STAC catalog gets built
# -----------------------------------------------------------------------------

export CATALOG_HOME_DIR="${TARGET}"

echo "=== Step 1: stage.py ==="
python staging/stage.py --execute

echo "=== Step 2: move.py ==="
python staging/move.py \
  --source-dir "${SOURCE}" \
  --target-collection-dir "${TARGET}/EO.FMI.DAT.DESTINE_CLIMATE_WILDFIRE_FWI" \
  --generation 2 --realization 1 --resolution 5km \
  --link --execute

echo "=== Step 3: update.py ==="
python staging/update.py

echo "Done. Items written under ${TARGET}/EO.FMI.DAT.DESTINE_CLIMATE_WILDFIRE_FWI/metadata/items/"
echo "To upload: cp .env.example .env (fill in credentials), then:"
echo "  bash run_pipeline.sh --execute --upload"
