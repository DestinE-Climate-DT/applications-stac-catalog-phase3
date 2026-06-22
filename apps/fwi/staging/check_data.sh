#!/usr/bin/env bash
# Pre-staging QC for FWI source data.
#
# Usage: bash check_data.sh <source_dir>
#   source_dir: top-level directory containing one subfolder per model
#               (same dir you'd pass to move.py --source-dir)
#
# Checks, per model and per year found:
#   - daily FWI file count under <model>/*/member01/ (expect 365 or 366)
#   - presence of the three annual statistics files under <model>/Annual_Stat/
#     (basic_and_days, quantiles, dailyclim_*)
#   - flags any .nc file that doesn't match either expected filename pattern
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

for model_dir in "${SRC}"/*/; do
  [ -d "${model_dir}" ] || continue
  model="$(basename "${model_dir}")"
  echo "=== Model: ${model} ==="

  echo "--- Daily files (expect 365 or 366 per year) ---"
  years=$(find "${model_dir}" -path "*/member01/*.nc" -name "????_??_??_T??_??_fwi.nc" 2>/dev/null \
    | sed -E 's#.*/([0-9]{4})_.*#\1#' | sort -u)
  if [ -z "${years}" ]; then
    echo "MISSING: no daily FWI files found under ${model_dir}*/member01/"
  fi
  for y in ${years}; do
    count=$(find "${model_dir}" -path "*/member01/${y}_??_??_T??_??_fwi.nc" 2>/dev/null | wc -l)
    if [ "${count}" -lt 365 ]; then
      echo "INCOMPLETE: ${y} has ${count} daily file(s) (expected 365/366)"
    else
      echo "OK: ${y} has ${count} daily file(s)"
    fi
  done

  echo "--- Annual statistics (expect 3 files per year: basic_and_days, quantiles, dailyclim_*) ---"
  annual_dir="${model_dir}Annual_Stat"
  if [ ! -d "${annual_dir}" ]; then
    echo "MISSING: ${annual_dir} does not exist"
  else
    annual_years=$(find "${annual_dir}" -maxdepth 1 -name "????_fwi_*.nc" 2>/dev/null \
      | sed -E 's#.*/([0-9]{4})_fwi_.*#\1#' | sort -u)
    for y in ${annual_years}; do
      has_basic=$(find "${annual_dir}" -maxdepth 1 -name "${y}_fwi_basic_and_days.nc" | wc -l)
      has_quant=$(find "${annual_dir}" -maxdepth 1 -name "${y}_fwi_quantiles.nc" | wc -l)
      has_clim=$(find "${annual_dir}" -maxdepth 1 -name "${y}_fwi_dailyclim_*.nc" | wc -l)
      missing=""
      [ "${has_basic}" -eq 0 ] && missing="${missing} basic_and_days"
      [ "${has_quant}" -eq 0 ] && missing="${missing} quantiles"
      [ "${has_clim}" -eq 0 ] && missing="${missing} dailyclim"
      if [ -n "${missing}" ]; then
        echo "INCOMPLETE: ${y} missing:${missing}"
      else
        echo "OK: ${y} has all three annual statistics files"
      fi
    done
  fi

  echo "--- Unrecognized .nc files ---"
  unrecognized=0
  while IFS= read -r -d '' f; do
    base="$(basename "${f}")"
    if ! [[ "${base}" =~ ^[0-9]{4}_[0-9]{2}_[0-9]{2}_T[0-9]{2}_[0-9]{2}_fwi\.nc$ ]] && \
       ! [[ "${base}" =~ ^[0-9]{4}_fwi_(basic_and_days|quantiles|dailyclim_[A-Za-z]+)\.nc$ ]]; then
      echo "UNRECOGNIZED: ${f#"${SRC}"/}"
      unrecognized=$((unrecognized + 1))
    fi
  done < <(find "${model_dir}" -name "*.nc" -print0)
  [ "${unrecognized}" -eq 0 ] && echo "(none)"
  echo ""
done

echo "=== Done ==="
