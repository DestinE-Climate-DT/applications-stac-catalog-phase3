#!/usr/bin/env python3
"""HydroMet staging on top of stac_dedl_core.

Reads ../catalog_config.yaml, writes collection metadata, and creates one
period-level item folder per simulation under data/<start_year>/<item>/.

Unlike HydroLand or Energy, HydroMet uses item_folder_level: YYYY — each item
spans a WHOLE simulation period (1990-2014 historical or 2015-2049
projection), not a single month. A single item can end up with many assets:
the DDF/KO_params NC files plus potentially thousands of individual extreme-
event CSV files for that period (see move.py).

Dry run by default; pass --execute to apply changes.
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

from stac_dedl_core.appconfig import AppConfig, load_app_config
from stac_dedl_core.collection_builder import write_collection_files
from stac_dedl_core.staging import (
    join_item_folder_name,
    ordered_properties,
    safe_slug,
    setup_logging,
)

APP_DIR = Path(__file__).resolve().parents[1]

logger = logging.getLogger("hydromet-stage")


def create_period_skeleton(cfg: AppConfig, execute: bool = False) -> dict[str, int]:
    """Create data/<start_year>/<item>/ — one folder per simulation."""
    stats: dict[str, int] = {"total": 0, "created": 0, "existing": 0}
    data_dir = cfg.collection_dir / "data"

    for sim in cfg.simulations:
        props = ordered_properties(sim.properties, cfg.property_order)
        # Bare property values (no "generation-"/"realization-" prefix), matching
        # the original staging script's plain string-concatenation convention.
        suffix_parts = [safe_slug(v) for v in props.values()]
        start = f"{sim.start_year}0101T000000"
        end = f"{sim.end_year}1231T230000"
        name = join_item_folder_name(cfg.id, start, end, suffix_parts)
        item_dir = data_dir / str(sim.start_year) / name

        stats["total"] += 1
        if item_dir.exists():
            stats["existing"] += 1
            logger.info("Already exists: %s", item_dir)
        elif execute:
            item_dir.mkdir(parents=True, exist_ok=True)
            stats["created"] += 1
            logger.info("Created: %s", item_dir)
        else:
            logger.info("[DRY RUN] would create: %s", item_dir)

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
    logger.info("Collection: %s (%s simulations)", cfg.id, len(cfg.simulations))

    if args.execute:
        collection_path, config_path = write_collection_files(cfg, overwrite=True)
        logger.info("Wrote %s and %s", collection_path, config_path)
    else:
        logger.info("[DRY RUN] Would write collection.json + collection_config.json")

    stats = create_period_skeleton(cfg, execute=args.execute)
    logger.info("Skeleton: %s", stats)

    if not args.execute:
        logger.info("Dry run complete. Re-run with --execute to apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
