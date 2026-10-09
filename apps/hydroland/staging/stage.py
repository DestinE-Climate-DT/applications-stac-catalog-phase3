#!/usr/bin/env python3
"""HydroLand staging on top of stac_dedl_core.

Reads ../catalog_config.yaml, writes collection metadata, and creates the
full data/YYYY/MM/<item>/ skeleton for every simulation × month × data_type.
Dry run by default; pass --execute to apply changes.
"""
from __future__ import annotations

import argparse
import calendar
import logging
import re
from pathlib import Path

from stac_dedl_core.appconfig import AppConfig, Simulation, load_app_config
from stac_dedl_core.collection_builder import write_collection_files
from stac_dedl_core.staging import (
    build_item_folder_name,
    materialize_file,
    ordered_properties,
    setup_logging,
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

# End-of-period stamp per data type, matching the items already published on the
# DEDL: mHM files hold daily means covering the whole last day (23:59:59), while
# mRM files hold hourly steps whose last stamp is 23:00:00. Some runs (IFS-FESOM
# historical) name daily mHM files with an hourly-style "_T00_00_to_..._T23_00_"
# pattern, so the stamp follows the data type, not the filename pattern.
MONTHLY_END_TIME = {"mhm": "T235959", "mrm": "T230000"}


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
        else:
            start = f"{p['start_year']}{p['start_month']}{p['start_day']}T000000"
        end = (
            f"{p['end_year']}{p['end_month']}{p['end_day']}"
            f"{MONTHLY_END_TIME[data_type]}"
        )
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

    def simulation_for(token: str) -> Simulation | None:
        is_scenario = any(marker in token for marker in markers)
        key = scen_key if is_scenario else ref_key
        if key not in sims_by_key:
            logger.warning(
                "Skipping indicator file with token '%s': simulation '%s' is not "
                "in the active catalog_config.yaml `simulations:` list (%s). "
                "Uncomment it there to stage this indicator.",
                token, key, sorted(sims_by_key),
            )
            return None
        return sims_by_key[key]

    data_dir = cfg.collection_dir / "data"
    for asset_path in sorted(p for p in source_dir.rglob("*.nc") if p.is_file()):
        parsed = parse_indicator_filename(asset_path.name)
        if not parsed:
            stats["ignored"] += 1
            logger.debug("Ignoring unrecognized indicator filename: %s", asset_path.name)
            continue

        sim = simulation_for(parsed["token"])
        if sim is None:
            stats["ignored"] += 1
            continue
        stats["recognized"] += 1
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


def create_monthly_skeleton(cfg: AppConfig, execute: bool = False) -> dict[str, int]:
    """Create data/YYYY/MM/<item>/ for every simulation × month × data_type.

    Data types are read from cfg.data_type_rules (unique 'data_type' values in
    declaration order). Falls back to ['mhm', 'mrm'] when no rules are defined.
    """
    if cfg.data_type_rules:
        seen: dict[str, None] = {}
        for rule in cfg.data_type_rules:
            seen.setdefault(rule["data_type"])
        data_types = list(seen)
    else:
        data_types = ["mhm", "mrm"]

    base_order = [k for k in cfg.property_order if k != "data_type"]
    data_dir = cfg.collection_dir / "data"
    stats: dict[str, int] = {"total": 0, "created": 0, "existing": 0}

    for sim in cfg.simulations:
        base_props = ordered_properties(sim.properties, base_order)
        n_months = (sim.end_year - sim.start_year + 1) * 12
        first_example: str | None = None

        for year in range(sim.start_year, sim.end_year + 1):
            for month in range(1, 13):
                last_day = calendar.monthrange(year, month)[1]
                start = f"{year}{month:02d}01T000000"
                for data_type in data_types:
                    end = (
                        f"{year}{month:02d}{last_day:02d}"
                        f"{MONTHLY_END_TIME.get(data_type, 'T230000')}"
                    )
                    props = {**base_props, "data_type": data_type}
                    name = build_item_folder_name(
                        cfg.id, start, end,
                        ordered_properties(props, cfg.property_order),
                    )
                    item_dir = data_dir / str(year) / f"{month:02d}" / name
                    if first_example is None:
                        first_example = str(item_dir)
                    stats["total"] += 1
                    if item_dir.exists():
                        stats["existing"] += 1
                    elif execute:
                        item_dir.mkdir(parents=True, exist_ok=True)
                        stats["created"] += 1
                    # individual paths logged at DEBUG only to avoid flooding
                    logger.debug(
                        "%s%s",
                        "" if execute else "[DRY RUN] would create: ",
                        item_dir,
                    )

        label = f"{sim.properties.get('model', '?')} {sim.properties.get('experiment', '?')} ({sim.start_year}-{sim.end_year})"
        n_folders = n_months * len(data_types)
        if execute:
            logger.info("Skeleton %s: %s folders created", label, n_folders)
        else:
            logger.info(
                "[DRY RUN] Skeleton %s: would create %s folders (data types: %s)\n"
                "          Example: %s",
                label, n_folders, ", ".join(data_types), first_example,
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
    setup_logging("hydroland-stage", args.log_level)

    cfg = load_app_config(APP_DIR)
    logger.info("Collection: %s (%s simulations)", cfg.id, len(cfg.simulations))

    if args.execute:
        collection_path, config_path = write_collection_files(cfg, overwrite=True)
        logger.info("Wrote %s and %s", collection_path, config_path)
    else:
        logger.info("[DRY RUN] Would write collection.json + collection_config.json")

    create_monthly_skeleton(cfg, execute=args.execute)

    if cfg.indicators:
        ind_stats = stage_indicators(cfg, execute=args.execute)
        logger.info("Indicator staging summary: %s", ind_stats)

    if not args.execute:
        logger.info("Dry run complete. Re-run with --execute to apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
