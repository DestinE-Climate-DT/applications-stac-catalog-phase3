#!/usr/bin/env python3
"""
Move Hydroland monthly NetCDF files into the final STAC-ready YYYY/MM/item
layout.

Historical legacy-folder example:
    python move_hydroland_monthly_data.py \
      --source-item-dir /work/lealroja/DestinE-DataLake-Lab/HDA/Usergenerated/EO.UFZ.DAT.HYDROLAND_OLD/data/1990/EO.UFZ.DAT.HYDROLAND_19900101T000000_20141231T230000__IFS-NEMO__hist__generation-2__baseline__realization-1 \
      --target-collection-dir /work/lealroja/DestinE-DataLake-Lab/HDA/Usergenerated/EO.UFZ.DAT.HYDROLAND \
      --execute

Projection flat-flux example:
    python move_hydroland_monthly_data.py \
      --source-flux-dir /work/lealroja/ifs-nemo/5km/projection_ba/hydroland/fluxes/mhm_daily \
      --target-collection-dir /work/lealroja/DestinE-DataLake-Lab/HDA/Usergenerated/EO.UFZ.DAT.HYDROLAND \
      --execute
"""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from stac_dedl_core.staging import (
    format_catalog_property,
    join_item_folder_name as build_month_item_folder_name,
)
from stage import parse_monthly_asset_filename


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Move monthly mHM/mRM NetCDF files from a legacy Hydroland item folder "
            "into the final YYYY/MM/item directory structure."
        )
    )
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument(
        "--source-item-dir",
        help="Legacy item folder containing monthly .nc files.",
    )
    source_group.add_argument(
        "--source-flux-dir",
        help=(
            "Flat projection flux folder containing monthly .nc files, such as "
            ".../fluxes/mhm or .../fluxes/mrm."
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
    parser.add_argument(
        "--model",
        default="IFS-NEMO",
        help="Model suffix for --source-flux-dir mode. Default: IFS-NEMO.",
    )
    parser.add_argument(
        "--experiment",
        default="SSP3-7.0",
        help="Experiment suffix for --source-flux-dir mode. Default: SSP3-7.0.",
    )
    parser.add_argument(
        "--generation",
        default="2",
        help="Generation suffix for --source-flux-dir mode. Default: 2.",
    )
    parser.add_argument(
        "--activity",
        default="projections",
        help="Activity suffix for --source-flux-dir mode. Default: projections.",
    )
    parser.add_argument(
        "--realization",
        default="1",
        help="Realization suffix for --source-flux-dir mode. Default: 1.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually move files. Without this flag the script performs a dry run.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing target file if it already exists.",
    )
    parser.add_argument(
        "--remove-empty-source-dirs",
        action="store_true",
        help="After moving, remove empty directories left under the source item dir.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"],
        help="Logging level (default: INFO).",
    )
    return parser.parse_args()


def setup_logging(level_name: str) -> logging.Logger:
    logging.basicConfig(
        level=getattr(logging, level_name.upper(), logging.INFO),
        format="%(levelname)s | %(message)s",
    )
    return logging.getLogger("hydroland-mover")


def remove_empty_dirs(root: Path) -> int:
    removed = 0
    for directory in sorted(root.rglob("*"), reverse=True):
        if directory.is_dir():
            try:
                directory.rmdir()
                removed += 1
            except OSError:
                pass
    return removed


def get_source_dir(args: argparse.Namespace) -> Path:
    raw_source_dir = args.source_item_dir or args.source_flux_dir
    return Path(raw_source_dir).expanduser().resolve()


def get_base_suffix_parts(args: argparse.Namespace, source_dir: Path) -> list[str]:
    if args.source_item_dir:
        suffix_parts = source_dir.name.split("__")[1:]
        if not suffix_parts:
            logging.getLogger("hydroland-mover").warning(
                "Source folder has no suffix metadata after '__': %s", source_dir.name
            )
        return suffix_parts

    return [
        format_catalog_property("model", args.model),
        format_catalog_property("experiment", args.experiment),
        format_catalog_property("generation", args.generation),
        format_catalog_property("activity", args.activity),
        format_catalog_property("realization", args.realization),
    ]


def main() -> int:
    args = parse_args()
    logger = setup_logging(args.log_level)

    source_dir = get_source_dir(args)
    target_collection_dir = Path(args.target_collection_dir).expanduser().resolve()
    collection_id = args.collection_id or target_collection_dir.name

    if not source_dir.is_dir():
        raise SystemExit(f"Source directory does not exist: {source_dir}")

    target_data_dir = target_collection_dir / "data"
    if not target_data_dir.is_dir():
        raise SystemExit(f"Target data directory does not exist: {target_data_dir}")

    suffix_parts = get_base_suffix_parts(args, source_dir)

    nc_files = sorted(path for path in source_dir.rglob("*.nc") if path.is_file())
    if not nc_files:
        logger.warning("No .nc files found in %s", source_dir)
        return 0

    stats = {
        "seen": 0,
        "recognized": 0,
        "moved": 0,
        "overwritten": 0,
        "skipped_existing": 0,
        "ignored": 0,
    }

    for source_file in nc_files:
        stats["seen"] += 1
        parsed = parse_monthly_asset_filename(source_file.name)
        if not parsed:
            stats["ignored"] += 1
            logger.warning("Ignoring unrecognized monthly filename: %s", source_file.name)
            continue

        stats["recognized"] += 1
        target_suffix_parts = [*suffix_parts, parsed["data_type"]]
        target_item_dir = (
            target_data_dir
            / parsed["year"]
            / parsed["month"]
            / build_month_item_folder_name(
                collection_id,
                parsed["start_timestamp"],
                parsed["end_timestamp"],
                target_suffix_parts,
            )
        )
        target_file = target_item_dir / source_file.name

        if target_file.exists() and not args.overwrite:
            stats["skipped_existing"] += 1
            logger.info("Skipping existing target: %s", target_file)
            continue

        logger.info("%s -> %s", source_file, target_file)

        if not args.execute:
            continue

        target_item_dir.mkdir(parents=True, exist_ok=True)
        if target_file.exists():
            target_file.unlink()
            stats["overwritten"] += 1

        shutil.move(str(source_file), str(target_file))
        stats["moved"] += 1

    removed_dirs = 0
    if args.execute and args.remove_empty_source_dirs:
        removed_dirs = remove_empty_dirs(source_dir)
        try:
            source_dir.rmdir()
            removed_dirs += 1
        except OSError:
            pass

    logger.info(
        "Summary:\n"
        "- dry run: %s\n"
        "- files seen: %s\n"
        "- recognized monthly files: %s\n"
        "- moved: %s\n"
        "- overwritten: %s\n"
        "- skipped existing: %s\n"
        "- ignored: %s\n"
        "- empty directories removed: %s",
        not args.execute,
        stats["seen"],
        stats["recognized"],
        stats["moved"],
        stats["overwritten"],
        stats["skipped_existing"],
        stats["ignored"],
        removed_dirs,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
