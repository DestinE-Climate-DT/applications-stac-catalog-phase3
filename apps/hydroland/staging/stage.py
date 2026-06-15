#!/usr/bin/env python3
"""HydroLand staging on top of stac_dedl_core.

Reads ../catalog_config.yaml, writes collection metadata, creates one
period-level catalog folder per simulation, and (with --restructure)
materialises monthly mHM/mRM NetCDF files into the data/YYYY/MM/<item>/
layout. Dry run by default; pass --execute to apply changes.

Only HydroLand-specific knowledge lives here: the mHM/mRM filename patterns
and the legacy year-level folder layout.
"""
from __future__ import annotations

import argparse
import calendar
import logging
import re
from pathlib import Path

from stac_dedl_core.appconfig import AppConfig, load_app_config
from stac_dedl_core.collection_builder import write_collection_files
from stac_dedl_core.staging import (
    build_item_folder_name,
    classify_data_type,
    join_item_folder_name,
    materialize_file,
    ordered_properties,
)

APP_DIR = Path(__file__).resolve().parents[1]

logger = logging.getLogger("hydroland-stage")

MHM_FILE_RE = re.compile(
    r"^(?P<start_year>\d{4})_(?P<start_month>\d{2})_(?P<start_day>\d{2})"
    r"_to_"
    r"(?P<end_year>\d{4})_(?P<end_month>\d{2})_(?P<end_day>\d{2})"
    r"_daily_mHM_Fluxes_States\.nc$"
)

MRM_FILE_RE = re.compile(
    r"^(?P<start_year>\d{4})_(?P<start_month>\d{2})_(?P<start_day>\d{2})"
    r"_T(?P<start_hour>\d{2})_(?P<start_minute>\d{2})"
    r"_to_"
    r"(?P<end_year>\d{4})_(?P<end_month>\d{2})_(?P<end_day>\d{2})"
    r"_T(?P<end_hour>\d{2})_(?P<end_minute>\d{2})"
    r"_mRM_Fluxes_States\.nc$"
)

MHM_WITH_TIME_RE = re.compile(
    r"^(?P<start_year>\d{4})_(?P<start_month>\d{2})_(?P<start_day>\d{2})"
    r"_T(?P<start_hour>\d{2})_(?P<start_minute>\d{2})"
    r"_to_"
    r"(?P<end_year>\d{4})_(?P<end_month>\d{2})_(?P<end_day>\d{2})"
    r"_T(?P<end_hour>\d{2})_(?P<end_minute>\d{2})"
    r"_mHM_Fluxes_States\.nc$"
)


def parse_monthly_asset_filename(file_name: str) -> dict[str, str] | None:
    """Parse one monthly mHM/mRM NetCDF filename into timestamps + data_type."""
    for pattern, data_type, has_time in (
        (MHM_WITH_TIME_RE, "mhm", True),
        (MHM_FILE_RE, "mhm", False),
        (MRM_FILE_RE, "mrm", True),
    ):
        match = pattern.match(file_name)
        if not match:
            continue
        p = match.groupdict()
        if has_time:
            start = (
                f"{p['start_year']}{p['start_month']}{p['start_day']}"
                f"T{p['start_hour']}{p['start_minute']}00"
            )
            end = (
                f"{p['end_year']}{p['end_month']}{p['end_day']}"
                f"T{p['end_hour']}{p['end_minute']}00"
            )
        else:
            start = f"{p['start_year']}{p['start_month']}{p['start_day']}T000000"
            end = f"{p['end_year']}{p['end_month']}{p['end_day']}T230000"
        return {
            "year": p["start_year"],
            "month": p["start_month"],
            "start_timestamp": start,
            "end_timestamp": end,
            "data_type": data_type,
        }
    return None


# Decadal indicator products (floods/droughts/soil-moisture) do NOT follow the
# monthly mHM/mRM layout. Two filename date-prefixes are supported:
#   YYYY_MM_YYYY_MM_<token>.nc   e.g. 1990_01_2014_12_aridity_index.nc
#   YYYY_YYYY_<token>.nc         e.g. 1990_2049_soil_moisture_deficit_ref_SWC_L01.nc
# The trailing <token> becomes the item's data_type (e.g. aridity_index).
INDICATOR_YM_RE = re.compile(
    r"^(?P<sy>\d{4})_(?P<sm>\d{2})_(?P<ey>\d{4})_(?P<em>\d{2})_(?P<token>.+)\.nc$"
)
INDICATOR_YY_RE = re.compile(r"^(?P<sy>\d{4})_(?P<ey>\d{4})_(?P<token>.+)\.nc$")


