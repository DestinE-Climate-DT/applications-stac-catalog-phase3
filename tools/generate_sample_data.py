#!/usr/bin/env python3
"""Generate tiny fake input data so each app's pipeline can be dry-run end-to-end.

This produces a few small NetCDF/CSV files laid out exactly the way each app's
move.py expects to find its raw input (see each app's run_<app>.ipynb notebook).
The files are ~KB-sized and carry just enough coordinates to be valid NetCDF —
they are NOT scientifically meaningful.

Usage:
    python tools/generate_sample_data.py <app> <output_root>

    app: one of hydroland | hydromet | energy_indicators | fwi | all
    output_root: directory the fake data is written under (created if missing)
"""
from __future__ import annotations

import argparse
import calendar
import sys
from pathlib import Path

import numpy as np
import xarray as xr

# A small Europe-ish grid so bboxes look plausible.
LAT = np.linspace(35.0, 70.0, 4)
LON = np.linspace(-10.0, 30.0, 4)


def write_nc(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = np.random.default_rng(0).random((LAT.size, LON.size)).astype("float32")
    ds = xr.Dataset({"value": (["lat", "lon"], data)}, coords={"lat": LAT, "lon": LON})
    ds.to_netcdf(path)
    ds.close()


def write_csv(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lats, lons = np.meshgrid(LAT, LON)
    with path.open("w", encoding="utf-8") as fh:
        fh.write("# fake event catalogue\n")
        fh.write("lat_center;lon_center\n")
        for lat, lon in zip(lats.ravel(), lons.ravel()):
            fh.write(f"{lat};{lon}\n")


# ---------------------------------------------------------------------------
# Per-app generators — match each app's move.py --source-*  input shape
# ---------------------------------------------------------------------------

def gen_hydroland(root: Path) -> None:
    """appdata/mhm/ + appdata/mrm/ — flat, one model/experiment per folder.

    Matches move.py --source-flux-dir (one call per data-type folder).
    """
    appdata = root / "appdata"
    write_nc(appdata / "mhm" / "1990_01_01_to_1990_01_31_daily_mHM_Fluxes_States.nc")
    write_nc(appdata / "mhm" / "1990_02_01_to_1990_02_28_daily_mHM_Fluxes_States.nc")
    write_nc(appdata / "mrm" / "1990_01_01_T00_00_to_1990_01_31_T23_00_mRM_Fluxes_States.nc")
    print(f"  hydroland: wrote fake appdata under {appdata}")


def gen_hydromet(root: Path) -> None:
    """appdata/<member>/EO.DWD.STAT.HYDROMET/data/<YYYY>/<item>/ — workflow output.

    Two experiments, laid out as the Climate DT workflow writes them with
    HYDROMET.UPLOAD_READY (get_stac_structure), with the REQUEST values as the
    item suffix. Matches move.py --source-dir (one member folder each).
    """
    experiments = [
        ("hist", "19900101", "20141231", "1990_01_01", "2014_12_31"),
        ("ssp370", "20150101", "20491231", "2015_01_01", "2049_12_31"),
    ]
    for member, start, end, fstart, fend in experiments:
        experiment, activity = ("hist", "baseline") if member == "hist" else ("SSP3-7.0", "projections")
        item = (
            root / "appdata" / member / "EO.DWD.STAT.HYDROMET" / "data" / start[:4] /
            f"EO.DWD.STAT.HYDROMET_EXTREMES_{start}T000000_{end}T230000"
            f"__IFS-NEMO__{experiment}__2__1__{activity}__high"
        )
        period = f"{fstart}_T00_00_to_{fend[:4]}_01_01_T00_00"
        write_nc(item / f"{period}_KO_params.nc")
        write_nc(item / f"{period}_DDF.nc")
        for region in ("neu", "med"):
            write_csv(item / f"{fstart}_T00_00_to_{fend}_T23_00_events_T5_{region}.csv")
    print(f"  hydromet: wrote fake workflow output under {root / 'appdata'}")


def gen_fwi(root: Path) -> None:
    """appdata/<model>/run01/member01/ + appdata/<model>/Annual_Stat/.

    Matches move.py --source-dir (top-level dir, model auto-discovered).
    """
    appdata = root / "appdata"
    for model in ("IFS-NEMO",):
        member = appdata / model / "run01" / "member01"
        write_nc(member / "2020_01_15_T00_00_fwi.nc")
        write_nc(member / "2020_02_15_T00_00_fwi.nc")
        annual = appdata / model / "Annual_Stat"
        write_nc(annual / "2020_fwi_basic_and_days.nc")
        write_nc(annual / "2020_fwi_quantiles.nc")
    print(f"  fwi: wrote fake appdata under {appdata}")


def gen_energy(root: Path) -> None:
    """appdata/YYYY/MM/*.nc — flat per-month, matches move.py --source-dir."""
    appdata = root / "appdata"
    year = 2016
    for month in (1, 2):
        last = calendar.monthrange(year, month)[1]
        write_nc(appdata / str(year) / f"{month:02d}" / f"{year}_{month:02d}_01_T00_00_cdd.nc")
        write_nc(appdata / str(year) / f"{month:02d}" / f"{year}_{month:02d}_{last:02d}_to_{year}_{month:02d}_{last:02d}_ws_timestep_60_daily_max.nc")
    print(f"  energy_indicators: wrote fake appdata under {appdata}")


GENERATORS = {
    "hydroland": gen_hydroland,
    "hydromet": gen_hydromet,
    "fwi": gen_fwi,
    "energy_indicators": gen_energy,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("app", choices=[*GENERATORS, "all"])
    parser.add_argument("output_root")
    args = parser.parse_args(argv)

    root = Path(args.output_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)

    apps = list(GENERATORS) if args.app == "all" else [args.app]
    for app in apps:
        GENERATORS[app](root / app if args.app == "all" else root)
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
