#!/usr/bin/env bash
# Minimal command-line example: stage -> move -> update for HydroLand, no
# Jupyter required. Stops before upload (use run_pipeline.sh --upload for that).
# For a narrated, cell-by-cell walkthrough with output already captured, see
# run_hydroland.ipynb instead.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

# --- Change these to point at your own data --------------------------------
SOURCE=/path/to/data/mhm                # flat folder of mHM flux/state .nc files
TARGET=/path/to/output/hydroland        # where the staged STAC catalog gets built
# -----------------------------------------------------------------------------

export CATALOG_HOME_DIR="${TARGET}"

echo "=== Step 1: stage.py ==="
python staging/stage.py --execute

echo "=== Step 2: move.py ==="
python staging/move.py \
  --source-flux-dir "${SOURCE}" \
  --target-collection-dir "${TARGET}/EO.UFZ.DAT.HYDROLAND" \
  --model IFS-NEMO --experiment hist \
  --generation 2 --activity baseline --realization 1 \
  --link --execute

echo "=== Step 3: update.py ==="
python staging/update.py

echo "Done. Items written under ${TARGET}/EO.UFZ.DAT.HYDROLAND/metadata/items/"
echo "To upload: cp .env.example .env (fill in credentials), then:"
echo "  bash run_pipeline.sh --execute --upload"