def parse_indicator_filename(file_name: str) -> dict[str, str] | None:
    """Parse a decadal indicator filename into period timestamps + token."""
    match = INDICATOR_YM_RE.match(file_name)
    if match:
        p = match.groupdict()
        last = calendar.monthrange(int(p["ey"]), int(p["em"]))[1]
        return {
            "start_timestamp": f"{p['sy']}{p['sm']}01T000000",
            "end_timestamp": f"{p['ey']}{p['em']}{last:02d}T230000",
            "start_year": p["sy"],
            "token": p["token"],
        }
    match = INDICATOR_YY_RE.match(file_name)
    if match:
        p = match.groupdict()
        return {
            "start_timestamp": f"{p['sy']}0101T000000",
            "end_timestamp": f"{p['ey']}1231T230000",
            "start_year": p["sy"],
            "token": p["token"],
        }
    return None


def stage_indicators(
    cfg: AppConfig, link_mode: str = "symlink", execute: bool = False
) -> dict[str, int]:
    """Stage period-level indicator products as one item per file.

    Config (catalog_config.yaml `indicators:`):
      source_dir:           where the indicator .nc files live
      reference_simulation: simulation key for historical/reference indicators
      scenario_simulation:  simulation key for projection/scenario indicators
      scenario_markers:     token substrings that mean "scenario" (default:
                            [scen, percent_change]); everything else is reference

    Each file becomes data/<start_year>/01/<id>_<start>_<end>__<sim props>__<token>/.
    """
    stats = {"recognized": 0, "created_links": 0, "skipped_existing": 0, "ignored": 0}
    ind = cfg.indicators or {}
    source = ind.get("source_dir")
    if not source:
        logger.info("No indicators.source_dir configured — skipping indicator staging.")
        return stats

    source_dir = Path(source).expanduser()
    if not source_dir.is_absolute():
        source_dir = (Path.cwd() / source_dir).resolve()
    if not source_dir.is_dir():
        logger.warning("indicators.source_dir does not exist: %s", source_dir)
        return stats

    sims_by_key = {s.key: s for s in cfg.simulations}
    ref_key = ind.get("reference_simulation")
    scen_key = ind.get("scenario_simulation")
    markers = ind.get("scenario_markers", ["scen", "percent_change"])
    base_order = [k for k in cfg.property_order if k != "data_type"]

    def simulation_for(token: str):
        is_scenario = any(marker in token for marker in markers)
        key = scen_key if is_scenario else ref_key
        if key not in sims_by_key:
            raise KeyError(
                f"indicators references simulation '{key}', which is not in the "
                f"catalog_config.yaml `simulations:` list ({sorted(sims_by_key)})."
            )
        return sims_by_key[key]

    data_dir = cfg.collection_dir / "data"
    for asset_path in sorted(p for p in source_dir.rglob("*.nc") if p.is_file()):
        parsed = parse_indicator_filename(asset_path.name)
        if not parsed:
            stats["ignored"] += 1
            logger.debug("Ignoring unrecognized indicator filename: %s", asset_path.name)
            continue
        stats["recognized"] += 1

        sim = simulation_for(parsed["token"])
        properties = dict(ordered_properties(sim.properties, base_order))
        properties["data_type"] = parsed["token"]
        item_name = build_item_folder_name(
            cfg.id, parsed["start_timestamp"], parsed["end_timestamp"], properties
        )
        target = data_dir / parsed["start_year"] / "01" / item_name / asset_path.name
        if materialize_file(asset_path, target, mode=link_mode, execute=execute):
            stats["created_links"] += 1
            logger.info("%s%s -> %s", "" if execute else "[DRY RUN] ", asset_path, target)
        else:
            stats["skipped_existing"] += 1
    return stats


