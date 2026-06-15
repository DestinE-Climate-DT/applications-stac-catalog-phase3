"""Utilities for environment variable validation and management."""

import os
from typing import Tuple
from dotenv import load_dotenv

from stac_dedl_core.config import IS_UPLOAD_S3

load_dotenv()

def validate_aws_credentials() -> Tuple[str, str]:
    """
    Validate and retrieve AWS credentials from environment variables.

    Note: We are using these credentials with Destination Earth Data Lake, Islet Service.
    S3 Object Storage is S3 compatible, so AWS credentials are used for authentication.

    Returns:
        A tuple of (aws_access_key_id, aws_secret_access_key)

    Raises:
        ValueError: If credentials are not set and IS_UPLOAD_S3 is True
    """
    aws_access_key_id = os.getenv("AWS_ACCESS_KEY_ID")
    aws_secret_access_key = os.getenv("AWS_SECRET_ACCESS_KEY")

    if not aws_access_key_id or not aws_secret_access_key:
        if IS_UPLOAD_S3:
            raise ValueError(
                "AWS credentials not set in environment variables. "
                "Please set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY in .env file"
            )
        else:
            print("Warning: Bucket credentials not set, but IS_UPLOAD_S3 is False. Skipping upload mode.")

    return aws_access_key_id, aws_secret_access_key
