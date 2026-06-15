import pystac
import os
from pathlib import Path
import re
from datetime import datetime

from stac_dedl_core.config import (
    ITEM_FOLDER_LEVEL,
    ITEM_FOLDER_LEVEL_DD,
    ITEM_FOLDER_LEVEL_MM,
    ITEM_FOLDER_NAMING_CONVENTION_TYPE,
    ItemFolderNamingConventionType,
)
from stac_dedl_core.usergenerated.config import confighelper


def get_media_type(file_path):
    """Get the media type for a file based on its extension."""
    _, ext = os.path.splitext(file_path)

    extension_to_media_type = {
        ".tif": pystac.MediaType.COG,
        ".png": pystac.MediaType.PNG,
        ".jpg": pystac.MediaType.JPEG,
        ".json": pystac.MediaType.JSON,
        ".html": pystac.MediaType.HTML,
        ".txt": pystac.MediaType.TEXT,
        ".xml": pystac.MediaType.XML,
        ".pdf": pystac.MediaType.PDF,
        ".nc": pystac.MediaType.NETCDF,
        ".csv": "text/csv",
        ".npy": "application/x-npy",
    }

    media_type = extension_to_media_type.get(ext.lower())
    if media_type is None:
        raise ValueError(f"Unsupported MediaType for file extension: {ext}")
    return media_type


def get_asset_role(media_type: str, asset_href: Path, thumbnail_regex: str, overview_regex: str):
    data = [
        pystac.MediaType.COG, pystac.MediaType.FLATGEOBUF, pystac.MediaType.GEOPACKAGE,
        pystac.MediaType.GEOTIFF, pystac.MediaType.HDF, pystac.MediaType.HDF5,
        pystac.MediaType.JPEG, pystac.MediaType.JPEG2000, pystac.MediaType.PARQUET,
        pystac.MediaType.PNG, pystac.MediaType.TIFF, pystac.MediaType.KML,
        pystac.MediaType.ZARR, pystac.MediaType.NETCDF,
        "text/csv", "application/x-npy",
    ]
    metadata = [
        pystac.MediaType.GEOJSON, pystac.MediaType.HTML, pystac.MediaType.JSON,
        pystac.MediaType.TEXT, pystac.MediaType.XML, pystac.MediaType.PDF,
    ]

    if re.match(thumbnail_regex, asset_href.name):
        return ["thumbnail"]
    if re.match(overview_regex, asset_href.name):
        return ["overview"]
    elif media_type in data:
        return ["data"]
    elif media_type in metadata:
        return ["metadata"]
    else:
        raise ValueError(f"Could not determine asset role for asset '{asset_href.name}'.")


def get_item_properties(item_id: str, collection_id: str, additional_property_keys: list):
    """
    Parse item_id to extract datetime and additional properties.

    item_id expected forms:
    - EO.XXX.YYY.ZZZ_20241116T000000_20241116T115959  (start + end)
    - EO.XXX.YYY.ZZZ_20241116T000000                  (datetime only)
    With optional suffix: __META1__META2
    """
    properties = {}

    if "__" in item_id:
        additional_property_parts = item_id.split("__")
        item_id = additional_property_parts[0]
        if len(additional_property_keys) > 0:
            if len(additional_property_parts[1:]) != len(additional_property_keys):
                raise ValueError("Number of additional properties does not match the number of additional property keys.")
            properties.update(dict(zip(additional_property_keys, additional_property_parts[1:])))

    if item_id.startswith(collection_id):
        item_id = item_id[len(collection_id) + 1:]
    else:
        raise ValueError("Item ID does not start with the Collection ID.")

    parts = item_id.split("_")

    if ITEM_FOLDER_NAMING_CONVENTION_TYPE == ItemFolderNamingConventionType.NON_STANDARD_1:
        parts = parts[1:]

    if len(parts) not in [1, 2]:
        raise ValueError("Invalid number of parts in item_id. Expected 1 or 2 parts.")

    start = parts[0] if len(parts) >= 1 else None
    end = parts[1] if len(parts) == 2 else None

    item_datetime: datetime = None

    if start and end:
        start_datetime = datetime.strptime(start, "%Y%m%dT%H%M%S")
        end_datetime = datetime.strptime(end, "%Y%m%dT%H%M%S")
        properties["start_datetime"] = start_datetime.strftime("%Y-%m-%dT%H:%M:%SZ")
        properties["end_datetime"] = end_datetime.strftime("%Y-%m-%dT%H:%M:%SZ")
        item_datetime = start_datetime
    elif start:
        item_datetime = datetime.strptime(start, "%Y%m%dT%H%M%S")
    else:
        raise ValueError("Item must have a start and end datetime.")

    return (item_datetime, properties)


def guess_mime_type_advanced(file_path):
    """Guess MIME type using python-magic (content-based, not extension-based)."""
    try:
        import magic
    except ImportError:
        raise ImportError("python-magic requires libmagic. Install via: conda install -c conda-forge python-magic")
    mime = magic.Magic(mime=True)
    return mime.from_file(file_path)


def is_valid_year(year_str: str, min_year: int = 1700, max_year: int = 2200) -> bool:
    if not (year_str.isdigit() and len(year_str) == 4):
        return False
    return min_year <= int(year_str) <= max_year


def get_datetime_from_folder_path(item_folder_path_parts, collection_config, item_id, collection_id):
    year_from_folder_path = item_folder_path_parts[2]

    if (
        not collection_config[ITEM_FOLDER_LEVEL]
        or collection_config[ITEM_FOLDER_LEVEL] == ITEM_FOLDER_LEVEL_MM
        or collection_config[ITEM_FOLDER_LEVEL] == ITEM_FOLDER_LEVEL_DD
    ):
        month_from_folder_path = item_folder_path_parts[3]
    else:
        month_from_folder_path = "01"

    if (
        not collection_config[ITEM_FOLDER_LEVEL]
        or collection_config[ITEM_FOLDER_LEVEL] == ITEM_FOLDER_LEVEL_DD
    ):
        day_from_folder_path = item_folder_path_parts[4]
    else:
        day_from_folder_path = "01"

    print(
        f"item_id:{item_id}, collection_id:{collection_id}, "
        f"year:{year_from_folder_path}, month:{month_from_folder_path}, day:{day_from_folder_path}"
    )

    return datetime(int(year_from_folder_path), int(month_from_folder_path), int(day_from_folder_path))


def get_item_date_overide(config_list):
    item_date_overide = confighelper.get_config_value(config_list, "item_date_overide", True)
    if item_date_overide:
        return datetime.strptime(item_date_overide, "%Y%m%d")
    return None
