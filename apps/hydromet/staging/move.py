#!/usr/bin/env python3
"""
Gather HydroMet workflow output into one STAC collection root.

The Climate DT workflow already writes the STAC layout (see
workflow_items.py): every experiment ends up in

    <member>/EO.DWD.STAT.HYDROMET/data/<YYYY>/<item>/

with the item period and the __model__...__resolution suffix in the folder
name. This script takes one or more such outputs and links/copies/moves their
item folders into the collection root, keeping the year folder, the item
folder name and the file names exactly as the workflow wrote them. Nothing is
reclassified or renamed, so the period is always the experiment's own.

Not needed when the catalog is built directly in the workflow's folder
(CATALOG_HOME_DIR=<member>); then run stage.py and update.py only.

Item folders whose name does not follow the workflow scheme, and files that do
not start with their <start>_to_<end> period, are reported and skipped.
Always a dry run unless --execute is given. Exactly one of --move, --copy or
--link is required.

Example (dry run — omit --execute to just see the plan):

    python move.py \
      --source-dir /path/to/output/hydromet/19900101/member01 \
      --source-dir /path/to/output/hydromet/20150101/member01 \
      --link --execute
"""

from __future__ import annotations

import argparse
from pathlib import Path

from stac_dedl_core.appconfig import load_app_config
from stac_dedl_core.staging import (
    add_mode_arguments,
    log_move_summary,
    materialize_file,
    mode_from_args,
    setup_logging,
)
from workflow_items import FILENAME_RE, find_item_dirs, load_item, resolve_data_dir

APP_DIR = Path(__file__).resolve().parents[1]

MATERIALIZED_STAT_KEY = {"symlink": "linked", "copy": "copied", "move": "moved"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Gather HydroMet workflow output (<root>/data/<YYYY>/<item>/) into the "
            "STAC collection root, keeping all folder and file names."
        )
    )
    parser.add_argument(
        "--source-dir",
        action="append",
        required=True,
        help=(
            "Workflow output: the EO.DWD.STAT.HYDROMET folder, the member folder "
            "holding it, or its data/ folder. Repeat for several experiments."
        ),
    )
    parser.add_argument(
        "--target-collection-dir",
        help=(
            "Collection root to fill (holds data/ and metadata/). Defaults to "
            "<CATALOG_HOME_DIR>/<collection_root_dir> from catalog_config.yaml."
        ),
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
        help="After --move, remove source item folders that end up empty.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"],
        help="Logging level (default: INFO).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logger = setup_logging("hydromet-mover", args.log_level)
    mode = mode_from_args(args)

    cfg = load_app_config(APP_DIR)
    target_collection_dir = (
        Path(args.target_collection_dir) if args.target_collection_dir
        else cfg.collection_dir
    ).expanduser().resolve()
    target_data_dir = target_collection_dir / "data"
    if not target_data_dir.is_dir():
        raise SystemExit(
            f"Target data directory does not exist: {target_data_dir} (run stage.py --execute first)"
        )
    root_dir_name = cfg.collection_dir.name

    stats = {
        "items seen": 0,
        "invalid items": 0,
        "items already in place": 0,
        "files seen": 0,
        "moved": 0,
        "copied": 0,
        "linked": 0,
        "overwritten": 0,
        "skipped existing": 0,
        "ignored files": 0,
    }
    emptied_item_dirs: list[Path] = []

    for source in args.source_dir:
        data_dir = resolve_data_dir(Path(source).expanduser().resolve(), root_dir_name)
        item_dirs = find_item_dirs(data_dir)
        if not item_dirs:
            logger.warning("No item folders under %s", data_dir)

        for item_dir in item_dirs:
            stats["items seen"] += 1
            try:
                item = load_item(item_dir, cfg.id, cfg.property_order)
            except ValueError as exc:
                stats["invalid items"] += 1
                logger.error("Skipping item folder %s: name %s", item_dir, exc)
                continue

            target_item_dir = target_data_dir / item.year_folder / item.name
            if target_item_dir.resolve() == item_dir:
                stats["items already in place"] += 1
                logger.info("Already in the collection root: %s", item_dir)
                continue

            logger.info(
                "Item %s (%s to %s, %s)", item.name, f"{item.start:%Y-%m-%d}",
                f"{item.end:%Y-%m-%d}", ", ".join(f"{k}={v}" for k, v in item.properties.items()),
            )
            for source_file in sorted(p for p in item_dir.rglob("*") if p.is_file()):
                stats["files seen"] += 1
                if not FILENAME_RE.match(source_file.name):
                    stats["ignored files"] += 1
                    logger.warning("Ignoring unrecognized filename: %s", source_file)
                    continue

                target_file = target_item_dir / source_file.relative_to(item_dir)
                if (target_file.exists() or target_file.is_symlink()) and not args.overwrite:
                    stats["skipped existing"] += 1
                    logger.info("Skipping existing target: %s", target_file)
                    continue

                logger.info("[%s] %s -> %s", mode, source_file, target_file)
                if not args.execute:
                    continue

                if target_file.exists() or target_file.is_symlink():
                    target_file.unlink()
                    stats["overwritten"] += 1
                target_file.parent.mkdir(parents=True, exist_ok=True)
                materialize_file(source_file, target_file, mode=mode, execute=True)
                stats[MATERIALIZED_STAT_KEY[mode]] += 1

            emptied_item_dirs.append(item_dir)

    removed = 0
    if args.execute and args.move and args.remove_empty_source_dirs:
        for item_dir in emptied_item_dirs:
            for folder in sorted(
                (p for p in item_dir.rglob("*") if p.is_dir()), reverse=True
            ):
                try:
                    folder.rmdir()
                except OSError:
                    pass
            try:
                item_dir.rmdir()
                removed += 1
            except OSError:
                pass
    stats["source item dirs removed"] = removed

    log_move_summary(logger, not args.execute, stats)
    return 1 if stats["invalid items"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
