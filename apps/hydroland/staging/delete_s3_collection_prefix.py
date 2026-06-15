#!/usr/bin/env python3
"""
Delete all objects stored under one collection prefix in the Hydroland S3 bucket.

By default this performs a dry run and only lists how many objects would be
deleted. Pass --execute to actually delete them.
"""

from __future__ import annotations

import argparse
import logging
from typing import Iterable

import boto3
from botocore.client import Config

from stac_dedl_core.config import S3_ENDPOINT_URL
from stac_dedl_core.upload import get_default_bucket_name
from stac_dedl_core.usergenerated.env_utils import validate_aws_credentials


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Delete all S3 objects under a given collection prefix. "
            "Runs in dry-run mode unless --execute is supplied."
        )
    )
    parser.add_argument(
        "collection_id",
        nargs="?",
        default="EO.UFZ.DAT.HYDROLAND",
        help="Collection id used to derive the default bucket and prefix.",
    )
    parser.add_argument(
        "--bucket-name",
        help="Override the destination bucket name.",
    )
    parser.add_argument(
        "--prefix",
        help=(
            "Override the key prefix to delete. "
            "Defaults to '<collection_id>/'"
        ),
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
        help="Logging level (default: INFO).",
    )
    return parser.parse_args()


def setup_logging(level_name: str) -> logging.Logger:
    logging.basicConfig(
        level=getattr(logging, level_name.upper(), logging.INFO),
        format="%(levelname)s | %(message)s",
    )
    return logging.getLogger("hydroland-s3-delete")


def batched(items: list[str], batch_size: int = 1000) -> Iterable[list[str]]:
    for start in range(0, len(items), batch_size):
        yield items[start : start + batch_size]


def main() -> int:
    args = parse_args()
    logger = setup_logging(args.log_level)

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
    object_keys: list[str] = []

    for page in paginator.paginate(Bucket=bucket_name, Prefix=prefix):
        for obj in page.get("Contents", []):
            object_keys.append(obj["Key"])

    logger.info(
        "Matched %s object(s) in bucket '%s' under prefix '%s'.",
        len(object_keys),
        bucket_name,
        prefix,
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


if __name__ == "__main__":
    raise SystemExit(main())
