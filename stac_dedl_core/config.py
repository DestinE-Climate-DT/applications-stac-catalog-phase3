import os
import logging
from enum import Enum

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

APP_LOGGER_NAME: str = "app_logger"
APP_LOGGER_FILE_PATH: str = "usergenerated.log"
APP_LOGGER_FILE_TRUNCATE_SIZE: int = 10 * 1024 * 1024
APP_LOGGER_FILE_BACKUP_COUNT: int = 5
APP_LOGGER_LEVEL: int = logging.INFO

# HDA uses stac version 1.0.0
STAC_VERSION: str = "1.0.0"

ITEM_CONFIG_FILE_NAME: str = "item_config.json"
ITEM_CONFIG_OPTIONAL: str = "item_config_optional"

ITEM_FOLDER_LEVEL: str = "item_folder_level"
ITEM_FOLDER_LEVEL_YYYY: str = "YYYY"
ITEM_FOLDER_LEVEL_MM: str = "MM"
ITEM_FOLDER_LEVEL_DD: str = "DD"
ITEM_FOLDER_LEVEL_NONE: str = "NONE"

ADDITIONAL_PROPERTY_KEYS: str = "additional_property_keys"

IS_UPLOAD_S3: bool = False
IS_OVERWRITE_S3: bool = False
S3_ENDPOINT_URL: str = "https://s3.central.data.destination-earth.eu"
S3_USER_GENERATED_BUCKET_PREFIX: str = "usergenerated-proposal"


class ItemFolderNamingConventionType(str, Enum):
    STANDARD = "standard"
    NON_STANDARD_1 = "non_standard_1"

ITEM_FOLDER_NAMING_CONVENTION_TYPE = ItemFolderNamingConventionType.STANDARD
