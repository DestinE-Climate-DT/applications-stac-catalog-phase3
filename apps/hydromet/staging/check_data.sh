#!/usr/bin/env bash
# Pre-staging QC for HydroMet source data.
#
# Usage: bash check_data.sh <source_dir>
#   source_dir: flat directory of .nc/.csv files for one model (same dir
#               you'd pass to move.py --source-dir)
#
# Checks:
#   - DDF.nc and KO_params.nc are present for the historical period (1990-2014)
#   - DDF.nc and KO_params.nc are present for the projection period (2015-2049)
#   - reports how many event catalogue CSVs were found per period
#   - flags any .nc/.csv file that doesn't match the expected filename pattern
#     (YYYY_MM_DD_THH_MM_to_YYYY_MM_DD_THH_MM_<token>.{nc,csv})
set -euo pipefail

SRC="${1:-}"
if [ -z "${SRC}" ]; then
  echo "usage: bash check_data.sh <source_dir>" >&2
  exit 1
fi
if [ ! -d "${SRC}" ]; then
  echo "Source directory does not exist: ${SRC}" >&2
  exit 1
fi

PATTERN='^[0-9]{4}_[0-9]{2}_[0-9]{2}_T[0-9]{2}_[0-9]{2}_to_[0-9]{4}_[0-9]{2}_[0-9]{2}_T[0-9]{2}_[0-9]{2}_.+\.(nc|csv)$'

echo "=== Checking ${SRC} ==="

for token in DDF KO_params; do
  for period in "historical:1990:2014" "projection:2015:2049"; do
    name="${period%%:*}"
    rest="${period#*:}"
    start_year="${rest%%:*}"
    end_year="${rest##*:}"
    count=$(find "${SRC}" -maxdepth 1 -type f -regextype posix-extended \
      -regex ".*/${start_year}_.*_${token}\.nc" 2>/dev/null | wc -l)
    if [ "${count}" -eq 0 ]; then
      echo "MISSING: ${token}.nc for ${name} (${start_year}-${end_year})"
    else
      echo "OK: ${token}.nc for ${name} (${start_year}-${end_year}) — ${count} file(s)"
    fi
  done
done

echo "--- Event catalogue CSVs ---"
hist_csv=$(find "${SRC}" -maxdepth 1 -type f -name "*.csv" -regextype posix-extended \
  -regex '.*/19[0-9][0-9]_.*\.csv|.*/20(0[0-9]|1[0-4])_.*\.csv' 2>/dev/null | wc -l)
proj_csv=$(find "${SRC}" -maxdepth 1 -type f -name "*.csv" -regextype posix-extended \
  -regex '.*/20(1[5-9]|[2-4][0-9])_.*\.csv' 2>/dev/null | wc -l)
echo "historical (1990-2014): ${hist_csv} event CSV(s)"
echo "projection (2015-2049): ${proj_csv} event CSV(s)"

echo "--- Unrecognized filenames ---"
unrecognized=0
while IFS= read -r -d '' f; do
  base="$(basename "${f}")"
  if ! [[ "${base}" =~ ${PATTERN} ]]; then
    echo "UNRECOGNIZED: ${base}"
    unrecognized=$((unrecognized + 1))
  fi
done < <(find "${SRC}" -maxdepth 1 -type f \( -name "*.nc" -o -name "*.csv" \) -print0)

if [ "${unrecognized}" -eq 0 ]; then
  echo "(none)"
fi

echo "=== Done ==="
