#!/usr/bin/env python3
"""FWI staging on top of stac_dedl_core.

Reads ../catalog_config.yaml, writes collection metadata, and creates the
data/YYYY/MM/<item>/ skeleton for every simulation. Unlike HydroLand, FWI has
two genuinely different item shapes that coexist:

- monthly items (data_type=monthly): one per simulation × month, built from
  daily FWI files — same shape as HydroLand's monthly mhm/mrm items.
- yearly items (data_type=yearly): one per simulation × year, built from that
  year's annual statistics files (basic_and_days, quantiles, dailyclim — all
  three merged into ONE item). Placed under the MM="01" subfolder to keep the
  same item_folder_level: MM layout, but the item id itself spans the whole
  year (YYYY0101-YYYY1231), not just January.

experiment/activity are derived from the year locally (FWI uses "historical"/
"ssp3-7.0", not the shared simulations.yaml's "hist"/"SSP3-7.0" spelling —
confirmed from the legacy stac_hda_fwi.py's experiment_from_year()), not read
from cfg.simulations properties.

Dry run by default; pass --execute to apply changes.
"""
from __future__ import annotations

import argparse
import calendar
import logging
from pathlib import Path

from stac_dedl_core.appconfig import AppConfig, load_app_config
from stac_dedl_core.collection_builder import write_collection_files
from stac_dedl_core.staging import join_item_folder_name, safe_slug, setup_logging

APP_DIR = Path(__file__).resolve().parents[1]

logger = logging.getLogger("fwi-stage")


def experiment_activity_for_year(year: int) -> tuple[str, str]:
    if 1990 <= year <= 2014:
        return "historical", "baseline"
    return "ssp3-7.0", "projections"


def suffix_parts(
    cfg: AppConfig, model: str, year: int, data_type: str,
    generation: object, realization: object, resolution: object,
) -> list[str]:
    experiment, activity = experiment_activity_for_year(year)
    values = {
        "model": model,
        "experiment": experiment,
        "generation": generation,
        "realization": realization,
        "resolution": resolution,
        "activity": activity,
        "data_type": data_type,
    }
    return [safe_slug(values[key]) for key in cfg.property_order]


def create_skeleton(cfg: AppConfig, execute: bool = False) -> dict[str, int]:
    stats: dict[str, int] = {"monthly_total": 0, "yearly_total": 0, "created": 0, "existing": 0}
    data_dir = cfg.collection_dir / "data"

    # generation/realization/resolution are constant across all simulations
    # (set via catalog_config.yaml `overrides:`), so any entry carries them.
    common = cfg.simulations[0].properties
    generation = common.get("generation", 2)
    realization = common.get("realization", 1)
    resolution = common.get("resolution", "5km")

    # One (model, start_year, end_year) per simulation entry — duplicates across
    # hist/proj for the same model are expected and harmless (different years).
    seen_models: dict[str, None] = {}
    for sim in cfg.simulations:
        model = sim.properties.get("model", "?")
        seen_models.setdefault(model)

        for year in range(sim.start_year, sim.end_year + 1):
            # Monthly items (data_type=monthly)
            for month in range(1, 13):
                last_day = calendar.monthrange(year, month)[1]
                start = f"{year}{month:02d}01T000000"
                end = f"{year}{month:02d}{last_day:02d}T230000"
                name = join_item_folder_name(
                    cfg.id, start, end,
                    suffix_parts(cfg, model, year, "monthly", generation, realization, resolution),
                )
                item_dir = data_dir / str(year) / f"{month:02d}" / name
                stats["monthly_total"] += 1
                _make(item_dir, execute, stats)

            # Yearly items (data_type=yearly), placed under month "01"
            start = f"{year}0101T000000"
            end = f"{year}1231T230000"
            name = join_item_folder_name(
                cfg.id, start, end,
                suffix_parts(cfg, model, year, "yearly", generation, realization, resolution),
            )
            item_dir = data_dir / str(year) / "01" / name
            stats["yearly_total"] += 1
            _make(item_dir, execute, stats)

    label = ", ".join(seen_models)
    total = stats["monthly_total"] + stats["yearly_total"]
    if execute:
        logger.info(
            "Skeleton for %s: %s folders created (%s monthly, %s yearly)",
            label, stats["created"], stats["monthly_total"], stats["yearly_total"],
        )
    else:
        logger.info(
            "[DRY RUN] Skeleton for %s: would create up to %s folders "
            "(%s monthly, %s yearly)",
            label, total, stats["monthly_total"], stats["yearly_total"],
        )
    return stats


def _make(item_dir: Path, execute: bool, stats: dict[str, int]) -> None:
    if item_dir.exists():
        stats["existing"] += 1
    elif execute:
        item_dir.mkdir(parents=True, exist_ok=True)
        stats["created"] += 1
    logger.debug("%s%s", "" if execute else "[DRY RUN] would create: ", item_dir)


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
    setup_logging("fwi-stage", args.log_level)

    cfg = load_app_config(APP_DIR)
    logger.info("Collection: %s (%s simulations)", cfg.id, len(cfg.simulations))

    if args.execute:
        collection_path, config_path = write_collection_files(cfg, overwrite=True)
        logger.info("Wrote %s and %s", collection_path, config_path)
    else:
        logger.info("[DRY RUN] Would write collection.json + collection_config.json")

    create_skeleton(cfg, execute=args.execute)

    if not args.execute:
        logger.info("Dry run complete. Re-run with --execute to apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
