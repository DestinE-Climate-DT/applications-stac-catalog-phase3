#!/usr/bin/env python3
"""
Create empty Hydroland projection item folders and STAC item metadata.

This is for the staging case where monthly NetCDF files are not in the
collection yet, but the final item directories and metadata should already
exist. The generated item JSON files include the expected future asset hrefs.
"""

from __future__ import annotations

import argparse
import calendar
import json
import logging
from pathlib import Path
from typing import Any

from stac_dedl_core.staging import (
    format_catalog_property,
    join_item_folder_name as build_month_item_folder_name,
)


DEFAULT_COLLECTION_DIR = "EO.UFZ.DAT.HYDROLAND"
DEFAULT_DATA_TYPES = ("mhm", "mrm")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create IFS-NEMO projection YYYY/MM/item folders and item metadata "
            "for Hydroland before the NetCDF files are moved into place."
        )
    )
    parser.add_argument(
        "--collection-dir",
        default=DEFAULT_COLLECTION_DIR,
        help=(
            "Hydroland collection directory. Run from HDA/Usergenerated or pass "
            "an absolute path. Default: EO.UFZ.DAT.HYDROLAND"
        ),
    )
    parser.add_argument("--start-year", type=int, default=2015)
    parser.add_argument("--end-year", type=int, default=2049)
    parser.add_argument("--model", default="IFS-NEMO")
    parser.add_argument("--experiment", default="SSP3-7.0")
    parser.add_argument("--generation", default="2")
    parser.add_argument("--activity", default="projections")
    parser.add_argument("--realization", default="1")
    parser.add_argument(
        "--data-types",
        nargs="+",
        choices=DEFAULT_DATA_TYPES,
        default=list(DEFAULT_DATA_TYPES),
        help="Data types to scaffold. Default: mhm mrm",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually create directories and item JSON files. Without this, dry run.",
    )
    parser.add_argument(
        "--overwrite-items",
        action="store_true",
        help="Overwrite existing item JSON files for the selected projection items.",
    )
    parser.add_argument(
        "--indent",
        type=int,
        default=4,
        help="JSON indentation for generated item metadata. Default: 4",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"],
    )
    return parser.parse_args()


def setup_logging(level_name: str) -> logging.Logger:
    logging.basicConfig(
        level=getattr(logging, level_name.upper(), logging.INFO),
        format="%(levelname)s | %(message)s",
    )
    return logging.getLogger("hydroland-projection-scaffold")


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return payload


def formatted_properties(args: argparse.Namespace, data_type: str) -> dict[str, str]:
    return {
        "model": args.model,
        "experiment": args.experiment,
        "generation": format_catalog_property("generation", args.generation),
        "activity": args.activity,
        "realization": format_catalog_property("realization", args.realization),
        "data_type": data_type,
    }


def asset_filename(year: int, month: int, last_day: int, data_type: str) -> str:
    if data_type == "mhm":
        return (
            f"{year}_{month:02d}_01_T00_00_to_{year}_{month:02d}_{last_day:02d}"
            "_T23_00_mHM_Fluxes_States.nc"
        )
    if data_type == "mrm":
        return (
            f"{year}_{month:02d}_01_T00_00_to_{year}_{month:02d}_{last_day:02d}"
            "_T23_00_mRM_Fluxes_States.nc"
        )
    raise ValueError(f"Unsupported data type: {data_type}")


def date_fields(year: int, month: int, last_day: int, data_type: str) -> dict[str, str]:
    return {
        "start_stamp": f"{year}{month:02d}01T000000",
        "end_stamp": f"{year}{month:02d}{last_day:02d}T230000",
        "start_datetime": f"{year}-{month:02d}-01T00:00:00Z",
        "end_datetime": f"{year}-{month:02d}-{last_day:02d}T23:00:00Z",
        "datetime": f"{year}-{month:02d}-01T00:00:00Z",
    }


def geometry_from_bbox(bbox: list[int | float]) -> dict[str, Any]:
    minx, miny, maxx, maxy = bbox
    return {
        "type": "Polygon",
        "coordinates": [
            [
                [float(maxx), float(miny)],
                [float(maxx), float(maxy)],
                [float(minx), float(maxy)],
                [float(minx), float(miny)],
                [float(maxx), float(miny)],
            ]
        ],
    }


def build_item_id(
    collection_id: str,
    date_meta: dict[str, str],
    property_keys: list[str],
    properties: dict[str, str],
) -> str:
    missing = [key for key in property_keys if key not in properties]
    if missing:
        raise ValueError(
            "Cannot build item suffix. Missing configured property key(s): "
            + ", ".join(missing)
        )

    return build_month_item_folder_name(
        collection_id,
        date_meta["start_stamp"],
        date_meta["end_stamp"],
        [properties[key] for key in property_keys],
    )


