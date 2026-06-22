#!/usr/bin/env bash
# Minimal command-line example: stage -> move -> update for Energy Indicators,
# no Jupyter required. Stops before upload (use run_pipeline.sh --upload for
# that). For a narrated, cell-by-cell walkthrough with output already
# captured, see run_energy_indicators.ipynb instead.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

# --- Change these to point at your own data --------------------------------
SOURCE=/path/to/data/energy_indicators/YYYY/MM   # one source dir per month, see move.py --help
TARGET=/path/to/output/energy_indicators         # where the staged STAC catalog gets built
# -----------------------------------------------------------------------------

export CATALOG_HOME_DIR="${TARGET}"

echo "=== Step 1: stage.py ==="
python staging/stage.py --execute

echo "=== Step 2: move.py (run once per YYYY/MM source folder) ==="
python staging/move.py \
  --source-dir "${SOURCE}" \
  --target-collection-dir "${TARGET}/EO.BSC.DAT.ENERGY_INDICATORS" \
  --model ifs-nemo --experiment ssp3-7.0 --generation 2 \
  --realization 1 --activity projections --resolution high \
  --link --execute

echo "=== Step 3: update.py ==="
python staging/update.py

echo "Done. Items written under ${TARGET}/EO.BSC.DAT.ENERGY_INDICATORS/metadata/items/"
echo "To upload: cp .env.example .env (fill in credentials), then:"
echo "  bash run_pipeline.sh --execute --upload"
