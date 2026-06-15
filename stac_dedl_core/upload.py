"""Shared upload of a staged collection tree to the DEDL S3 bucket.

Replaces the per-app s3cmd scripts and the IS_UPLOAD_S3 config toggle.
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

from stac_dedl_core.config import (
    S3_ENDPOINT_URL,
    S3_USER_GENERATED_BUCKET_PREFIX,
)

logger = logging.getLogger("stac-dedl-upload")


def get_default_bucket_name(collection_id: str) -> str:
    return f"{S3_USER_GENERATED_BUCKET_PREFIX}-{collection_id.lower()}"


def iter_upload_pairs(
    collection_root: Path, collection_id: str, year: str | None = None
) -> Iterator[Tuple[Path, str]]:
    """Yield (file_path, object_key): metadata/ first, then data/ by year/month."""

    def key_for(fp: Path) -> str:
        return f"{collection_id}/{fp.relative_to(collection_root).as_posix()}"

    metadata_dir = collection_root / "metadata"
    if metadata_dir.is_dir():
        for fp in sorted(p for p in metadata_dir.rglob("*") if p.is_file()):
            yield fp, key_for(fp)

    data_dir = collection_root / "data"
    if data_dir.is_dir():
        for year_dir in sorted(p for p in data_dir.iterdir() if p.is_dir()):
            if year is not None and year_dir.name != str(year):
                continue
            for fp in sorted(p for p in year_dir.rglob("*") if p.is_file()):
                yield fp, key_for(fp)


def _make_s3_client():
    load_dotenv()
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
    collection_root: str | Path,
    bucket_name: str | None = None,
    year: str | None = None,
    overwrite: bool = False,
    execute: bool = False,
    s3_client=None,
) -> dict:
    collection_root = Path(collection_root).expanduser().resolve()
    if not collection_root.is_dir():
        raise FileNotFoundError(f"Collection root not found: {collection_root}")

    bucket = bucket_name or get_default_bucket_name(collection_id)
    pairs = list(iter_upload_pairs(collection_root, collection_id, year=year))
    stats = {"matched": len(pairs), "uploaded": 0, "skipped_existing": 0, "failed": 0}

    if year is not None and not any(f"{collection_id}/data/" in key for _, key in pairs):
        logger.warning(
            "--year %s matched no data files; check the year or the directory structure.",
            year,
        )

    if not execute:
        for fp, key in pairs[:5]:
            logger.info("[DRY RUN] %s -> s3://%s/%s", fp, bucket, key)
        logger.info(
            "[DRY RUN] %s file(s) would be uploaded to bucket '%s'. "
            "Re-run with --execute to upload.",
            len(pairs),
            bucket,
        )
        return stats

    if s3_client is None:
        s3_client = _make_s3_client()

    for fp, key in pairs:
        if not overwrite:
            try:
                s3_client.head_object(Bucket=bucket, Key=key)
                stats["skipped_existing"] += 1
                logger.info("Exists, skipping: %s", key)
                continue
            except ClientError as e:
                if e.response["Error"]["Code"] != "404":
                    raise
        try:
            s3_client.upload_file(str(fp), bucket, key)
        except (ClientError, OSError) as e:
            stats["failed"] += 1
            logger.error("Failed uploading %s: %s", key, e)
            continue
        stats["uploaded"] += 1
        logger.info("Uploaded: s3://%s/%s", bucket, key)

    if stats["failed"]:
        logger.error(
            "Upload finished with errors. failed=%s uploaded=%s skipped_existing=%s",
            stats["failed"],
            stats["uploaded"],
            stats["skipped_existing"],
        )
    else:
        logger.info(
            "Done. matched=%s uploaded=%s skipped_existing=%s",
            stats["matched"],
            stats["uploaded"],
            stats["skipped_existing"],
        )
    return stats


def main(argv: list[str] | None = None) -> int:
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
    parser.add_argument("--year", help="Only upload data/<year>/ (metadata always included).")
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
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
    root = Path(args.root) if args.root else Path.cwd() / args.collection_id
    try:
        stats = upload_collection(
            args.collection_id,
            root,
            bucket_name=args.bucket,
            year=args.year,
            overwrite=args.overwrite,
            execute=args.execute,
        )
    except (ValueError, FileNotFoundError) as e:
        logger.error("%s", e)
        return 1
    return 1 if stats["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
