import logging
import boto3
from botocore.client import Config
from botocore.exceptions import NoCredentialsError, ClientError
from pathlib import Path
from typing import Optional

from stac_dedl_core.config import APP_LOGGER_NAME, IS_UPLOAD_S3

logger = logging.getLogger(APP_LOGGER_NAME)


class S3Tools:
    """Utility class for interacting with S3-compatible object storage (DEDL Islet Service).

    For collection-tree uploads prefer stac_dedl_core.upload.upload_collection
    (CLI: python -m stac_dedl_core.upload); this class remains for compatibility.
    """

    def __init__(self, aws_access_key_id: str, aws_secret_access_key: str, is_overwrite_s3: bool = True) -> None:
        self.aws_access_key_id = aws_access_key_id
        self.aws_secret_access_key = aws_secret_access_key

        if not self.aws_access_key_id or not self.aws_secret_access_key:
            if IS_UPLOAD_S3:
                raise ValueError("Bucket Credentials not set")
            else:
                logger.warning("Bucket credentials not set, but IS_UPLOAD_S3 is False. Skipping upload mode.")

        self.is_overwrite_s3 = is_overwrite_s3

    def upload_file_to_s3(self, file_name: str, endpoint_url: str, bucket_name: str, object_name: Optional[str] = None) -> bool:
        if object_name is None:
            object_name = file_name

        s3_client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=self.aws_access_key_id,
            aws_secret_access_key=self.aws_secret_access_key,
            config=Config(signature_version="s3v4"),
        )

        if not self.is_overwrite_s3:
            try:
                s3_client.head_object(Bucket=bucket_name, Key=object_name)
                logger.warning(f"File '{object_name}' already exists in bucket '{bucket_name}'.")
                return False
            except ClientError as e:
                if e.response["Error"]["Code"] != "404":
                    logger.error(f"An error occurred: {e}")
                    return False

        try:
            s3_client.upload_file(file_name, bucket_name, object_name)
            logger.info(f"File '{file_name}' uploaded to bucket '{bucket_name}' as '{object_name}'.")
        except FileNotFoundError:
            logger.error(f"The file '{file_name}' was not found.")
            return False
        except NoCredentialsError:
            logger.error("Credentials not available.")
            return False

        return True

    def upload_folder_to_s3(self, folder_path: str, endpoint_url: str, bucket_name: str) -> None:
        s3_client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=self.aws_access_key_id,
            aws_secret_access_key=self.aws_secret_access_key,
            config=Config(signature_version="s3v4"),
        )

        folder_path: Path = Path(folder_path)
        for file_path in folder_path.rglob("*"):
            if file_path.is_file():
                object_name_string: str = str(file_path)

                if not self.is_overwrite_s3:
                    try:
                        s3_client.head_object(Bucket=bucket_name, Key=object_name_string)
                        logger.info(f"File '{object_name_string}' already exists. Skipping.")
                        continue
                    except ClientError as e:
                        if e.response["Error"]["Code"] != "404":
                            logger.error(f"An error occurred: {e}")
                            continue

                try:
                    s3_client.upload_file(str(file_path), bucket_name, object_name_string)
                    logger.info(f"File '{file_path}' uploaded to bucket '{bucket_name}'.")
                except FileNotFoundError:
                    logger.error(f"The file '{file_path}' was not found.")
                except NoCredentialsError:
                    logger.error("Credentials not available.")
                except ClientError as e:
                    logger.error(f"An error occurred: {e}")
