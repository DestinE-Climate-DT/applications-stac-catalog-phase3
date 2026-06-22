#!/usr/bin/env bash
# Dry-run an app's full STAC pipeline (stage -> move -> update) against freshly
# generated fake data. No credentials and no network are used; nothing is
# uploaded. All four apps use the identical stage.py/move.py/update.py pattern,
# so this script runs the same four steps for each, just with different
# move.py flags (see each app's run_*.ipynb notebook).
#
# Prerequisite:  conda activate stac-catalog   (see apps/RUN_GUIDE.md)
#
# Usage:
#   bash tools/dry_run.sh <app> [sandbox_dir]
#     app:         hydroland | hydromet | fwi | energy_indicators | all
#     sandbox_dir: where fake data + output go (default: a fresh mktemp dir)
#
# Example:
#   bash tools/dry_run.sh all
#   bash tools/dry_run.sh hydromet /tmp/my_dryrun
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP="${1:-}"
SB_ROOT="${2:-$(mktemp -d -t stac_dryrun.XXXX)}"

if [ -z "${APP}" ]; then
  echo "usage: bash tools/dry_run.sh <hydroland|hydromet|fwi|energy_indicators|all> [sandbox_dir]" >&2
  exit 1
fi

GEN="${REPO}/tools/generate_sample_data.py"

hr() { printf '\n========== %s ==========\n' "$1"; }
count_items() {  # $1 = items dir
  local n; n=$(find "$1" -name '*.json' 2>/dev/null | wc -l | tr -d ' ')
  echo "  -> generated ${n} item JSON(s) in $1"
}

run_app() {  # $1=app dir name  $2=collection id  $3...=extra move.py args (after --source-* and before --link)
  local app="$1" id="$2"; shift 2
  local SB="${SB_ROOT}/${app}"
  mkdir -p "${SB}"
  python "${GEN}" "${app}" "${SB}"

  export CATALOG_HOME_DIR="${SB}"
  (
    cd "${REPO}/apps/${app}"
    echo "--- STAGE (--execute) ---"
    python staging/stage.py --execute 2>&1 | grep -iE "wrote|skeleton" | head -5 || true
    echo "--- MOVE (--link --execute) ---"
    python staging/move.py --target-collection-dir "${SB}/${id}" "$@" --link --execute \
      2>&1 | grep -iE "summary|linked|recognized" || true
    echo "--- UPDATE ---"
    python staging/update.py 2>&1 | grep -iE "done\." || true
  )
  unset CATALOG_HOME_DIR
  count_items "${SB}/${id}/metadata/items"
}

run_hydroland() {
  hr "HydroLand"
  local SB="${SB_ROOT}/hydroland" ID="EO.UFZ.DAT.HYDROLAND"
  mkdir -p "${SB}"
  python "${GEN}" hydroland "${SB}"
  export CATALOG_HOME_DIR="${SB}"
  (
    cd "${REPO}/apps/hydroland"
    echo "--- STAGE (--execute) ---"
    python staging/stage.py --execute 2>&1 | grep -iE "wrote|skeleton" | head -5 || true
    echo "--- MOVE mhm (--link --execute) ---"
    python staging/move.py --source-flux-dir "${SB}/appdata/mhm" --target-collection-dir "${SB}/${ID}" \
      --model IFS-NEMO --experiment hist --generation 2 --activity baseline --realization 1 \
      --link --execute 2>&1 | grep -iE "summary|linked" || true
    echo "--- MOVE mrm (--link --execute) ---"
    python staging/move.py --source-flux-dir "${SB}/appdata/mrm" --target-collection-dir "${SB}/${ID}" \
      --model IFS-NEMO --experiment hist --generation 2 --activity baseline --realization 1 \
      --link --execute 2>&1 | grep -iE "summary|linked" || true
    echo "--- UPDATE ---"
    python staging/update.py 2>&1 | grep -iE "done\." || true
  )
  unset CATALOG_HOME_DIR
  count_items "${SB}/${ID}/metadata/items"
}

run_hydromet() {
  hr "HydroMet"
  run_app hydromet "EO.DWD.STAT.HYDROMET_EXTREMES" \
    --source-dir "${SB_ROOT}/hydromet/appdata" --model IFS-NEMO --generation 2 --realization 1 --resolution 5km
}

run_fwi() {
  hr "FWI"
  run_app fwi "EO.FMI.DAT.DESTINE_CLIMATE_WILDFIRE_FWI" \
    --source-dir "${SB_ROOT}/fwi/appdata" --generation 2 --realization 1 --resolution 5km
}

run_energy() {
  hr "Energy Indicators"
  run_app energy_indicators "EO.BSC.DAT.ENERGY_INDICATORS" \
    --source-dir "${SB_ROOT}/energy_indicators/appdata" \
    --model ifs-nemo --experiment ssp3-7.0 --generation 2 --realization 1 --activity projections --resolution high
}

case "${APP}" in
  hydroland)         run_hydroland ;;
  hydromet)          run_hydromet ;;
  fwi)               run_fwi ;;
  energy_indicators) run_energy ;;
  all)               run_hydroland; run_hydromet; run_fwi; run_energy ;;
  *) echo "unknown app: ${APP}" >&2; exit 1 ;;
esac

hr "Done"
echo "Sandbox: ${SB_ROOT}"
echo "Inspect a result, e.g.:  ls ${SB_ROOT}/<app>/<COLLECTION_ID>/metadata/items/"
echo "Remove it when finished:  rm -rf ${SB_ROOT}"
