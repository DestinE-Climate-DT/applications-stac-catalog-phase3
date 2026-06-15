#!/usr/bin/env bash
# Dry-run an app's STAC pipeline (stage + generate item metadata) against freshly
# generated fake data. No credentials and no network are used; nothing is uploaded.
#
# Prerequisite:  conda activate stac-catalog   (see docs/RUN_GUIDE.md)
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

run_hydroland() {
  hr "HydroLand (native dry run)"
  local SB="${SB_ROOT}/hydroland" ID="EO.UFZ.DAT.HYDROLAND"
  mkdir -p "${SB}/appdata"
  python "${GEN}" hydroland "${SB}"
  ( export CATALOG_HOME_DIR="${SB}" APP_DATA_DIR="${SB}/appdata"
    cd "${REPO}/apps/hydroland"
    echo "--- STAGE (dry run, no --execute) ---"
    python staging/stage.py --restructure 2>&1 | grep -iE "dry run|catalog folder" | head -4 || true
    echo "--- STAGE (--execute) ---"
    python staging/stage.py --restructure --execute --link-mode copy 2>&1 | grep -iE "wrote|restructure summary" | tail -2 || true
    echo "--- GENERATE ---"
    cd "${SB}"
    python -c "from stac_dedl_core import ItemGenerator; ItemGenerator('${ID}').run()" >/dev/null 2>&1 || true
  )
  count_items "${SB}/${ID}/metadata/items"
}

run_hydromet() {
  hr "HydroMet"
  local SB="${SB_ROOT}/hydromet" ID="EO.DWD.STAT.HYDROMET_EXTREMES"
  mkdir -p "${SB}"
  cp "${REPO}/apps/hydromet/catalog_config.yaml" "${SB}/"
  # parameters.json is optional now (datacube is inlined in the yaml); copy if present.
  [ -f "${REPO}/apps/hydromet/parameters.json" ] && cp "${REPO}/apps/hydromet/parameters.json" "${SB}/" || true
  python "${GEN}" hydromet "${SB}"
  ( cd "${SB}"
    echo "--- STAGE ---"
    python "${REPO}/apps/hydromet/staging/stac_hda_hydromet.py" | tail -1 || true
    echo "--- GENERATE ---"
    python -c "from stac_dedl_core import ItemGenerator; ItemGenerator('${ID}').run()" >/dev/null 2>&1 || true
  )
  count_items "${SB}/${ID}/metadata/items"
}

run_fwi() {
  hr "FWI"
  local SB="${SB_ROOT}/fwi" ID="EO.FMI.DAT.DESTINE_CLIMATE_WILDFIRE_FWI"
  mkdir -p "${SB}"
  python "${GEN}" fwi "${SB}"
  python -c "import yaml; c=yaml.safe_load(open('${REPO}/apps/fwi/catalog_config.yaml')); c['daily_data_dir']='${SB}/appdata'; yaml.safe_dump(c, open('${SB}/catalog_config.yaml','w'), sort_keys=False)"
  ( cd "${SB}"
    echo "--- STAGE ---"
    python "${REPO}/apps/fwi/staging/stac_hda_fwi.py" | tail -1 || true
    echo "--- GENERATE ---"
    python "${REPO}/apps/fwi/staging/generate_item_metadata.py" >/dev/null 2>&1 || true
  )
  count_items "${SB}/${ID}/metadata/items"
}

run_energy() {
  hr "Energy Indicators (provisional config — pending BSC confirmation)"
  local SB="${SB_ROOT}/energy_indicators" ID="EO.BSC.DAT.ENERGY_INDICATORS"
  mkdir -p "${SB}"
  # Fake data is already in the staged collection layout (what BSC's organize
  # step produces). The raw->staged organize step is shown in docs/RUN_GUIDE.md.
  python "${GEN}" energy_indicators "${SB}"
  ( export CATALOG_HOME_DIR="${SB}" APP_DATA_DIR="${SB}"
    echo "--- STAGE (collection metadata via shared builder) ---"
    python -c "
from stac_dedl_core.appconfig import load_app_config
from stac_dedl_core.collection_builder import write_collection_files
write_collection_files(load_app_config('${REPO}/apps/energy_indicators'), overwrite=True)
print('wrote collection.json + collection_config.json')" 2>&1 | tail -1 || true
    echo "--- GENERATE ---"
    cd "${SB}"
    python -c "from stac_dedl_core import ItemGenerator; ItemGenerator('${ID}').run()" >/dev/null 2>&1 || true
  )
  count_items "${SB}/${ID}/metadata/items"
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
