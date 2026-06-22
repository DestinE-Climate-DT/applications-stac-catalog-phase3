#!/usr/bin/env python3
"""
Stage FWI NetCDF files into the STAC-ready YYYY/MM/item layout.

Unlike the other apps, --source-dir is the TOP-LEVEL directory containing one
subfolder per model (<source-dir>/<model>/...) — the model is read from that
subfolder name, not passed as a flag, and ALL models found are processed in
one run. Two source shapes are handled:

  <source-dir>/<model>/<run>/member01/*.nc   daily FWI files -> monthly items
  <source-dir>/<model>/Annual_Stat/*.nc      annual statistics -> yearly items
                                              (basic_and_days + quantiles +
                                              dailyclim_* all merged into ONE
                                              item per model × year)

experiment/activity are derived from each file's own year (FWI uses
"historical"/"ssp3-7.0" — see stage.py). Always a dry run unless --execute is
given. Must specify exactly one of --move, --copy, or --link.

Example (dry run — omit --execute to just see the plan):

    python move.py \
      --source-dir /scratch/project_465000454/poladesu/ReRuns_FWI \
      --target-collection-dir /path/to/EO.FMI.DAT.DESTINE_CLIMATE_WILDFIRE_FWI \
      --generation 2 --realization 1 --resolution 5km \
      --link --execute
"""

from __future__ import annotations

import argparse
import calendar
import logging
import re
from collections import defaultdict
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

DAILY_RE = re.compile(
    r"^(?P<year>\d{4})_(?P<month>\d{2})_(?P<day>\d{2})_T\d{2}_\d{2}_fwi\.nc$",
    re.IGNORECASE,
)
ANNUAL_RE = re.compile(
    r"^(?P<year>\d{4})_fwi_(?:basic_and_days|quantiles|dailyclim_[A-Za-z]+)\.nc$",
    re.IGNORECASE,
)

# Property order must match catalog_config.yaml's property_order exactly.
PROPERTY_ORDER = ["model", "experiment", "generation", "realization", "resolution", "activity", "data_type"]

MATERIALIZED_STAT_KEY = {"symlink": "linked", "copy": "copied", "move": "moved"}


def experiment_activity_for_year(year: int) -> tuple[str, str]:
    if 1990 <= year <= 2014:
        return "historical", "baseline"
    return "ssp3-7.0", "projections"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Stage FWI daily/annual NetCDF files into the final YYYY/MM/item "
            "directory structure. Scans every <source-dir>/<model>/ subfolder."
        )
    )
    parser.add_argument(
        "--source-dir",
        required=True,
        help="Top-level directory containing one subfolder per model.",
    )
    parser.add_argument(
        "--target-collection-dir",
        required=True,
        help="Collection root that contains the target data/YYYY/MM layout.",
    )
    parser.add_argument(
        "--collection-id",
        help="Collection id to use in target item folder names. Defaults to the target collection directory name.",
    )
    parser.add_argument("--generation", default="2")
    parser.add_argument("--realization", default="1")
    parser.add_argument("--resolution", default="5km")
    add_mode_arguments(parser)
    parser.add_argument(
        "--execute", action="store_true",
        help="Apply changes. Without this flag the script is always a dry run.",
    )
    parser.add_argument(
        "--overwrite", action="store_true",
        help="Replace an existing target file if it already exists.",
    )
    parser.add_argument(
        "--log-level", default="INFO",
        choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"],
    )
    return parser.parse_args()


def find_models(source_dir: Path) -> list[Path]:
    return sorted(p for p in source_dir.iterdir() if p.is_dir())


def materialize(
    source: Path, target: Path, mode: str, args: argparse.Namespace,
    logger: logging.Logger, stats: dict,
) -> None:
    if target.exists() and not args.overwrite:
        stats["skipped existing"] += 1
        logger.info("Skipping existing target: %s", target)
        return

    logger.info("[%s] %s -> %s", mode, source, target)
    if not args.execute:
        return

    if target.exists():
        target.unlink()
        stats["overwritten"] += 1
    materialize_file(source, target, mode=mode, execute=True)
    stats[MATERIALIZED_STAT_KEY[mode]] += 1


