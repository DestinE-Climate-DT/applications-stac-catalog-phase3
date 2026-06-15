#!/usr/bin/env python3
"""Generate tiny fake input data so each app's pipeline can be dry-run end-to-end.

This produces a few small NetCDF/CSV files laid out exactly the way each app's
staging script expects to find its raw input. The files are ~KB-sized and carry
just enough coordinates / global attributes to satisfy the stagers — they are NOT
scientifically meaningful.

Usage:
    python tools/generate_sample_data.py <app> <output_root>

    app: one of hydroland | hydromet | energy_indicators | fwi | all
    output_root: directory the fake data is written under (created if missing)

See docs/RUN_GUIDE.md for how each app then consumes this data.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

# A small Europe-ish grid so bboxes look plausible.
LAT = np.linspace(35.0, 70.0, 4)
LON = np.linspace(-10.0, 30.0, 4)


def write_nc(path: Path, lat_name: str = "lat", lon_name: str = "lon",
             attrs: dict | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = np.random.default_rng(0).random((LAT.size, LON.size)).astype("float32")
    ds = xr.Dataset(
        {"value": ([lat_name, lon_name], data)},
        coords={lat_name: LAT, lon_name: LON},
    )
    if attrs:
        ds.attrs.update(attrs)
    ds.to_netcdf(path)
    ds.close()


def write_csv(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lats, lons = np.meshgrid(LAT, LON)
    df = pd.DataFrame({"lat_center": lats.ravel(), "lon_center": lons.ravel()})
    with path.open("w", encoding="utf-8") as fh:
        fh.write("# fake hydromet event catalogue\n")
        df.to_csv(fh, sep=";", index=False)


# ---------------------------------------------------------------------------
# Per-app generators
# ---------------------------------------------------------------------------

def gen_hydromet(root: Path) -> None:
    """appdata/<model>/<period>.nc|.csv  (the catalog_config.yaml carries the datacube).

    Filenames must match YYYY_MM_DD_THH_MM_to_YYYY_MM_DD_THH_MM.
    """
    appdata = root / "appdata"
    for model in ("ICON", "IFS-NEMO"):
        write_nc(appdata / model / "1990_01_01_T00_00_to_2014_12_31_T23_00.nc")
        write_nc(appdata / model / "2015_01_01_T00_00_to_2049_12_31_T23_00.nc")
    # one CSV event catalogue to exercise the csv branch
    write_csv(appdata / "ICON" / "1990_01_01_T00_00_to_2014_12_31_T23_00.csv")
    print(f"  hydromet: wrote fake appdata under {appdata}")


def gen_fwi(root: Path) -> None:
    """appdata/<model>/<run>/member01/daily  +  appdata/<model>/Annual_Stat/annual."""
    appdata = root / "appdata"
    attrs = {
        "generation": "2",
        "realization": "1",
        "resolution": "high",
        "activity": "projections",
    }
    for model in ("IFS-NEMO",):
        member = appdata / model / "run01" / "member01"
        # two daily files in 2020 (-> month items for Jan and Feb)
        write_nc(member / "2020_01_15_T00_00_fwi.nc", attrs=attrs)
        write_nc(member / "2020_02_15_T00_00_fwi.nc", attrs=attrs)
        # annual statistics for 2020 (metadata derived from a representative daily file)
        annual = appdata / model / "Annual_Stat"
        write_nc(annual / "2020_fwi_basic_and_days.nc", attrs=attrs)
        write_nc(annual / "2020_fwi_quantiles.nc", attrs=attrs)
    print(f"  fwi: wrote fake appdata under {appdata}")


def gen_hydroland(root: Path, collection_id: str = "EO.UFZ.DAT.HYDROLAND") -> None:
    """Legacy year-level item folders that `stage.py --restructure` reorganises.

    Layout: <root>/<collection_id>/data/<year>/<legacy_item_folder>/<monthly nc>
    """
    legacy_name = (
        f"{collection_id}_19900101T000000_20141231T230000"
        "__IFS-NEMO__hist__generation-2__baseline__realization-1"
    )
    legacy_dir = root / collection_id / "data" / "1990" / legacy_name
    # monthly mHM + mRM files (must match the stage.py filename regexes)
    write_nc(legacy_dir / "1990_01_01_to_1990_01_31_daily_mHM_Fluxes_States.nc")
    write_nc(legacy_dir / "1990_02_01_to_1990_02_28_daily_mHM_Fluxes_States.nc")
    write_nc(legacy_dir / "1990_01_01_T00_00_to_1990_01_31_T23_00_mRM_Fluxes_States.nc")
    print(f"  hydroland: wrote fake legacy data under {root / collection_id}")


def gen_energy(root: Path, collection_id: str = "EO.BSC.DAT.ENERGY_INDICATORS") -> None:
    """Already-staged collection tree (what BSC's organize step produces).

    Layout: <root>/<collection_id>/data/2016/MM/<item>/2016_MM_01_T00_00_cdd.nc
    Item folder suffix order matches the real data:
        __<model>__<experiment>__<generation>__<realization>__<activity>__<resolution>
    The legacy `organize_output_energy_indicators.py` (the raw -> staged step) is
    demonstrated separately in docs/RUN_GUIDE.md via its built-in DRY_RUN toggle.
    """
    import calendar

    attrs = {
        "model": "IFS-NEMO",
        "experiment": "SSP3-7.0",
        "generation": "2",
        "realization": "1",
        "activity": "projections",
        "resolution": "high",
    }
    year = 2016
    for month in (1, 2):
        last = calendar.monthrange(year, month)[1]
        item = (
            f"{collection_id}_{year}{month:02d}01T000000_{year}{month:02d}{last:02d}T230000"
            "__ifs-nemo__ssp3-7.0__2__1__projections__high"
        )
        item_dir = root / collection_id / "data" / str(year) / f"{month:02d}" / item
        write_nc(item_dir / f"{year}_{month:02d}_01_T00_00_cdd.nc", attrs=attrs)
    print(f"  energy_indicators: wrote fake staged tree under {root / collection_id}")


GENERATORS = {
    "hydromet": gen_hydromet,
    "fwi": gen_fwi,
    "hydroland": gen_hydroland,
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
