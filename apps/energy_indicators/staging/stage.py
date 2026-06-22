#!/usr/bin/env python3
"""Energy Indicators staging on top of stac_dedl_core.

Reads ../catalog_config.yaml, writes collection metadata, and creates the
full data/YYYY/MM/<item>/ skeleton for every simulation × month. Unlike
HydroLand there is no data_type split: every NC file produced in a given
month (daily indicators + monthly aggregates) is an asset of the SAME item.

Dry run by default; pass --execute to apply changes.
"""
from __future__ import annotations

import argparse
import calendar
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

logger = logging.getLogger("energy-stage")


def create_monthly_skeleton(cfg: AppConfig, execute: bool = False) -> dict[str, int]:
    """Create data/YYYY/MM/<item>/ for every simulation × month (one item per month)."""
    stats: dict[str, int] = {"total": 0, "created": 0, "existing": 0}
    data_dir = cfg.collection_dir / "data"

    for sim in cfg.simulations:
        props = ordered_properties(sim.properties, cfg.property_order)
        # Energy's already-published item names use bare property values (e.g. "2",
        # "1") with NO "generation-"/"realization-" prefix, unlike HydroLand's
        # convention — so join_item_folder_name + safe_slug is used directly here
        # instead of build_item_folder_name (which always adds that prefix).
        suffix_parts = [safe_slug(v) for v in props.values()]
        n_months = (sim.end_year - sim.start_year + 1) * 12
        first_example: str | None = None

        for year in range(sim.start_year, sim.end_year + 1):
            for month in range(1, 13):
                last_day = calendar.monthrange(year, month)[1]
                start = f"{year}{month:02d}01T000000"
                end = f"{year}{month:02d}{last_day:02d}T230000"
                name = join_item_folder_name(cfg.id, start, end, suffix_parts)
                item_dir = data_dir / str(year) / f"{month:02d}" / name
                if first_example is None:
                    first_example = str(item_dir)
                stats["total"] += 1
                if item_dir.exists():
                    stats["existing"] += 1
                elif execute:
                    item_dir.mkdir(parents=True, exist_ok=True)
                    stats["created"] += 1
                logger.debug(
                    "%s%s", "" if execute else "[DRY RUN] would create: ", item_dir
                )

        label = f"{sim.properties.get('model', '?')} {sim.properties.get('experiment', '?')} ({sim.start_year}-{sim.end_year})"
        if execute:
            logger.info("Skeleton %s: %s folders created", label, n_months)
        else:
            logger.info(
                "[DRY RUN] Skeleton %s: would create %s folders\n"
                "          Example: %s",
                label, n_months, first_example,
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
    setup_logging("energy-stage", args.log_level)

    cfg = load_app_config(APP_DIR)
    logger.info("Collection: %s (%s simulations)", cfg.id, len(cfg.simulations))

    if args.execute:
        collection_path, config_path = write_collection_files(cfg, overwrite=True)
        logger.info("Wrote %s and %s", collection_path, config_path)
    else:
        logger.info("[DRY RUN] Would write collection.json + collection_config.json")

    create_monthly_skeleton(cfg, execute=args.execute)

    if not args.execute:
        logger.info("Dry run complete. Re-run with --execute to apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