def build_item_json(
    collection_id: str,
    collection_title: str,
    item_id: str,
    item_href: str,
    asset_name: str,
    bbox: list[int | float],
    date_meta: dict[str, str],
    properties: dict[str, str],
) -> dict[str, Any]:
    item_properties: dict[str, str] = dict(properties)
    item_properties.update(
        {
            "start_datetime": date_meta["start_datetime"],
            "end_datetime": date_meta["end_datetime"],
            "datetime": date_meta["datetime"],
        }
    )

    return {
        "type": "Feature",
        "stac_version": "1.0.0",
        "stac_extensions": [],
        "id": item_id,
        "geometry": geometry_from_bbox(bbox),
        "bbox": bbox,
        "properties": item_properties,
        "links": [
            {
                "rel": "collection",
                "href": (
                    "https://hda.data.destination-earth.eu/stac/v2/collections/"
                    f"{collection_id}"
                ),
                "type": "application/json",
                "title": collection_title,
            },
            {
                "rel": "self",
                "href": (
                    "https://hda.data.destination-earth.eu/stac/v2/collections/"
                    f"{collection_id}/items/{item_id}"
                ),
                "type": "application/json",
            },
        ],
        "assets": {
            asset_name: {
                "href": item_href,
                "type": "application/netcdf",
                "roles": ["data"],
            }
        },
        "collection": collection_id,
    }


def main() -> int:
    args = parse_args()
    logger = setup_logging(args.log_level)

    if args.start_year > args.end_year:
        raise SystemExit("--start-year must be less than or equal to --end-year")

    collection_dir = Path(args.collection_dir).expanduser().resolve()
    metadata_dir = collection_dir / "metadata"
    data_dir = collection_dir / "data"
    items_dir = metadata_dir / "items"
    collection_path = metadata_dir / "collection.json"
    config_path = metadata_dir / "collection_config.json"

    if not collection_path.is_file():
        raise SystemExit(f"Missing collection metadata: {collection_path}")
    if not config_path.is_file():
        raise SystemExit(f"Missing collection config: {config_path}")

    collection = read_json(collection_path)
    collection_config = read_json(config_path)
    collection_id = str(collection.get("id") or collection_dir.name)
    collection_title = str(collection.get("title") or collection_id)

    item_folder_level = collection_config.get("item_folder_level")
    if item_folder_level != "MM":
        raise SystemExit(
            f"Expected item_folder_level 'MM' in {config_path}, found {item_folder_level!r}"
        )

    property_keys = collection_config.get("additional_property_keys") or []
    if not isinstance(property_keys, list):
        raise SystemExit("collection_config additional_property_keys must be a list")

    bbox = collection_config.get("bbox")
    if not bbox:
        bbox = collection.get("extent", {}).get("spatial", {}).get("bbox", [[None]])[0]
    if not isinstance(bbox, list) or len(bbox) != 4:
        raise SystemExit("Could not read a 4-value bbox from collection_config/collection")

    stats = {
        "item_dirs": 0,
        "item_json_written": 0,
        "item_json_skipped": 0,
    }

    for year in range(args.start_year, args.end_year + 1):
        for month in range(1, 13):
            last_day = calendar.monthrange(year, month)[1]
            for data_type in args.data_types:
                properties = formatted_properties(args, data_type)
                date_meta = date_fields(year, month, last_day, data_type)
                item_id = build_item_id(
                    collection_id, date_meta, property_keys, properties
                )
                file_name = asset_filename(year, month, last_day, data_type)
                item_dir = data_dir / f"{year}" / f"{month:02d}" / item_id
                item_href = (
                    Path("data") / f"{year}" / f"{month:02d}" / item_id / file_name
                ).as_posix()
                item_path = items_dir / f"{item_id}.json"
                item_payload = build_item_json(
                    collection_id,
                    collection_title,
                    item_id,
                    item_href,
                    file_name,
                    bbox,
                    date_meta,
                    properties,
                )

                logger.debug("Scaffold item dir: %s", item_dir)
                stats["item_dirs"] += 1

                if item_path.exists() and not args.overwrite_items:
                    stats["item_json_skipped"] += 1
                    continue

                if args.execute:
                    item_dir.mkdir(parents=True, exist_ok=True)
                    items_dir.mkdir(parents=True, exist_ok=True)
                    with item_path.open("w", encoding="utf-8") as handle:
                        json.dump(item_payload, handle, indent=args.indent)
                        handle.write("\n")

                stats["item_json_written"] += 1

    logger.info(
        "Projection scaffold summary:\n"
        "- collection: %s\n"
        "- years: %s-%s\n"
        "- data types: %s\n"
        "- dry run: %s\n"
        "- item directories selected: %s\n"
        "- item JSON written: %s\n"
        "- item JSON skipped existing: %s",
        collection_dir,
        args.start_year,
        args.end_year,
        ", ".join(args.data_types),
        not args.execute,
        stats["item_dirs"],
        stats["item_json_written"],
        stats["item_json_skipped"],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
