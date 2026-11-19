#!/usr/bin/env bash
# Pre-staging QC for HydroMet workflow output.
#
# Usage: bash check_data.sh <source_dir>
#   source_dir: what the Climate DT workflow wrote — the EO.DWD.STAT.HYDROMET
#               folder, the member folder holding it, or its data/ folder
#               (same as move.py --source-dir).
#
# For every item folder data/<YYYY>/<item>/ it checks:
#   - the item name is EO.DWD.STAT.HYDROMET_EXTREMES_<start>_<end>__<6 values>
#     (model, experiment, generation, realization, activity, resolution)
#   - the year folder is the start year of the item
#   - a *_KO_params.nc and a *_DDF.nc file are present (Kostradamus)
#   - how many event catalogue CSVs (one per region) are present
#   - every file starts with its <start>_to_<end> period
set -euo pipefail

COLLECTION_ID="EO.DWD.STAT.HYDROMET_EXTREMES"
ROOT_DIR_NAME="EO.DWD.STAT.HYDROMET"

SRC="${1:-}"
if [ -z "${SRC}" ]; then
  echo "usage: bash check_data.sh <source_dir>" >&2
  exit 1
fi
if [ ! -d "${SRC}" ]; then
  echo "Source directory does not exist: ${SRC}" >&2
  exit 1
fi

if [ "$(basename "${SRC}")" == "data" ]; then
  DATA="${SRC}"
elif [ -d "${SRC}/data" ]; then
  DATA="${SRC}/data"
elif [ -d "${SRC}/${ROOT_DIR_NAME}/data" ]; then
  DATA="${SRC}/${ROOT_DIR_NAME}/data"
else
  echo "No data/ folder in ${SRC} or ${SRC}/${ROOT_DIR_NAME}" >&2
  exit 1
fi

ID_RE="${COLLECTION_ID//./\\.}"
ITEM_RE="^${ID_RE}_([0-9]{8})T[0-9]{6}_([0-9]{8})T[0-9]{6}(__[^_]+(_[^_]+)*){6}$"
FILE_RE='^[0-9]{4}_[0-9]{2}_[0-9]{2}_T[0-9]{2}_[0-9]{2}_to_[0-9]{4}_[0-9]{2}_[0-9]{2}_T[0-9]{2}_[0-9]{2}_.+\.(nc|csv)$'

echo "=== Checking ${DATA} ==="
problems=0
items=0

while IFS= read -r -d '' item; do
  items=$((items + 1))
  name="$(basename "${item}")"
  year="$(basename "$(dirname "${item}")")"
  echo "--- ${year}/${name}"

  # Exactly six __ separated values: count the "__" separators
  suffix="${name#*__}"
  n_values=$(( $(grep -o "__" <<<"__${suffix}" | wc -l) ))
  if ! [[ "${name}" =~ ${ITEM_RE} ]] || [ "${n_values}" -ne 6 ]; then
    echo "INVALID NAME: expected ${COLLECTION_ID}_<start>_<end>__model__experiment__generation__realization__activity__resolution"
    problems=$((problems + 1))
  else
    start="${BASH_REMATCH[1]}"
    end="${BASH_REMATCH[2]}"
    echo "period: ${start} to ${end}"
    if [ "${year}" != "${start:0:4}" ]; then
      echo "WRONG YEAR FOLDER: ${year}, item starts in ${start:0:4}"
      problems=$((problems + 1))
    fi
  fi

  for token in KO_params DDF; do
    count=$(find "${item}" -maxdepth 1 -type f -name "*_${token}.nc" | wc -l)
    if [ "${count}" -eq 0 ]; then
      echo "MISSING: *_${token}.nc"
      problems=$((problems + 1))
    else
      echo "OK: *_${token}.nc (${count})"
    fi
  done
  echo "event CSVs: $(find "${item}" -maxdepth 1 -type f -name "*_events_*.csv" | wc -l)"

  while IFS= read -r -d '' f; do
    base="$(basename "${f}")"
    if ! [[ "${base}" =~ ${FILE_RE} ]]; then
      echo "UNRECOGNIZED FILE: ${base}"
      problems=$((problems + 1))
    fi
  done < <(find "${item}" -type f -print0)
done < <(find "${DATA}" -mindepth 2 -maxdepth 2 -type d -print0 | sort -z)

echo "=== ${items} item(s), ${problems} problem(s) ==="
[ "${items}" -gt 0 ] && [ "${problems}" -eq 0 ]
