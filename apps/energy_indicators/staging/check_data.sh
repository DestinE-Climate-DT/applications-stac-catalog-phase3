#!/usr/bin/env bash

for y in {1990..2015}; do
  echo "======= year: $y ======="

  # Daily stats (expect 365 or 366)
  for stat in lwe hwe pvp cdd hdd; do
    count=$(find . -type f -name "*${y}*${stat}*" | wc -l)

    if [[ "$count" -ne 365 && "$count" -ne 366 ]]; then
      echo "STAT: ${stat} year: ${y} DATA MISSING! (found $count)"
    fi
  done

  # Monthly / aggregated stats (expect 12)
  for stat in \
    "percentile" \
    "cf_i_.*counts" \
    "cf_ii_.*counts" \
    "cf_iii_.*counts" \
    "cf_s.*counts" \
    "ws_timestep_60_daily_max" \
    "ws_timestep_60_monthly_histogram.*counts"
  do
    count=$(find . -type f | grep "$y" | grep -E "$stat" | wc -l)

    if [[ "$count" -ne 12 ]]; then
      echo "STAT: ${stat} year: ${y} DATA MISSING! (found $count)"
    fi
  done
done


