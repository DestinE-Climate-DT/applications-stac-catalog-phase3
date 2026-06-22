#!/usr/bin/env python3
"""
Stage HydroMet NetCDF/CSV files into the STAC-ready <start_year>/item layout.

HydroMet's source data (DDF.nc, KO_params.nc parameter files, and event
catalogue CSV files) is a flat directory per model, with no item folder
structure. Each file is classified into the historical (1990-2014) or
projection (2015-2049) period purely from the START year embedded in its own
filename, then linked/copied/moved as-is into that period's pre-built item
folder (built by stage.py). Always a dry run unless --execute is given. Must
specify exactly one of --move, --copy, or --link.

Example (dry run — omit --execute to just see the plan):

    python move.py \
      --source-dir /path/to/appdata/IFS-NEMO \
      --target-collection-dir /path/to/EO.DWD.STAT.HYDROMET_EXTREMES \
      --model IFS-NEMO --generation 2 --realization 1 --resolution 5km \
      --link --execute
"""

from __future__ import annotations

import argparse
import re
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

# Two filename patterns seen in HydroMet output:
#   YYYY_MM_DD_THH_MM_to_YYYY_MM_DD_THH_MM_<token>.nc   (DDF, KO_params)
#   YYYY_MM_DD_THH_MM_to_YYYY_MM_DD_THH_MM_<token>.csv  (event catalogues)
# Only the START year is used to classify the file into a period — the file's
# own (possibly narrow) date range is preserved as-is in its filename.
FILENAME_RE = re.compile(
    r"^(?P<sy>\d{4})_\d{2}_\d{2}_T\d{2}_\d{2}_to_\d{4}_\d{2}_\d{2}_T\d{2}_\d{2}_.+\.(nc|csv)$"
)

# Canonical period definitions, matching apps/_shared/simulations.yaml's
# generation-2 historical/projection entries.
PERIODS = [
    {"start_year": 1990, "end_year": 2014, "experiment": "hist", "activity": "baseline"},
    {"start_year": 2015, "end_year": 2049, "experiment": "SSP3-7.0", "activity": "projections"},
]

MATERIALIZED_STAT_KEY = {"symlink": "linked", "copy": "copied", "move": "moved"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Stage HydroMet NetCDF/CSV files into the final <start_year>/item "
            "directory structure, classified by the start year in each filename."
        )
    )
    parser.add_argument(
        "--source-dir",
        required=True,
        help="Flat directory of .nc/.csv files for one model (not recursive).",
    )
    parser.add_argument(
        "--target-collection-dir",
        required=True,
        help="Collection root that contains the target data/<start_year> layout.",
    )
    parser.add_argument(
        "--collection-id",
        help=(
            "Collection id to use in target item folder names. "
            "Defaults to the target collection directory name."
        ),
    )
    parser.add_argument("--model", default="IFS-NEMO")
    parser.add_argument("--generation", default="2")
    parser.add_argument("--realization", default="1")
    parser.add_argument("--resolution", default="5km")
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
        help="After --move, remove the source dir if it ends up empty.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"],
        help="Logging level (default: INFO).",
    )
    return parser.parse_args()


def period_for_year(year: int) -> dict | None:
    for period in PERIODS:
        if period["start_year"] <= year <= period["end_year"]:
            return period
    return None


def main() -> int:
    args = parse_args()
    logger = setup_logging("hydromet-mover", args.log_level)
    mode = mode_from_args(args)

    source_dir = Path(args.source_dir).expanduser().resolve()
    target_collection_dir = Path(args.target_collection_dir).expanduser().resolve()
    collection_id = args.collection_id or target_collection_dir.name

    if not source_dir.is_dir():
        raise SystemExit(f"Source directory does not exist: {source_dir}")

    target_data_dir = target_collection_dir / "data"
    if not target_data_dir.is_dir():
        raise SystemExit(f"Target data directory does not exist: {target_data_dir}")

    source_files = sorted(
        p for p in source_dir.iterdir() if p.is_file() and p.suffix in (".nc", ".csv")
    )
    if not source_files:
        logger.warning("No .nc/.csv files found in %s", source_dir)
        return 0

    stats = {
        "files seen": 0,
        "recognized": 0,
        "moved": 0,
        "copied": 0,
        "linked": 0,
        "overwritten": 0,
        "skipped existing": 0,
        "ignored": 0,
    }

    for source_file in source_files:
        stats["files seen"] += 1
        match = FILENAME_RE.match(source_file.name)
        if not match:
            stats["ignored"] += 1
            logger.warning("Ignoring unrecognized filename: %s", source_file.name)
            continue

        period = period_for_year(int(match.group("sy")))
        if period is None:
            stats["ignored"] += 1
            logger.warning(
                "Ignoring %s: start year %s is outside known periods (%s)",
                source_file.name, match.group("sy"),
                [(p["start_year"], p["end_year"]) for p in PERIODS],
            )
            continue
        stats["recognized"] += 1

        suffix_parts = [
            safe_slug(args.model),
            safe_slug(period["experiment"]),
            safe_slug(args.generation),
            safe_slug(args.realization),
            safe_slug(period["activity"]),
            safe_slug(args.resolution),
        ]
        start_timestamp = f"{period['start_year']}0101T000000"
        end_timestamp = f"{period['end_year']}1231T230000"
        target_item_dir = (
            target_data_dir / str(period["start_year"]) /
            join_item_folder_name(collection_id, start_timestamp, end_timestamp, suffix_parts)
        )
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

    removed = False
    if args.execute and args.move and args.remove_empty_source_dirs:
        try:
            source_dir.rmdir()
            removed = True
        except OSError:
            pass
    stats["source dir removed"] = removed

    log_move_summary(logger, not args.execute, stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
