#!/bin/bash

module use /gpfs/projects/bsc32/software/rhel/9.2/modules/all

module load s3cmd/2.4.0-foss-2023b-Python-3.11.5

YEAR=$1

if [ -z "$YEAR" ]; then
  echo "Usage: $0 <year>"
  exit 1
fi

base=/gpfs/scratch/ehpc01/bsc032056/a314/output/energy_indicators/20150101/member01/EO.BSC.DAT.ENERGY_INDICATORS/data
bucket=s3://usergenerated-proposal-eo.bsc.dat.energy-indicators/EO.BSC.DAT.ENERGY_INDICATORS/data

max_jobs=10

s3cmd --config ~/.config-s3cmd --verbose sync /gpfs/scratch/ehpc01/bsc032056/a314/output/energy_indicators/20150101/member01/EO.BSC.DAT.ENERGY_INDICATORS/metadata/ s3://usergenerated-proposal-eo.bsc.dat.energy-indicators/EO.BSC.DAT.ENERGY_INDICATORS/metadata/


for m in $(seq -w 1 12); do

    s3cmd --config ~/.config-s3cmd --verbose sync ${base}/${YEAR}/${m}/ ${bucket}/${YEAR}/${m}/

done

wait

