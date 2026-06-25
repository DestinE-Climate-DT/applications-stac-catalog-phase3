"""Shared upload of a staged collection tree to the DEDL S3 bucket.

Dry run by default; uploads metadata/ first, then data/ in year/month order
so an interrupted transfer can resume with --year.

Usage:
    python -m stac_dedl_core.upload EO.UFZ.DAT.HYDROLAND \
        --root /path/to/EO.UFZ.DAT.HYDROLAND [--year 2015] [--execute]
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Iterator, Tuple

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from dotenv import load_dotenv

from stac_dedl_core.config import S3_ENDPOINT_URL, S3_USER_GENERATED_BUCKET_PREFIX

logger = logging.getLogger(__name__)


def get_default_bucket_name(collection_id: str) -> str:
    return f"{S3_USER_GENERATED_BUCKET_PREFIX}-{collection_id.lower()}"


def iter_upload_pairs(
    collection_root: Path,
    collection_id: str,
    year: str | None = None,
) -> Iterator[Tuple[Path, str]]:
    """Yield (file_path, object_key): metadata/ first, then data/ by year/month.

    Object keys are prefixed with collection_id so they land in the right
    top-level prefix inside the bucket.
    """

    def key_for(p: Path) -> str:
        return f"{collection_id}/{p.relative_to(collection_root).as_posix()}"

    # metadata/ always goes first
    metadata_dir = collection_root / "metadata"
    if metadata_dir.is_dir():
        for f in sorted(metadata_dir.rglob("*")):
            if f.is_file():
                yield f, key_for(f)

    # data/ in sorted year/month order so --year can resume cleanly
    data_dir = collection_root / "data"
    if data_dir.is_dir():
        for year_dir in sorted(d for d in data_dir.iterdir() if d.is_dir()):
            if year and year_dir.name != year:
                continue
            for f in sorted(year_dir.rglob("*")):
                if f.is_file():
                    yield f, key_for(f)


def _make_s3_client(dotenv_path: Path | None = None):
    load_dotenv(dotenv_path)
    aws_access_key_id = os.getenv("AWS_ACCESS_KEY_ID")
    aws_secret_access_key = os.getenv("AWS_SECRET_ACCESS_KEY")
    if not aws_access_key_id or not aws_secret_access_key:
        raise ValueError(
            "AWS credentials missing — set AWS_ACCESS_KEY_ID and "
            "AWS_SECRET_ACCESS_KEY in the app's .env file."
        )
    return boto3.client(
        "s3",
        endpoint_url=S3_ENDPOINT_URL,
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        config=Config(signature_version="s3v4"),
    )


def upload_collection(
    collection_id: str,
    root: Path,
    bucket: str | None = None,
    year: str | None = None,
    overwrite: bool = False,
    execute: bool = False,
    s3_client=None,
) -> dict:
    """Upload a staged collection tree to S3. Dry run unless execute=True."""
    root = Path(root).expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Collection root not found: {root}")

    bucket_name = bucket or get_default_bucket_name(collection_id)
    pairs = list(iter_upload_pairs(root, collection_id, year=year))

    if not pairs:
        logger.warning(
            "--year %s matched no files; check the year or the directory structure.",
            year,
        )

    stats = {"matched": len(pairs), "uploaded": 0, "skipped_existing": 0, "failed": 0}

    if not execute:
        for file_path, object_key in pairs:
            logger.info("[DRY RUN] %s -> s3://%s/%s", file_path, bucket_name, object_key)
        logger.info(
            "[DRY RUN] %s file(s) would be uploaded to bucket '%s'. "
            "Re-run with --execute to upload.",
            stats["matched"],
            bucket_name,
        )
        return stats

    s3 = s3_client if s3_client is not None else _make_s3_client()
    for file_path, object_key in pairs:
        if not overwrite:
            try:
                s3.head_object(Bucket=bucket_name, Key=object_key)
                logger.info("Exists, skipping: %s", object_key)
                stats["skipped_existing"] += 1
                continue
            except ClientError as e:
                if e.response["Error"]["Code"] != "404":
                    raise

        try:
            s3.upload_file(str(file_path), bucket_name, object_key)
            logger.info("Uploaded: s3://%s/%s", bucket_name, object_key)
            stats["uploaded"] += 1
        except Exception as e:
            logger.error("Failed uploading %s: %s", object_key, e)
            stats["failed"] += 1

    if stats["failed"]:
        logger.error(
            "Upload finished with errors. failed=%s uploaded=%s skipped_existing=%s",
            stats["failed"], stats["uploaded"], stats["skipped_existing"],
        )
    else:
        logger.info(
            "Done. matched=%s uploaded=%s skipped_existing=%s",
            stats["matched"], stats["uploaded"], stats["skipped_existing"],
        )

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m stac_dedl_core.upload",
        description="Upload a staged STAC collection tree to the DEDL S3 bucket.",
    )
    parser.add_argument("collection_id", help="e.g. EO.UFZ.DAT.HYDROLAND")
    parser.add_argument(
        "--root",
        help="Collection root directory (default: ./<collection_id>)",
    )
    parser.add_argument("--bucket", help="Override the destination bucket name.")
    parser.add_argument(
        "--year",
        help="Only upload data/<year>/ (metadata always included).",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Re-upload objects that already exist in the bucket.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually upload. Without this flag, dry run only.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

    root = Path(args.root) if args.root else Path(args.collection_id)
    stats = upload_collection(
        args.collection_id,
        root=root,
        bucket=args.bucket,
        year=args.year,
        overwrite=args.overwrite,
        execute=args.execute,
    )
    if stats.get("failed"):
        sys.exit(1)


if __name__ == "__main__":
    main()
