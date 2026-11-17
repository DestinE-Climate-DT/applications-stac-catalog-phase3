#!/usr/bin/env bash
# Minimal command-line example: stage -> move -> update for HydroMet, no
# Jupyter required. Stops before upload (use run_pipeline.sh --upload for that).
# For a narrated, cell-by-cell walkthrough with output already captured, see
# run_hydromet.ipynb instead.
#
# The Climate DT workflow (HYDROMET.UPLOAD_READY: true) already writes the STAC
# layout into each member folder:
#   <member>/EO.DWD.STAT.HYDROMET/data/<YYYY>/EO.DWD.STAT.HYDROMET_EXTREMES_<start>_<end>__.../
# EO.DWD.STAT.HYDROMET is the bucket root. Two ways to use it:
#   a) one experiment: build the catalog in place, skip move.py:
#        export CATALOG_HOME_DIR=<member>; python staging/stage.py --execute; python staging/update.py
#   b) several experiments: gather them into one catalog (below).
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

# --- Change these to point at your own data --------------------------------
SOURCES=(                                   # workflow member folders, one per experiment
  /path/to/output/hydromet/19900101/member01
  /path/to/output/hydromet/20150101/member01
)
TARGET=/path/to/output/hydromet_catalog     # where the STAC catalog gets built
# -----------------------------------------------------------------------------

export CATALOG_HOME_DIR="${TARGET}"

echo "=== Step 0: check_data.sh ==="
for SOURCE in "${SOURCES[@]}"; do
  bash staging/check_data.sh "${SOURCE}"
done

echo "=== Step 1: stage.py ==="
python staging/stage.py --execute

echo "=== Step 2: move.py ==="
MOVE_ARGS=()
for SOURCE in "${SOURCES[@]}"; do
  MOVE_ARGS+=(--source-dir "${SOURCE}")
done
python staging/move.py "${MOVE_ARGS[@]}" --link --execute

echo "=== Step 3: update.py ==="
python staging/update.py

echo "Done. Items written under ${TARGET}/EO.DWD.STAT.HYDROMET/metadata/items/"
echo "To upload: cp .env.example .env (fill in credentials), then:"
echo "  bash run_pipeline.sh --execute --upload"