def main() -> int:
    args = parse_args()
    logger = setup_logging("fwi-mover", args.log_level)
    mode = mode_from_args(args)

    source_dir = Path(args.source_dir).expanduser().resolve()
    target_collection_dir = Path(args.target_collection_dir).expanduser().resolve()
    collection_id = args.collection_id or target_collection_dir.name

    if not source_dir.is_dir():
        raise SystemExit(f"Source directory does not exist: {source_dir}")
    target_data_dir = target_collection_dir / "data"
    if not target_data_dir.is_dir():
        raise SystemExit(f"Target data directory does not exist: {target_data_dir}")

    models = find_models(source_dir)
    if not models:
        logger.warning("No model subfolders found under %s", source_dir)
        return 0

    stats = {
        "models seen": len(models),
        "daily files seen": 0, "daily files recognized": 0,
        "annual files seen": 0, "annual files recognized": 0,
        "moved": 0, "copied": 0, "linked": 0, "overwritten": 0,
        "skipped existing": 0, "ignored": 0,
    }

    for model_dir in models:
        model = model_dir.name

        # --- Daily files -> monthly items ---
        for daily_file in sorted(model_dir.glob("*/member01/*.nc")):
            stats["daily files seen"] += 1
            match = DAILY_RE.match(daily_file.name)
            if not match:
                stats["ignored"] += 1
                logger.warning("Ignoring unrecognized daily filename: %s", daily_file.name)
                continue
            stats["daily files recognized"] += 1

            year, month = int(match.group("year")), int(match.group("month"))
            experiment, activity = experiment_activity_for_year(year)
            last_day = calendar.monthrange(year, month)[1]
            start = f"{year}{month:02d}01T000000"
            end = f"{year}{month:02d}{last_day:02d}T230000"
            values = {
                "model": model, "experiment": experiment, "generation": args.generation,
                "realization": args.realization, "resolution": args.resolution,
                "activity": activity, "data_type": "monthly",
            }
            suffix = [safe_slug(values[key]) for key in PROPERTY_ORDER]
            target_dir = target_data_dir / str(year) / f"{month:02d}" / join_item_folder_name(collection_id, start, end, suffix)
            materialize(daily_file, target_dir / daily_file.name, mode, args, logger, stats)

        # --- Annual statistics -> yearly items (grouped: 1 item per year, multiple files) ---
        annual_dir = model_dir / "Annual_Stat"
        if not annual_dir.is_dir():
            continue
        files_by_year: dict[int, list[Path]] = defaultdict(list)
        for annual_file in sorted(annual_dir.glob("*.nc")):
            stats["annual files seen"] += 1
            match = ANNUAL_RE.match(annual_file.name)
            if not match:
                stats["ignored"] += 1
                logger.warning("Ignoring unrecognized annual filename: %s", annual_file.name)
                continue
            stats["annual files recognized"] += 1
            files_by_year[int(match.group("year"))].append(annual_file)

        for year, files in sorted(files_by_year.items()):
            experiment, activity = experiment_activity_for_year(year)
            start = f"{year}0101T000000"
            end = f"{year}1231T230000"
            values = {
                "model": model, "experiment": experiment, "generation": args.generation,
                "realization": args.realization, "resolution": args.resolution,
                "activity": activity, "data_type": "yearly",
            }
            suffix = [safe_slug(values[key]) for key in PROPERTY_ORDER]
            target_dir = target_data_dir / str(year) / "01" / join_item_folder_name(collection_id, start, end, suffix)
            for annual_file in files:
                materialize(annual_file, target_dir / annual_file.name, mode, args, logger, stats)

    log_move_summary(logger, not args.execute, stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