def create_catalog_folders(cfg: AppConfig, execute: bool = False) -> list[Path]:
    """Create data/<start_year>/<period item folder> for every simulation."""
    created: list[Path] = []
    base_order = [k for k in cfg.property_order if k != "data_type"]
    for sim in cfg.simulations:
        name = build_item_folder_name(
            cfg.id,
            f"{sim.start_year}0101T000000",
            f"{sim.end_year}1231T230000",
            ordered_properties(sim.properties, base_order),
        )
        target = cfg.collection_dir / "data" / str(sim.start_year) / name
        logger.info("%sCatalog folder: %s", "" if execute else "[DRY RUN] ", target)
        if execute:
            target.mkdir(parents=True, exist_ok=True)
        created.append(target)
    return created


def restructure_existing_data(
    cfg: AppConfig, link_mode: str = "symlink", execute: bool = False
) -> dict[str, int]:
    """Materialise monthly files from year-level item folders into YYYY/MM items."""
    data_dir = cfg.collection_dir / "data"
    stats = {
        "source_item_folders": 0,
        "recognized_files": 0,
        "created_links": 0,
        "skipped_existing": 0,
        "ignored_files": 0,
    }

    if not data_dir.is_dir():
        logger.info("No data directory at %s yet — nothing to restructure.", data_dir)
        return stats

    for year_dir in sorted(p for p in data_dir.iterdir() if p.is_dir()):
        for source_item_dir in sorted(p for p in year_dir.iterdir() if p.is_dir()):
            if not source_item_dir.name.startswith(f"{cfg.id}_"):
                continue
            stats["source_item_folders"] += 1
            suffix_parts = source_item_dir.name.split("__")[1:]
            expected_parts = len([k for k in cfg.property_order if k != "data_type"])
            if len(suffix_parts) != expected_parts:
                logger.warning(
                    "Expected %s suffix parts for %s but found %s. "
                    "Continuing with folder-derived values.",
                    expected_parts,
                    source_item_dir.name,
                    len(suffix_parts),
                )

            for asset_path in sorted(p for p in source_item_dir.rglob("*") if p.is_file()):
                parsed = parse_monthly_asset_filename(asset_path.name)
                if not parsed:
                    stats["ignored_files"] += 1
                    logger.debug("Ignoring non-monthly asset during restructure: %s", asset_path)
                    continue
                stats["recognized_files"] += 1

                # data_type defaults to the mHM/mRM token parsed from the filename,
                # but config-driven data_type_rules (if any) take precedence so apps
                # can add dimensions like river_discharge/soil_moisture from config.
                data_type = classify_data_type(
                    asset_path, cfg.data_type_rules, default=parsed["data_type"]
                )
                item_suffix = list(suffix_parts)
                if cfg.split_data_type_items:
                    item_suffix.append(data_type)

                target = (
                    data_dir
                    / parsed["year"]
                    / parsed["month"]
                    / join_item_folder_name(
                        cfg.id,
                        parsed["start_timestamp"],
                        parsed["end_timestamp"],
                        item_suffix,
                    )
                    / asset_path.name
                )
                if materialize_file(asset_path, target, mode=link_mode, execute=execute):
                    stats["created_links"] += 1
                    logger.info(
                        "%s%s -> %s", "" if execute else "[DRY RUN] ", asset_path, target
                    )
                else:
                    stats["skipped_existing"] += 1
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Apply changes. Without this flag everything is a dry run.",
    )
    parser.add_argument(
        "--restructure",
        action="store_true",
        help="Materialise monthly files from legacy year-level item folders.",
    )
    parser.add_argument(
        "--link-mode",
        default="symlink",
        choices=["symlink", "hardlink", "copy", "move"],
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"],
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level), format="%(levelname)s | %(message)s"
    )

    cfg = load_app_config(APP_DIR)
    logger.info("Collection: %s (%s simulations)", cfg.id, len(cfg.simulations))

    if args.execute:
        collection_path, config_path = write_collection_files(cfg, overwrite=True)
        logger.info("Wrote %s and %s", collection_path, config_path)
    else:
        logger.info("[DRY RUN] Would write collection.json + collection_config.json")

    create_catalog_folders(cfg, execute=args.execute)

    if args.restructure:
        stats = restructure_existing_data(
            cfg, link_mode=args.link_mode, execute=args.execute
        )
        logger.info("Restructure summary: %s", stats)

    if cfg.indicators:
        ind_stats = stage_indicators(
            cfg, link_mode=args.link_mode, execute=args.execute
        )
        logger.info("Indicator staging summary: %s", ind_stats)

    if not args.execute:
        logger.info("Dry run complete. Re-run with --execute to apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
