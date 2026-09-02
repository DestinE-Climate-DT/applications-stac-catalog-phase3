import argparse
import logging
import os
import json
import pystac
from datetime import datetime
from pathlib import Path
from shapely.geometry import box, mapping
from typing import Callable, List, Dict, Any, Optional


from stac_dedl_core.config import (
    APP_LOGGER_NAME,
    COLLECTION_BUCKET_OVERRIDES,
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

from stac_dedl_core.usergenerated import datetools
from stac_dedl_core.usergenerated.config import confighelper
from stac_dedl_core.usergenerated.item import itemhelper
from stac_dedl_core.usergenerated.s3tools import S3Tools
from stac_dedl_core.usergenerated.env_utils import validate_aws_credentials

logger = logging.getLogger(__name__)


# Bucket overrides live in config.py so upload.py and this module cannot drift.
DEFAULT_BUCKET_OVERRIDES = COLLECTION_BUCKET_OVERRIDES


def get_default_bucket_name(collection_id: str) -> str:
    return DEFAULT_BUCKET_OVERRIDES.get(
        collection_id, f"{S3_USER_GENERATED_BUCKET_PREFIX}-{collection_id.lower()}"
    )


class ItemGenerator:

    def __init__(
        self,
        collection_id: str,
        overide_bucket_name: Optional[str] = None,
        is_upload_s3: Optional[bool] = None,
        is_overwrite_s3: Optional[bool] = None,
        is_validate_stac_schema: bool = True,
        upload_file_years: Optional[List[str]] = None,
        is_skip_metadata_upload: bool = False,
        is_upload_only: bool = False,
        is_clean_items_dir: bool = False,
    ) -> None:
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
        # instance collection_id
        self.collection_id = collection_id

        if "-" in collection_id:
            raise ValueError(
                "collection_id cannot contain a dash ('-'). Only underscores ('_') are permitted in a dedl Collection ID."
            )

        self.overide_bucket_name = overide_bucket_name
        self.is_upload_s3 = IS_UPLOAD_S3 if is_upload_s3 is None else is_upload_s3
        self.is_validate_stac_schema = is_validate_stac_schema
        self.upload_file_years = upload_file_years or []
        self.is_skip_metadata_upload = is_skip_metadata_upload
        self.is_upload_only = is_upload_only
        self.is_clean_items_dir = is_clean_items_dir

        # Path to root of all collection related data: used when uploading to S3 bucket
        self.collection_root = Path(collection_id)

        # Path to collection.json STAC file
        self.collection_path = Path(f"{collection_id}/metadata/collection.json")
        # Path to collection level config file, containing global config when generating Item metadata
        self.collection_config_path = Path(
            f"{collection_id}/metadata/collection_config.json"
        )
        # Path to expected folder where STAC Item (feature) metadata will be generated
        self.items_root = Path(f"{collection_id}/metadata/items")
        # Path to expected data folder which is used to generate the Item metadata
        self.data_root = Path(f"{collection_id}/data")

        ##### Initialise S3Tools object to handle S3 interaction #####

        self.is_overwrite_s3 = (
            IS_OVERWRITE_S3 if is_overwrite_s3 is None else is_overwrite_s3
        )
        self.aws_access_key_id, self.aws_secret_access_key = validate_aws_credentials()
        if self.is_upload_s3 and (
            not self.aws_access_key_id or not self.aws_secret_access_key
        ):
            raise ValueError(
                "AWS credentials not set. Put AWS_ACCESS_KEY_ID and "
                "AWS_SECRET_ACCESS_KEY in .env or export them before using --upload."
            )

        self.s3tools = S3Tools(
            self.aws_access_key_id, self.aws_secret_access_key, self.is_overwrite_s3
        )

    def _get_item_folders_by_level(
        self, folder_level: str
    ) -> List[Path]:
        """
        Retrieve item folder paths based on the specified folder level configuration.
        
        Args:
            folder_level: The folder level configuration (YYYY, MM, DD, or NONE)
            
        Returns:
            List of Path objects pointing to item folders
            
        Raises:
            ValueError: If an unexpected folder level configuration is provided
        """
        item_folder_paths: List[Path] = []

        if folder_level == ITEM_FOLDER_LEVEL_DD:
            # Navigate: data/YYYY/MM/DD/items
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
            # Navigate: data/YYYY/MM/items
            for year_folder in self.data_root.iterdir():
                if year_folder.is_dir():
                    for month_folder in year_folder.iterdir():
                        if month_folder.is_dir():
                            for item_folder in month_folder.iterdir():
                                if item_folder.is_dir():
                                    item_folder_paths.append(item_folder)

        elif folder_level == ITEM_FOLDER_LEVEL_YYYY:
            # Navigate: data/YYYY/items
            for year_folder in self.data_root.iterdir():
                if year_folder.is_dir():
                    for item_folder in year_folder.iterdir():
                        if item_folder.is_dir():
                            item_folder_paths.append(item_folder)

        elif folder_level == ITEM_FOLDER_LEVEL_NONE:
            # Any folders at the root of data become items (simplified process)
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

    def _build_upload_filter(self) -> Optional[Callable[[Path], bool]]:
        if not self.upload_file_years and not self.is_skip_metadata_upload:
            return None

        year_prefixes = tuple(f"{year}_" for year in self.upload_file_years)

        def include_file(file_path: Path) -> bool:
            path_parts = file_path.parts
            if "metadata" in path_parts:
                return not self.is_skip_metadata_upload
            if "data" not in path_parts:
                return False if year_prefixes else True
            if not year_prefixes:
                return True
            return file_path.name.startswith(year_prefixes)

        return include_file

    def _upload_collection(self) -> None:
        if not self.is_upload_s3:
            raise ValueError("Upload requested without upload mode enabled.")

        # Hydroland uses the legacy bucket from the original IFS-NEMO collection id.
        bucket_name = get_default_bucket_name(self.collection_id)

        # An optional overide_bucket_name can be provided to upload the generated metadata to S3 (Case-sensitive)
        # Only needed if the bucket_name you have been provided with does not follow the naming convention
        if self.overide_bucket_name:
            bucket_name = self.overide_bucket_name

        # Upload whole folder, or a filtered subset if requested.
        upload_stats = self.s3tools.upload_folder_to_s3(
            str(self.collection_root),
            S3_ENDPOINT_URL,
            bucket_name,
            include_file=self._build_upload_filter(),
        )
        summary_lines = [
            "Upload summary:",
            f"- bucket: {bucket_name}",
            f"- selected files: {upload_stats['selected']}",
            f"- uploaded: {upload_stats['uploaded']}",
            f"- skipped existing: {upload_stats['skipped_existing']}",
            f"- failed: {upload_stats['failed']}",
        ]

        if self.upload_file_years:
            summary_lines.insert(
                2, f"- upload file years: {', '.join(self.upload_file_years)}"
            )

        print("\n".join(summary_lines))

    def _clean_items_metadata(self) -> int:
        removed = 0
        if not self.items_root.exists():
            return removed

        for item_file in self.items_root.glob("*.json"):
            item_file.unlink()
            removed += 1

        print(f"Removed {removed} existing item metadata files from {self.items_root}")
        return removed

    def run(self) -> None:
        """
        Main entry point to generate STAC Item metadata for the collection.
        """
        if self.is_upload_only:
            self._upload_collection()
            return

        if self.is_clean_items_dir:
            self._clean_items_metadata()

        ##### Load and Validate the Collection #####
        collection = confighelper.load_and_validate_collection(
            self.collection_path,
            self.collection_id,
            save_reordered_collection=False,
            is_compare_expected_id=True,
            is_validate_stac_schema=self.is_validate_stac_schema,
        )

        ###### load the collection config #####
        collection_config = confighelper.load_config(self.collection_config_path)
        logger.debug(f"collection_config:{collection_config}")

        # ITEM Folders are expected by default to be in a folder representing a day DD
        if ITEM_FOLDER_LEVEL not in collection_config:
            collection_config[ITEM_FOLDER_LEVEL] = ITEM_FOLDER_LEVEL_DD

        # Get list of item folder paths based on the configured level
        item_folder_paths = self._get_item_folders_by_level(
            collection_config[ITEM_FOLDER_LEVEL]
        )

        self.is_simplified_process = (
            collection_config[ITEM_FOLDER_LEVEL] == ITEM_FOLDER_LEVEL_NONE
        )

        # Iterate over Item folders to create Item files
        for item_folder_path in item_folder_paths:

            if not self.is_simplified_process:
                self.create_item(item_folder_path, collection, collection_config)
            else:
                self.create_item_simplified_process(
                    item_folder_path, collection, collection_config
                )

        # Assure that item assets are always ordered consistently
        confighelper.sort_item_assets_in_folder(self.items_root)

        if self.is_upload_s3:
            self._upload_collection()

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
        """
        Create and save a STAC Item with assets to disk.

        Args:
            item_id: Unique identifier for the item
            geometry: GeoJSON geometry object for the item
            bbox: Bounding box as [minx, miny, maxx, maxy]
            item_datetime: Datetime associated with the item
            item_properties: Additional properties for the item
            item_folder_path: Path to the folder containing item data files
            config_list: List of configuration dictionaries
            collection: The parent STAC Collection object
        """

        pystac.set_stac_version(STAC_VERSION)

        # Create the STAC item
        item = pystac.Item(
            id=item_id,
            geometry=geometry,
            bbox=bbox,
            datetime=item_datetime,
            properties=item_properties,
        )

        ####################

        # Gather all file paths in the item folder and subfolders
        asset_paths = [file for file in item_folder_path.rglob("*") if file.is_file()]

        # Process each file and add as an asset to the item
        for asset_path in asset_paths:

            asset_href_data_root = Path(*asset_path.parts[1:])

            # Compute the relative href
            asset_href = asset_path.relative_to(item_folder_path)
            logger.info(f"asset_href:{asset_href}")

            # Skip files listed in the ignore list from the configuration
            item_asset_ignore_list = confighelper.get_config_value(
                config_list, "item_asset_ignore_list"
            )
            if asset_href.name not in item_asset_ignore_list:
                # Determine the MIME type of the asset
                media_type = itemhelper.get_media_type(asset_path)

                # Get regex patterns for thumbnails and overviews
                thumbnail_regex = confighelper.get_config_value(
                    config_list, "thumbnail_regex"
                )
                overview_regex = confighelper.get_config_value(
                    config_list, "overview_regex"
                )

                # Add the asset to the item
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

        # Set collection and item self links
        collection.set_self_href(
            f"https://hda.data.destination-earth.eu/stac/v2/collections/{self.collection_id}"
        )
        item.set_collection(collection)
        item.set_self_href(
            f"https://hda.data.destination-earth.eu/stac/v2/collections/{self.collection_id}/items/{item_id}"
        )

        # Ensure the items_root directory exists
        self.items_root.mkdir(parents=True, exist_ok=True)

        # Save the item metadata to a JSON file
        item_path = self.items_root / f"{item.id}.json"
        with open(item_path, "w") as f:
            json.dump(item.to_dict(), f, indent=4)

        logger.info(f"Item metadata saved to {item_path}\n")

    def create_item_simplified_process(
        self,
        item_folder_path: Path,
        collection: pystac.Collection,
        collection_config: dict,
    ):
        """
        Function to create an item for each data file, using a 'simplified' process
        That is to say we only use the name of folders at root of 'data' folder as items.
        Naming conventions on item folders are ignored.
        No start datetime or end datetime can be retrieved from folder name
        No addtional parameters can be retrieved from the folder name
        Dates from naming of folders is possible still but taken from YYYY/01/01 if root folder is in form YYYY.
        Dates can be overiden with new config 'item_date_overide'

        Parameters:
        item_folder_path (Path): Path to the folder containing the item data files.
        collection (pystac.Collection): The STAC collection to which the item belongs.
        collection_config (dict): Configuration dictionary for the collection.

        Returns:
        pystac.Item: The created STAC item.
        """

        try:

            ###################################################################
            ###### Simplified Process: The Item Config File is optional   #####
            ###################################################################

            # Load item-specific configuration from a file in the item folder
            item_config = confighelper.load_config(
                item_folder_path / ITEM_CONFIG_FILE_NAME,
                is_config_file_optional=True,
            )
            logger.debug(item_config)

            # Combine item and collection configuration, with item-specific values overriding collection values
            config_list = [item_config, collection_config]

            ###################################################################
            ###### Initialize item_id and collection_id from folder names #####
            ###################################################################

            # Extract item ID and date components from the folder path
            item_id = item_folder_path.name
            item_folder_path_parts = str(item_folder_path).split(os.path.sep)
            collection_id = item_folder_path_parts[0]

            # Simplified Process: Prefix with real collection id if folder name does not start with it.
            if not item_id.startswith(collection_id):
                item_id = collection_id + "_" + item_id

            ###################################################################
            ###### Simplified Process: Initialise datetime_from_folder_path #####
            ###################################################################

            # Simplified Process: The root folder can represent a year OR not
            year_from_folder_path = item_folder_path_parts[2]

            # Simplified Process: The item datetime can be overiden through configuration
            item_date_overide = itemhelper.get_item_date_overide(config_list)
            if item_date_overide:
                datetime_from_folder_path = item_date_overide

            # Simplified Process: If root folder (in data folder) is a valid year we can use it to set datetime as usual
            elif itemhelper.is_valid_year(year_from_folder_path):

                datetime_from_folder_path = itemhelper.get_datetime_from_folder_path(
                    item_folder_path_parts, collection_config, item_id, collection_id
                )

            else:

                # Just use today at midnight
                datetime_from_folder_path = datetime.today().replace(
                    hour=0, minute=0, second=0, microsecond=0
                )

            ###################################################################
            ###### Simplified Process: item_datetime item_properties        #####
            ###################################################################

            # Get datetime object and date related properties from the item ID
            # (item_datetime, item_properties) = itemhelper.get_item_properties(
            #     item_id,
            #     collection_id,
            #     confighelper.get_config_value(config_list, ADDITIONAL_PROPERTY_KEYS, True)
            #     or [],
            # )

            # Simplified process for a Year folder (Simplified Process)
            item_datetime = datetime_from_folder_path
            item_properties = {}

            # Update item_properties with additional properties if they exist
            item_properties.update(
                confighelper.get_config_value(config_list, "properties", True) or {}
            )

            # Ensure the folder date matches the item ID date : Sanity Check
            datetools.is_same_day(datetime_from_folder_path, item_datetime)

            ###################################################################
            ###### Initialise bbox                                        #####
            ###################################################################

            # Retrieve bounding box from the configuration : Normally Item Specific i.e. in item_config.json
            bbox = confighelper.get_config_value(config_list, "bbox", True)

            # Create a polygon from the bounding box and convert to GeoJSON
            if bbox:
                polygon = box(*bbox)
                geometry = mapping(polygon)
            else:
                geometry = None

            ###################################################################
            ###### common get_item process : normal and Simplified process  #####
            ###################################################################

            item = self.get_item(
                item_id,
                geometry,
                bbox,
                item_datetime,
                item_properties,
                item_folder_path,
                config_list,
                collection,
            )

            return item

        except Exception as e:
            logger.error(f"Error creating item: {e}")
            return None

    def create_item(
        self,
        item_folder_path: Path,
        collection: pystac.Collection,
        collection_config: dict,
    ):
        """
        Function to create an item for each data file

        Parameters:
        item_folder_path (Path): Path to the folder containing the item data files.
        collection (pystac.Collection): The STAC collection to which the item belongs.
        collection_config (dict): Configuration dictionary for the collection.

        Returns:
        pystac.Item: The created STAC item.
        """
        try:

            ###################################################################
            ###### Initialise item_config (obligatory) and config_list    #####
            ###################################################################
            #
            # Load item-specific configuration from a file in the item folder

            # Item_Config is mandatory by default
            is_item_config_optional = False
            if ITEM_CONFIG_OPTIONAL in collection_config:
                is_item_config_optional = collection_config[ITEM_CONFIG_OPTIONAL]
                print(f"{ITEM_CONFIG_OPTIONAL}:{is_item_config_optional}")

            item_config = confighelper.load_config(
                item_folder_path / ITEM_CONFIG_FILE_NAME, is_item_config_optional
            )
            logger.debug(item_config)

            # Combine item and collection configuration, with item-specific values overriding collection values
            config_list = [item_config, collection_config]

            ###################################################################
            ###### Initialize item_id and collection_id from folder names #####
            ###################################################################

            logger.info(f"item_folder_path:{item_folder_path}")

            # Extract item ID and date components from the folder path
            item_id = item_folder_path.name
            item_folder_path_parts = str(item_folder_path).split(os.path.sep)
            collection_id = item_folder_path_parts[0]

            ###################################################################
            ###### Initialise datetime_from_folder_path                   #####
            ###################################################################

            datetime_from_folder_path = itemhelper.get_datetime_from_folder_path(
                item_folder_path_parts, collection_config, item_id, collection_id
            )

            ###################################################################
            ###### item_datetime item_properties                          #####
            ###################################################################

            # Get datetime object and date related properties from the item ID
            (item_datetime, item_properties) = itemhelper.get_item_properties(
                item_id,
                collection_id,
                confighelper.get_config_value(
                    config_list, ADDITIONAL_PROPERTY_KEYS, True
                )
                or [],
            )

            # Update item_properties with additional properties if they exist
            item_properties.update(
                confighelper.get_config_value(config_list, "properties", True) or {}
            )

            # Ensure the folder date matches the item ID date : Sanity Check
            datetools.is_same_day(datetime_from_folder_path, item_datetime)

            ###################################################################
            ###### Initialise bbox                                        #####
            ###################################################################

            # Retrieve bounding box from the configuration : Normally Item Specific i.e. in item_config.json
            bbox = confighelper.get_config_value(config_list, "bbox", True)

            # Create a polygon from the bounding box and convert to GeoJSON
            if bbox:
                polygon = box(*bbox)
                geometry = mapping(polygon)
            else:
                geometry = None

            ###################################################################
            ###### common get_item process : normal and Simplified process  #####
            ###################################################################

            item = self.get_item(
                item_id,
                geometry,
                bbox,
                item_datetime,
                item_properties,
                item_folder_path,
                config_list,
                collection,
            )

            return item

        except Exception as e:
            logger.error(f"Error creating item: {e}")
            return None


#################### START ####################

if __name__ == "__main__":

    # Get App Logger
    logger = logging.getLogger(APP_LOGGER_NAME)

    parser = argparse.ArgumentParser(
        description=(
            "Generate STAC Item metadata for a prepared collection folder and "
            "optionally upload the collection folder to S3."
        )
    )
    parser.add_argument(
        "collection_id",
        nargs="?",
        default="EO.UFZ.DAT.HYDROLAND",
        help="Collection folder/id to process (default: EO.UFZ.DAT.HYDROLAND).",
    )
    parser.add_argument(
        "--bucket-name",
        help=(
            "Override the destination bucket. Defaults to "
            "usergenerated-proposal-<lowercase collection_id>."
        ),
    )
    parser.add_argument(
        "--upload",
        action="store_true",
        help="Upload the collection folder to S3 after generating item metadata.",
    )
    parser.add_argument(
        "--overwrite-s3",
        action="store_true",
        help="Overwrite existing objects in S3 instead of skipping them.",
    )
    parser.add_argument(
        "--upload-file-year",
        action="append",
        metavar="YYYY",
        help=(
            "When uploading, only upload data files whose filename starts "
            "with this year and an underscore. Can be repeated."
        ),
    )
    parser.add_argument(
        "--skip-metadata-upload",
        action="store_true",
        help="When uploading a filtered data slice, do not upload metadata files again.",
    )
    parser.add_argument(
        "--upload-only",
        action="store_true",
        help="Skip metadata generation and only upload files selected by the upload filters.",
    )
    parser.add_argument(
        "--clean-items-dir",
        action="store_true",
        help="Remove existing metadata/items/*.json before regenerating item metadata.",
    )
    parser.add_argument(
        "--skip-stac-schema-validation",
        action="store_true",
        help=(
            "Skip remote PySTAC JSON-schema validation. Useful on systems "
            "without internet access; local collection checks still run."
        ),
    )
    args = parser.parse_args()

    # Initialise ItemGenerator to create Item (Feature) metadata associated with the Collection and Data
    # Note: a second argument can be provided to overide the bucket name (only necessary if it does not follow the case-sensitive naming convention) 'usergenerated-proposal-[collection_id]'
    item_generator = ItemGenerator(
        args.collection_id,
        args.bucket_name,
        is_upload_s3=args.upload,
        is_overwrite_s3=args.overwrite_s3,
        is_validate_stac_schema=not args.skip_stac_schema_validation,
        upload_file_years=args.upload_file_year,
        is_skip_metadata_upload=args.skip_metadata_upload,
        is_upload_only=args.upload_only,
        is_clean_items_dir=args.clean_items_dir,
    )
    item_generator.run()
