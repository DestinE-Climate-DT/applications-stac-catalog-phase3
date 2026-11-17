#!/usr/bin/env bash
# Wraps stage.py + update.py + upload. With CATALOG_HOME_DIR set to the
# workflow's member folder the catalog is built in place on the workflow output.
# To gather several workflow outputs into one catalog, run staging/move.py
# between stage and update (see run_example.sh) — this script moves no files.
# All input lives in catalog_config.yaml; credentials in .env.
#
#   bash run_pipeline.sh                    # stage (dry run) — show the plan
#   bash run_pipeline.sh --execute          # stage + generate items
#   bash run_pipeline.sh --execute --upload # stage + generate + upload
#   bash run_pipeline.sh --execute --upload --year 1990
#   bash run_pipeline.sh --execute --upload --replace   # replace published items that changed
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

if [ -f .env ]; then
  set -o allexport
  # shellcheck disable=SC1091
  source .env
  set +o allexport
fi

EXECUTE=0
UPLOAD=0
REPLACE=0
YEAR=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --execute) EXECUTE=1 ;;
    --upload)  UPLOAD=1 ;;
    --replace) REPLACE=1 ;;
    --year)    [[ "$2" =~ ^[0-9]{4}$ ]] || { echo "--year must be a 4-digit year" >&2; exit 1; }; YEAR="$2"; shift ;;
    *) echo "Unknown argument: $1" >&2; exit 1 ;;
  esac
  shift
done

if [ "${REPLACE}" -eq 1 ] && [ "${UPLOAD}" -eq 0 ]; then
  echo "--replace only applies to --upload" >&2
  exit 1
fi

if [ "${UPLOAD}" -eq 1 ] && [ "${EXECUTE}" -eq 0 ]; then
  echo "--upload requires --execute (items must be generated before uploading)" >&2
  exit 1
fi

COLLECTION_ID="$(python -c "import yaml; print(yaml.safe_load(open('catalog_config.yaml'))['id'])")"
# Collection root: <CATALOG_HOME_DIR>/<collection_root_dir> (EO.DWD.STAT.HYDROMET,
# the folder the workflow writes), resolved the same way stage.py/update.py do.
COLLECTION_ROOT="$(python -c "from stac_dedl_core.appconfig import load_app_config; print(load_app_config('.').collection_dir)")"

echo "=== Step 1: Stage (${COLLECTION_ID}) ==="
STAGE_ARGS=()
[ "${EXECUTE}" -eq 1 ] && STAGE_ARGS+=(--execute)
python staging/stage.py "${STAGE_ARGS[@]}"

if [ "${EXECUTE}" -eq 1 ]; then
  echo "=== Step 2: Generate STAC item metadata ==="
  python staging/update.py
fi

if [ "${UPLOAD}" -eq 1 ]; then
  echo "=== Step 3: Upload to DEDL S3 ==="
  UPLOAD_ARGS=("${COLLECTION_ID}" --root "${COLLECTION_ROOT}" --execute)
  [ -n "${YEAR}" ] && UPLOAD_ARGS+=(--year "${YEAR}")
  [ "${REPLACE}" -eq 1 ] && UPLOAD_ARGS+=(--replace)
  python -m stac_dedl_core.upload "${UPLOAD_ARGS[@]}"
fi

echo "=== Pipeline complete ==="
