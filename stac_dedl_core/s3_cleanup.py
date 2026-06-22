"""Shared logic to delete all S3 objects under one collection prefix.

Used by every app's `staging/delete_s3_collection_prefix.py` (a thin wrapper
passing that app's collection id as the default). Dry run by default; pass
--execute to actually delete.
"""
from __future__ import annotations

import argparse
from typing import Iterable

import boto3
from botocore.client import Config

from stac_dedl_core.config import S3_ENDPOINT_URL
from stac_dedl_core.staging import setup_logging
from stac_dedl_core.upload import get_default_bucket_name
from stac_dedl_core.usergenerated.env_utils import validate_aws_credentials


def batched(items: list[str], batch_size: int = 1000) -> Iterable[list[str]]:
    for start in range(0, len(items), batch_size):
        yield items[start : start + batch_size]


def run_cli(default_collection_id: str) -> int:
    """Entry point for an app's `staging/delete_s3_collection_prefix.py` wrapper."""
    parser = argparse.ArgumentParser(
        description=(
            "Delete all S3 objects under a given collection prefix. "
            "Runs in dry-run mode unless --execute is supplied."
        )
    )
    parser.add_argument(
        "collection_id",
        nargs="?",
        default=default_collection_id,
        help="Collection id used to derive the default bucket and prefix.",
    )
    parser.add_argument("--bucket-name", help="Override the destination bucket name.")
    parser.add_argument(
        "--prefix",
        help="Override the key prefix to delete. Defaults to '<collection_id>/'",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually delete objects. Without this flag the script only reports matches.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"],
    )
    args = parser.parse_args()
    logger = setup_logging(f"{args.collection_id}-s3-delete", args.log_level)

    aws_access_key_id, aws_secret_access_key = validate_aws_credentials()
    bucket_name = args.bucket_name or get_default_bucket_name(args.collection_id)
    prefix = args.prefix or f"{args.collection_id}/"

    s3_client = boto3.client(
        "s3",
        endpoint_url=S3_ENDPOINT_URL,
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        config=Config(signature_version="s3v4"),
    )

    paginator = s3_client.get_paginator("list_objects_v2")
    object_keys = [
        obj["Key"]
        for page in paginator.paginate(Bucket=bucket_name, Prefix=prefix)
        for obj in page.get("Contents", [])
    ]

    logger.info(
        "Matched %s object(s) in bucket '%s' under prefix '%s'.",
        len(object_keys), bucket_name, prefix,
    )
    if not object_keys:
        return 0

    if not args.execute:
        logger.info("Dry run only. Re-run with --execute to delete these objects.")
        return 0

    deleted = 0
    for batch in batched(object_keys):
        response = s3_client.delete_objects(
            Bucket=bucket_name,
            Delete={"Objects": [{"Key": key} for key in batch]},
        )
        deleted += len(response.get("Deleted", []))
        for err in response.get("Errors", []):
            logger.error("Failed deleting %s: %s", err.get("Key"), err.get("Message"))

    logger.info("Deleted %s object(s) from '%s' under '%s'.", deleted, bucket_name, prefix)
    return 0
