#!/usr/bin/env bash
# Pre-staging QC for HydroLand source data.
#
# Usage: bash check_data.sh <source_flux_dir> <start_year> <end_year>
#   source_flux_dir: flat directory of monthly mHM or mRM .nc files (same dir
#                     you'd pass to move.py --source-flux-dir)
#   start_year/end_year: expected coverage, e.g. 1990 2014 for historical or
#                         2015 2049 for projection
#
# Checks:
#   - exactly one recognized monthly file per (year, month) in the given range
#   - flags any .nc file that doesn't match a recognized mHM/mRM filename
#     pattern (see staging/stage.py's MHM_FILE_RE / MHM_WITH_TIME_RE / MRM_FILE_RE)
set -euo pipefail

SRC="${1:-}"
START_YEAR="${2:-}"
END_YEAR="${3:-}"

if [ -z "${SRC}" ] || [ -z "${START_YEAR}" ] || [ -z "${END_YEAR}" ]; then
  echo "usage: bash check_data.sh <source_flux_dir> <start_year> <end_year>" >&2
  exit 1
fi
if [ ! -d "${SRC}" ]; then
  echo "Source directory does not exist: ${SRC}" >&2
  exit 1
fi

echo "=== Checking ${SRC} (${START_YEAR}-${END_YEAR}) ==="

echo "--- Monthly coverage (expect exactly 1 file per year/month) ---"
missing=0
for y in $(seq "${START_YEAR}" "${END_YEAR}"); do
  for m in $(seq -w 1 12); do
    # daily_mHM, mHM with time, or mRM — all start with YYYY_MM_DD
    count=$(find "${SRC}" -maxdepth 1 -type f -name "${y}_${m}_*.nc" 2>/dev/null | wc -l)
    if [ "${count}" -eq 0 ]; then
      echo "MISSING: ${y}-${m}"
      missing=$((missing + 1))
    elif [ "${count}" -gt 1 ]; then
      echo "WARNING: ${y}-${m} has ${count} files (expected 1)"
    fi
  done
done
if [ "${missing}" -eq 0 ]; then
  echo "OK: all $(( (END_YEAR - START_YEAR + 1) * 12 )) months present"
else
  echo "${missing} month(s) missing"
fi

echo "--- Unrecognized filenames ---"
unrecognized=0
while IFS= read -r -d '' f; do
  base="$(basename "${f}")"
  if ! [[ "${base}" =~ ^[0-9]{4}_[0-9]{2}_[0-9]{2}_to_[0-9]{4}_[0-9]{2}_[0-9]{2}_daily_mHM_Fluxes_States\.nc$ ]] && \
     ! [[ "${base}" =~ ^[0-9]{4}_[0-9]{2}_[0-9]{2}_T[0-9]{2}_[0-9]{2}_to_[0-9]{4}_[0-9]{2}_[0-9]{2}_T[0-9]{2}_[0-9]{2}_mHM_Fluxes_States\.nc$ ]] && \
     ! [[ "${base}" =~ ^[0-9]{4}_[0-9]{2}_[0-9]{2}_T[0-9]{2}_[0-9]{2}_to_[0-9]{4}_[0-9]{2}_[0-9]{2}_T[0-9]{2}_[0-9]{2}_mRM_Fluxes_States\.nc$ ]]; then
    echo "UNRECOGNIZED: ${base}"
    unrecognized=$((unrecognized + 1))
  fi
done < <(find "${SRC}" -maxdepth 1 -type f -name "*.nc" -print0)
[ "${unrecognized}" -eq 0 ] && echo "(none)"

echo "=== Done ==="
