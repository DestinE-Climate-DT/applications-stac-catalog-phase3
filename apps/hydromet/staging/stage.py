#!/usr/bin/env python3
"""HydroMet staging on top of stac_dedl_core.

Reads ../catalog_config.yaml and writes metadata/collection.json and
metadata/collection_config.json into the collection root
(<CATALOG_HOME_DIR>/<collection_root_dir>, i.e. EO.DWD.STAT.HYDROMET, the
folder the Climate DT workflow writes and the root of the bucket).

Unlike the other apps, HydroMet does not create item folders: the workflow
already writes data/<YYYY>/<item>/, named after the experiment's own period and
REQUEST values (see workflow_items.py). This script only lists the item
folders it finds and reports any whose name does not follow that scheme, as
update.py would fail on them.

Dry run by default; pass --execute to apply changes.
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

from stac_dedl_core.appconfig import AppConfig, load_app_config
from stac_dedl_core.collection_builder import write_collection_files
from stac_dedl_core.staging import setup_logging
from workflow_items import find_item_dirs, load_item

APP_DIR = Path(__file__).resolve().parents[1]

logger = logging.getLogger("hydromet-stage")


def report_items(cfg: AppConfig) -> dict[str, int]:
    """List the workflow item folders under data/ and flag invalid names."""
    stats: dict[str, int] = {"items": 0, "invalid": 0}
    data_dir = cfg.collection_dir / "data"
    if not data_dir.is_dir():
        logger.info("No data/ folder yet in %s", cfg.collection_dir)
        return stats

    for item_dir in find_item_dirs(data_dir):
        stats["items"] += 1
        try:
            item = load_item(item_dir, cfg.id, cfg.property_order)
        except ValueError as exc:
            stats["invalid"] += 1
            logger.error("Invalid item folder %s: name %s", item_dir, exc)
            continue
        logger.info(
            "Item %s/%s (%s to %s)", item.year_folder, item.name,
            f"{item.start:%Y-%m-%d}", f"{item.end:%Y-%m-%d}",
        )
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Apply changes. Without this flag everything is a dry run.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"],
    )
    args = parser.parse_args()
    setup_logging("hydromet-stage", args.log_level)

    cfg = load_app_config(APP_DIR)
    logger.info("Collection: %s in %s", cfg.id, cfg.collection_dir)

    if args.execute:
        collection_path, config_path = write_collection_files(cfg, overwrite=True)
        logger.info("Wrote %s and %s", collection_path, config_path)
    else:
        logger.info("[DRY RUN] Would write collection.json + collection_config.json")

    stats = report_items(cfg)
    logger.info("Workflow items: %s", stats)

    if not args.execute:
        logger.info("Dry run complete. Re-run with --execute to apply.")
    return 1 if stats["invalid"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
