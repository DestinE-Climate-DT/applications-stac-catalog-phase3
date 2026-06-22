#!/usr/bin/env python3
"""
Stage Energy Indicators monthly NetCDF files into the STAC-ready YYYY/MM/item
layout.

Unlike HydroLand, metadata is not parsed per-file — every file produced for a
given YYYY/MM is an asset of the SAME item, so one item folder name is built
per source YYYY/MM folder and every .nc file inside it is linked/copied/moved
in as-is. Always a dry run unless --execute is given. Must specify exactly
one of --move, --copy, or --link.

Example (dry run — omit --execute to just see the plan):

    python move.py \
      --source-dir /gpfs/scratch/.../output/energy_indicators/20150101/member01 \
      --target-collection-dir /path/to/EO.BSC.DAT.ENERGY_INDICATORS \
      --model ifs-nemo --experiment ssp3-7.0 --generation 2 \
      --realization 1 --activity projections --resolution high \
      --link --execute
"""

from __future__ import annotations

import argparse
import calendar
from pathlib import Path

from stac_dedl_core.staging import (
    add_mode_arguments,
    join_item_folder_name,
    log_move_summary,
    materialize_file,
    mode_from_args,
    safe_slug,
    setup_logging,
)

MATERIALIZED_STAT_KEY = {"symlink": "linked", "copy": "copied", "move": "moved"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Stage Energy Indicators monthly NetCDF files (daily indicators + "
            "monthly aggregates) into the final YYYY/MM/item directory structure."
        )
    )
    parser.add_argument(
        "--source-dir",
        required=True,
        help=(
            "Raw output root containing YYYY/MM/ subfolders of .nc files "
            "(e.g. .../output/energy_indicators/20150101/member01)."
        ),
    )
    parser.add_argument(
        "--target-collection-dir",
        required=True,
        help="Collection root that contains the target data/YYYY/MM layout.",
    )
    parser.add_argument(
        "--collection-id",
        help=(
            "Collection id to use in target item folder names. "
            "Defaults to the target collection directory name."
        ),
    )
    parser.add_argument("--model", default="ifs-nemo")
    parser.add_argument("--experiment", default="ssp3-7.0")
    parser.add_argument("--generation", default="2")
    parser.add_argument("--realization", default="1")
    parser.add_argument("--activity", default="projections")
    parser.add_argument("--resolution", default="high")
    add_mode_arguments(parser)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Apply changes. Without this flag the script is always a dry run.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing target file if it already exists.",
    )
    parser.add_argument(
        "--remove-empty-source-dirs",
        action="store_true",
        help="After --move, remove empty YYYY/MM directories left under the source dir.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"],
        help="Logging level (default: INFO).",
    )
    return parser.parse_args()


def remove_empty_dirs(root: Path) -> int:
    removed = 0
    for directory in sorted(root.rglob("*"), reverse=True):
        if not directory.is_dir():
            continue
        try:
            directory.rmdir()
            removed += 1
        except OSError:
            pass
    return removed


def find_year_month_dirs(source_dir: Path) -> list[tuple[str, str, Path]]:
    """Find <source_dir>/YYYY/MM/ subfolders. Returns (year, month, path) tuples."""
    year_dirs = sorted(p for p in source_dir.iterdir() if p.is_dir() and p.name.isdigit())
    return [
        (year_dir.name, f"{int(month_dir.name):02d}", month_dir)
        for year_dir in year_dirs
        for month_dir in sorted(p for p in year_dir.iterdir() if p.is_dir() and p.name.isdigit())
        if 1 <= int(month_dir.name) <= 12
    ]


def main() -> int:
    args = parse_args()
    logger = setup_logging("energy-mover", args.log_level)
    mode = mode_from_args(args)

    source_dir = Path(args.source_dir).expanduser().resolve()
    target_collection_dir = Path(args.target_collection_dir).expanduser().resolve()
    collection_id = args.collection_id or target_collection_dir.name

    if not source_dir.is_dir():
        raise SystemExit(f"Source directory does not exist: {source_dir}")

    target_data_dir = target_collection_dir / "data"
    if not target_data_dir.is_dir():
        raise SystemExit(f"Target data directory does not exist: {target_data_dir}")

    suffix_parts = [
        safe_slug(args.model),
        safe_slug(args.experiment),
        safe_slug(args.generation),
        safe_slug(args.realization),
        safe_slug(args.activity),
        safe_slug(args.resolution),
    ]

    year_month_dirs = find_year_month_dirs(source_dir)
    if not year_month_dirs:
        logger.warning("No YYYY/MM subfolders found under %s", source_dir)
        return 0

    stats = {
        "YYYY/MM folders with data": 0,
        "files seen": 0,
        "moved": 0,
        "copied": 0,
        "linked": 0,
        "overwritten": 0,
        "skipped existing": 0,
        "ignored (non-.nc, e.g. .pkl checkpoints)": 0,
    }

    for year, month, month_dir in year_month_dirs:
        nc_files = sorted(p for p in month_dir.glob("*.nc") if p.is_file())
        all_files = [p for p in month_dir.iterdir() if p.is_file()]
        stats["ignored (non-.nc, e.g. .pkl checkpoints)"] += len(all_files) - len(nc_files)
        if not nc_files:
            continue
        stats["YYYY/MM folders with data"] += 1

        last_day = calendar.monthrange(int(year), int(month))[1]
        start_timestamp = f"{year}{month}01T000000"
        end_timestamp = f"{year}{month}{last_day:02d}T230000"
        target_item_dir = (
            target_data_dir / year / month /
            join_item_folder_name(collection_id, start_timestamp, end_timestamp, suffix_parts)
        )

        for source_file in nc_files:
            stats["files seen"] += 1
            target_file = target_item_dir / source_file.name

            if target_file.exists() and not args.overwrite:
                stats["skipped existing"] += 1
                logger.info("Skipping existing target: %s", target_file)
                continue

            logger.info("[%s] %s -> %s", mode, source_file, target_file)
            if not args.execute:
                continue

            if target_file.exists():
                target_file.unlink()
                stats["overwritten"] += 1
            materialize_file(source_file, target_file, mode=mode, execute=True)
            stats[MATERIALIZED_STAT_KEY[mode]] += 1

    removed_dirs = 0
    if args.execute and args.move and args.remove_empty_source_dirs:
        removed_dirs = remove_empty_dirs(source_dir)
    stats["empty directories removed"] = removed_dirs

    log_move_summary(logger, not args.execute, stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
