import logging
import os
import json
import pystac
from datetime import datetime
from pathlib import Path
from shapely.geometry import box, mapping
from typing import List, Dict, Any, Optional


from stac_dedl_core.config import (
    APP_LOGGER_NAME,
    IS_OVERWRITE_S3,
    IS_UPLOAD_S3,
    ITEM_CONFIG_FILE_NAME,
    ITEM_CONFIG_OPTIONAL,
    ITEM_FOLDER_LEVEL,
    ITEM_FOLDER_LEVEL_DD,
    ITEM_FOLDER_LEVEL_MM,
    ITEM_FOLDER_LEVEL_NONE,
    ITEM_FOLDER_LEVEL_YYYY,
    ADDITIONAL_PROPERTY_KEYS,
    S3_ENDPOINT_URL,
    S3_USER_GENERATED_BUCKET_PREFIX,
    STAC_VERSION,
)

import stac_dedl_core.usergenerated.logging_config  # must be imported before other modules
from stac_dedl_core.usergenerated import datetools
from stac_dedl_core.usergenerated.config import confighelper
from stac_dedl_core.usergenerated.item import itemhelper
from stac_dedl_core.usergenerated.s3tools import S3Tools
from stac_dedl_core.usergenerated.env_utils import validate_aws_credentials

logger = logging.getLogger(APP_LOGGER_NAME)


