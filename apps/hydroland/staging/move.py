#!/usr/bin/env python3
"""
Stage Hydroland monthly NetCDF files into the STAC-ready YYYY/MM/item layout.

Always a dry run unless --execute is given. Must specify exactly one of
--move, --copy, or --link.

Examples (dry run — omit --execute to just see the plan):

    # Symlink historical mHM files (source kept in place):
    python move.py \
      --source-flux-dir /data/hsd/.../historical/mhm \
      --target-collection-dir /work/.../EO.UFZ.DAT.HYDROLAND \
      --model IFS-NEMO --experiment hist --generation 2 --activity baseline --realization 1 \
      --link --execute

    # Move projection mRM files (source removed):
    python move.py \
      --source-flux-dir /data/hsd/.../projection/mrm \
      --target-collection-dir /work/.../EO.UFZ.DAT.HYDROLAND \
      --model IFS-NEMO --experiment SSP3-7.0 --generation 2 --activity projections --realization 1 \
      --move --execute
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from stac_dedl_core.staging import (
    add_mode_arguments,
    format_catalog_property,
    join_item_folder_name,
    log_move_summary,
    materialize_file,
    mode_from_args,
    setup_logging,
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
        help="After --move, remove empty directories left under the source dir.",
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


def get_source_dir(args: argparse.Namespace) -> Path:
    raw_source_dir = args.source_item_dir or args.source_flux_dir
    return Path(raw_source_dir).expanduser().resolve()


def get_base_suffix_parts(
    args: argparse.Namespace, source_dir: Path, logger: logging.Logger
) -> list[str]:
    if args.source_item_dir:
        suffix_parts = source_dir.name.split("__")[1:]
        if not suffix_parts:
            logger.warning(
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
    logger = setup_logging("hydroland-mover", args.log_level)
    mode = mode_from_args(args)

    source_dir = get_source_dir(args)
    target_collection_dir = Path(args.target_collection_dir).expanduser().resolve()
    collection_id = args.collection_id or target_collection_dir.name

    if not source_dir.is_dir():
        raise SystemExit(f"Source directory does not exist: {source_dir}")

    target_data_dir = target_collection_dir / "data"
    if not target_data_dir.is_dir():
        raise SystemExit(f"Target data directory does not exist: {target_data_dir}")

    suffix_parts = get_base_suffix_parts(args, source_dir, logger)

    nc_files = sorted(path for path in source_dir.rglob("*.nc") if path.is_file())
    if not nc_files:
        logger.warning("No .nc files found in %s", source_dir)
        return 0

    stats = {
        "files seen": 0,
        "recognized monthly files": 0,
        "moved": 0,
        "copied": 0,
        "linked": 0,
        "overwritten": 0,
        "skipped existing": 0,
        "ignored": 0,
    }
    materialized_stat_key = {"symlink": "linked", "copy": "copied", "move": "moved"}

    for source_file in nc_files:
        stats["files seen"] += 1
        parsed = parse_monthly_asset_filename(source_file.name)
        if not parsed:
            stats["ignored"] += 1
            logger.warning("Ignoring unrecognized monthly filename: %s", source_file.name)
            continue

        stats["recognized monthly files"] += 1
        target_item_dir = (
            target_data_dir
            / parsed["year"]
            / parsed["month"]
            / join_item_folder_name(
                collection_id,
                parsed["start_timestamp"],
                parsed["end_timestamp"],
                [*suffix_parts, parsed["data_type"]],
            )
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
        stats[materialized_stat_key[mode]] += 1

    removed_dirs = 0
    if args.execute and args.move and args.remove_empty_source_dirs:
        removed_dirs = remove_empty_dirs(source_dir)
        try:
            source_dir.rmdir()
            removed_dirs += 1
        except OSError:
            pass
    stats["empty directories removed"] = removed_dirs

    log_move_summary(logger, not args.execute, stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