class ItemGenerator:

    def __init__(self, collection_id: str, overide_bucket_name: Optional[str] = None) -> None:
        """
        Class to generate STAC Item metadata for a given collection.

        The class is initialized with the collection ID that you have been provided with
        (Case-sensitive, use UpperCase) e.g. 'EO.XXX.YYY.ZZZ-ZZZ'

        An optional overide_bucket_name can be provided to upload the generated metadata to S3 (Case-sensitive)
        If not provided, the bucket_name is assumed to be 'usergenerated-proposal-[collection_id]'
        e.g. 'usergenerated-proposal-EO.XXX.YYY.ZZZ-ZZZ'

        Args:
            collection_id: The collection identifier to process
            overide_bucket_name: Optional override for the S3 bucket name

        Raises:
            ValueError: If collection_id contains dash or credentials are not set
        """
        self.collection_id = collection_id

        if "-" in collection_id:
            raise ValueError(
                "collection_id cannot contain a dash ('-'). Only underscores ('_') are permitted in a dedl Collection ID."
            )

        self.overide_bucket_name = overide_bucket_name

        self.collection_root = Path(collection_id)
        self.collection_path = Path(f"{collection_id}/metadata/collection.json")
        self.collection_config_path = Path(f"{collection_id}/metadata/collection_config.json")
        self.items_root = Path(f"{collection_id}/metadata/items")
        self.data_root = Path(f"{collection_id}/data")

        self.is_overwrite_s3 = IS_OVERWRITE_S3
        self.aws_access_key_id, self.aws_secret_access_key = validate_aws_credentials()

        self.s3tools = S3Tools(
            self.aws_access_key_id, self.aws_secret_access_key, self.is_overwrite_s3
        )

    def _get_item_folders_by_level(self, folder_level: str) -> List[Path]:
        item_folder_paths: List[Path] = []

        if folder_level == ITEM_FOLDER_LEVEL_DD:
            for year_folder in self.data_root.iterdir():
                if year_folder.is_dir():
                    for month_folder in year_folder.iterdir():
                        if month_folder.is_dir():
                            for day_folder in month_folder.iterdir():
                                if day_folder.is_dir():
                                    for item_folder in day_folder.iterdir():
                                        if item_folder.is_dir():
                                            item_folder_paths.append(item_folder)

        elif folder_level == ITEM_FOLDER_LEVEL_MM:
            for year_folder in self.data_root.iterdir():
                if year_folder.is_dir():
                    for month_folder in year_folder.iterdir():
                        if month_folder.is_dir():
                            for item_folder in month_folder.iterdir():
                                if item_folder.is_dir():
                                    item_folder_paths.append(item_folder)

        elif folder_level == ITEM_FOLDER_LEVEL_YYYY:
            for year_folder in self.data_root.iterdir():
                if year_folder.is_dir():
                    for item_folder in year_folder.iterdir():
                        if item_folder.is_dir():
                            item_folder_paths.append(item_folder)

        elif folder_level == ITEM_FOLDER_LEVEL_NONE:
            for item_folder in self.data_root.iterdir():
                if item_folder.is_dir():
                    item_folder_paths.append(item_folder)

        else:
            raise ValueError(
                f"Unexpected ITEM_FOLDER_LEVEL configuration: '{folder_level}'. "
                f"Expected values: {ITEM_FOLDER_LEVEL_YYYY}, {ITEM_FOLDER_LEVEL_MM}, "
                f"{ITEM_FOLDER_LEVEL_DD}, or {ITEM_FOLDER_LEVEL_NONE}"
            )

        return item_folder_paths

    def run(self) -> None:
        collection = confighelper.load_and_validate_collection(
            self.collection_path,
            self.collection_id,
            save_reordered_collection=False,
            is_compare_expected_id=True,
        )

        collection_config = confighelper.load_config(self.collection_config_path)
        logger.debug(f"collection_config:{collection_config}")

        if ITEM_FOLDER_LEVEL not in collection_config:
            collection_config[ITEM_FOLDER_LEVEL] = ITEM_FOLDER_LEVEL_DD

        item_folder_paths = self._get_item_folders_by_level(collection_config[ITEM_FOLDER_LEVEL])

        self.is_simplified_process = (
            collection_config[ITEM_FOLDER_LEVEL] == ITEM_FOLDER_LEVEL_NONE
        )

        for item_folder_path in item_folder_paths:
            if not self.is_simplified_process:
                self.create_item(item_folder_path, collection, collection_config)
            else:
                self.create_item_simplified_process(item_folder_path, collection, collection_config)

        confighelper.sort_item_assets_in_folder(self.items_root)

        if IS_UPLOAD_S3:
            bucket_name = f"{S3_USER_GENERATED_BUCKET_PREFIX}-{self.collection_id.lower()}"
            if self.overide_bucket_name:
                bucket_name = self.overide_bucket_name
            self.s3tools.upload_folder_to_s3(str(self.collection_root), S3_ENDPOINT_URL, bucket_name)

    def get_item(
        self,
        item_id: str,
        geometry: Optional[Dict[str, Any]],
        bbox: Optional[List[float]],
        item_datetime: datetime,
        item_properties: Dict[str, Any],
        item_folder_path: Path,
        config_list: List[Dict[str, Any]],
        collection: pystac.Collection,
    ) -> None:
        pystac.set_stac_version(STAC_VERSION)

        item = pystac.Item(
            id=item_id,
            geometry=geometry,
            bbox=bbox,
            datetime=item_datetime,
            properties=item_properties,
        )

        asset_paths = [file for file in item_folder_path.rglob("*") if file.is_file()]

        for asset_path in asset_paths:
            asset_href_data_root = Path(*asset_path.parts[1:])
            asset_href = asset_path.relative_to(item_folder_path)
            logger.info(f"asset_href:{asset_href}")

            item_asset_ignore_list = confighelper.get_config_value(
                config_list, "item_asset_ignore_list"
            )
            if asset_href.name not in item_asset_ignore_list:
                media_type = itemhelper.get_media_type(asset_path)
                thumbnail_regex = confighelper.get_config_value(config_list, "thumbnail_regex")
                overview_regex = confighelper.get_config_value(config_list, "overview_regex")

                item.add_asset(
                    key=str(asset_href),
                    asset=pystac.Asset(
                        href=str(asset_href_data_root),
                        media_type=media_type,
                        roles=itemhelper.get_asset_role(
                            media_type, asset_href, thumbnail_regex, overview_regex
                        ),
                    ),
                )

        collection.set_self_href(
            f"https://hda.data.destination-earth.eu/stac/v2/collections/{self.collection_id}"
        )
        item.set_collection(collection)
        item.set_self_href(
            f"https://hda.data.destination-earth.eu/stac/v2/collections/{self.collection_id}/items/{item_id}"
        )

        self.items_root.mkdir(parents=True, exist_ok=True)

        item_path = self.items_root / f"{item.id}.json"
        with open(item_path, "w") as f:
            json.dump(item.to_dict(), f, indent=4)

        logger.info(f"Item metadata saved to {item_path}\n")

    def create_item_simplified_process(self, item_folder_path, collection, collection_config):
        try:
            item_config = confighelper.load_config(
                item_folder_path / ITEM_CONFIG_FILE_NAME, is_config_file_optional=True
            )
            config_list = [item_config, collection_config]

            item_id = item_folder_path.name
            item_folder_path_parts = str(item_folder_path).split(os.path.sep)
            collection_id = item_folder_path_parts[0]

            if not item_id.startswith(collection_id):
                item_id = collection_id + "_" + item_id

            year_from_folder_path = item_folder_path_parts[2]
            item_date_overide = itemhelper.get_item_date_overide(config_list)

            if item_date_overide:
                datetime_from_folder_path = item_date_overide
            elif itemhelper.is_valid_year(year_from_folder_path):
                datetime_from_folder_path = itemhelper.get_datetime_from_folder_path(
                    item_folder_path_parts, collection_config, item_id, collection_id
                )
            else:
                datetime_from_folder_path = datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)

            item_datetime = datetime_from_folder_path
            item_properties = {}
            item_properties.update(confighelper.get_config_value(config_list, "properties", True) or {})
            datetools.is_same_day(datetime_from_folder_path, item_datetime)

            bbox = confighelper.get_config_value(config_list, "bbox", True)
            if bbox:
                polygon = box(*bbox)
                geometry = mapping(polygon)
            else:
                geometry = None

            return self.get_item(
                item_id, geometry, bbox, item_datetime, item_properties,
                item_folder_path, config_list, collection,
            )

        except Exception as e:
            logger.error(f"Error creating item: {e}")
            return None

    def create_item(self, item_folder_path, collection, collection_config):
        try:
            is_item_config_optional = False
            if ITEM_CONFIG_OPTIONAL in collection_config:
                is_item_config_optional = collection_config[ITEM_CONFIG_OPTIONAL]

            item_config = confighelper.load_config(
                item_folder_path / ITEM_CONFIG_FILE_NAME, is_item_config_optional
            )
            config_list = [item_config, collection_config]

            logger.info(f"item_folder_path:{item_folder_path}")

            item_id = item_folder_path.name
            item_folder_path_parts = str(item_folder_path).split(os.path.sep)
            collection_id = item_folder_path_parts[0]

            datetime_from_folder_path = itemhelper.get_datetime_from_folder_path(
                item_folder_path_parts, collection_config, item_id, collection_id
            )

            (item_datetime, item_properties) = itemhelper.get_item_properties(
                item_id,
                collection_id,
                confighelper.get_config_value(config_list, ADDITIONAL_PROPERTY_KEYS, True) or [],
            )
            item_properties.update(confighelper.get_config_value(config_list, "properties", True) or {})
            datetools.is_same_day(datetime_from_folder_path, item_datetime)

            bbox = confighelper.get_config_value(config_list, "bbox", True)
            if bbox:
                polygon = box(*bbox)
                geometry = mapping(polygon)
            else:
                geometry = None

            return self.get_item(
                item_id, geometry, bbox, item_datetime, item_properties,
                item_folder_path, config_list, collection,
            )

        except Exception as e:
            logger.error(f"Error creating item: {e}")
            return None


if __name__ == "__main__":
    logger = logging.getLogger(APP_LOGGER_NAME)
    collection_id = "EO.XXX.YYY.ZZZ"
    item_generator = ItemGenerator(collection_id)
    item_generator.run()
