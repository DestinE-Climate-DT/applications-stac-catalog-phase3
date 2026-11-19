"""Shared upload of a staged collection tree to the DEDL S3 bucket.

Dry run by default. Uploads the collection metadata, then item by item the
item's data and its item JSON last, so an item is never listed before its
files are there. Items already published are compared with the local ones:
identical items are skipped (a repeated or resumed upload, or one with --year,
is harmless), differing ones stop the upload unless --replace is given.

Usage:
    python -m stac_dedl_core.upload EO.UFZ.DAT.HYDROLAND \
        --root /path/to/EO.UFZ.DAT.HYDROLAND [--year 2015] [--replace] [--execute]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Tuple

import boto3
from boto3.s3.transfer import TransferConfig
from botocore.client import Config
from botocore.exceptions import ClientError
from dotenv import load_dotenv

from stac_dedl_core.config import (
    COLLECTION_BUCKET_OVERRIDES,
    COLLECTION_KEY_PREFIX_OVERRIDES,
    S3_ENDPOINT_URL,
    S3_USER_GENERATED_BUCKET_PREFIX,
)

logger = logging.getLogger(__name__)

# Collection assets are multi-GB NetCDF files, so the boto3 default 8 MiB
# multipart chunk measures ~40% slower than 64 MiB against the DEDL endpoint and
# would put a 34 GB mRM file at >4000 parts. 64 MiB keeps part counts in the
# hundreds and saturates the link with the same 10 concurrent threads.
TRANSFER_CONFIG = TransferConfig(
    multipart_threshold=64 * 1024**2,
    multipart_chunksize=64 * 1024**2,
    max_concurrency=10,
)


def get_default_bucket_name(collection_id: str) -> str:
    """Bucket for a collection: an explicit override, else the naming convention.

    S3 bucket names cannot contain underscores, so they become hyphens.
    """
    if collection_id in COLLECTION_BUCKET_OVERRIDES:
        return COLLECTION_BUCKET_OVERRIDES[collection_id]
    return f"{S3_USER_GENERATED_BUCKET_PREFIX}-{collection_id.lower().replace('_', '-')}"


def get_default_key_prefix(collection_id: str) -> str:
    """Top-level key prefix inside the bucket. Empty means objects sit at the root."""
    return COLLECTION_KEY_PREFIX_OVERRIDES.get(collection_id, "")


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


# ── upload plan ─────────────────────────────────────────────────────────────


@dataclass
class ItemUpload:
    """One STAC item: its metadata JSON and the files of its data folder."""

    item_id: str
    json_path: Path
    json_key: str
    payload: dict
    # Remote key prefix of the item's data folder ("" when it has no data folder)
    data_prefix: str
    files: list[Tuple[Path, str]] = field(default_factory=list)


@dataclass
class UploadPlan:
    collection_files: list[Tuple[Path, str]]  # metadata/ outside items/
    items: list[ItemUpload]
    loose_files: list[Tuple[Path, str]]  # data/ files outside any item folder

    def pairs(self) -> Iterator[Tuple[Path, str]]:
        """Upload order: collection metadata, then per item its data and its
        JSON last, then loose data files. An item JSON never reaches the bucket
        before its data."""
        yield from self.collection_files
        for item in self.items:
            yield from item.files
            yield item.json_path, item.json_key
        yield from self.loose_files


def build_upload_plan(
    collection_root: Path,
    collection_id: str,
    year: str | None = None,
    key_prefix: str | None = None,
) -> UploadPlan:
    """Group the files under collection_root into collection metadata, items and
    loose data files.

    An item is a metadata/items/<id>.json; its data folder is the folder named
    <id> under data/ (at any depth, so any item_folder_level works). With
    `year`, only items (and loose files) under data/<year>/ are included;
    collection metadata always is.
    """
    if key_prefix is None:
        key_prefix = get_default_key_prefix(collection_id)
    prefix = key_prefix.strip("/")

    def key_for(p: Path) -> str:
        rel = p.relative_to(collection_root).as_posix()
        return f"{prefix}/{rel}" if prefix else rel

    metadata_dir = collection_root / "metadata"
    items_dir = metadata_dir / "items"
    collection_files = []
    if metadata_dir.is_dir():
        collection_files = [
            (f, key_for(f)) for f in sorted(metadata_dir.rglob("*"))
            if f.is_file() and items_dir not in f.parents
        ]

    items: dict[str, ItemUpload] = {}
    for json_path in sorted(items_dir.glob("*.json")) if items_dir.is_dir() else []:
        with json_path.open(encoding="utf-8") as fh:
            payload = json.load(fh)
        item_id = str(payload.get("id") or json_path.stem)
        items[item_id] = ItemUpload(item_id, json_path, key_for(json_path), payload, "")

    # One walk over data/: folders named after an item are item folders;
    # everything else is a loose file.
    data_dir = collection_root / "data"
    item_years: dict[str, str] = {}
    loose_files = []
    if data_dir.is_dir():
        for dirpath, dirnames, filenames in os.walk(data_dir, followlinks=True):
            dirnames.sort()
            current = Path(dirpath)
            for name in list(dirnames):
                if name in items:
                    item_dir = current / name
                    item = items[name]
                    if item.data_prefix:
                        raise ValueError(
                            f"Item {name} has more than one data folder: "
                            f"{item.data_prefix} and {key_for(item_dir)}/"
                        )
                    item.data_prefix = key_for(item_dir) + "/"
                    item.files = [
                        (f, key_for(f)) for f in sorted(item_dir.rglob("*")) if f.is_file()
                    ]
                    item_years[name] = item_dir.relative_to(data_dir).parts[0]
                    dirnames.remove(name)  # its files belong to the item
            for name in sorted(filenames):
                f = current / name
                if f.is_file():
                    loose_files.append((f, key_for(f)))

    selected = [
        item for item in items.values()
        if not year or item_years.get(item.item_id) == year
    ]
    if year:
        loose_files = [
            (f, k) for f, k in loose_files
            if f.relative_to(data_dir).parts[0] == year
        ]
    return UploadPlan(collection_files, selected, loose_files)


def iter_upload_pairs(
    collection_root: Path,
    collection_id: str,
    year: str | None = None,
    key_prefix: str | None = None,
) -> Iterator[Tuple[Path, str]]:
    """Yield (file_path, object_key) in upload order (see UploadPlan.pairs)."""
    yield from build_upload_plan(collection_root, collection_id, year, key_prefix).pairs()


# ── remote state ────────────────────────────────────────────────────────────


def _is_missing(error: ClientError) -> bool:
    return error.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound")


def _md5(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(8 * 1024**2), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _head(s3, bucket: str, key: str) -> dict | None:
    try:
        return s3.head_object(Bucket=bucket, Key=key)
    except ClientError as e:
        if _is_missing(e):
            return None
        raise


def _get_json(s3, bucket: str, key: str) -> dict | None:
    try:
        body = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
    except ClientError as e:
        if _is_missing(e):
            return None
        raise
    return json.loads(body)


def _list_sizes(s3, bucket: str, prefix: str) -> dict[str, int]:
    """All keys below prefix with their size."""
    sizes: dict[str, int] = {}
    kwargs = {"Bucket": bucket, "Prefix": prefix}
    while True:
        page = s3.list_objects_v2(**kwargs)
        for obj in page.get("Contents", []):
            sizes[obj["Key"]] = obj["Size"]
        if not page.get("IsTruncated"):
            return sizes
        kwargs["ContinuationToken"] = page["NextContinuationToken"]


def _same_file(s3, bucket: str, key: str, path: Path, remote_size: int | None) -> bool:
    """Size must match; the md5 too when the object carries one (uploads made
    by this module store it as metadata, older objects only allow a size check)."""
    if remote_size is None or remote_size != path.stat().st_size:
        return False
    head = _head(s3, bucket, key) or {}
    remote_md5 = (head.get("Metadata") or {}).get("md5")
    return remote_md5 is None or remote_md5 == _md5(path)


def _item_differences(s3, bucket: str, item: ItemUpload) -> tuple[list[str], dict[str, int]]:
    """Why the published item differs from the local one (empty: identical),
    plus the sizes of its remote data objects."""
    remote = _list_sizes(s3, bucket, item.data_prefix) if item.data_prefix else {}
    local = dict((key, path) for path, key in item.files)
    reasons = []
    if _get_json(s3, bucket, item.json_key) != item.payload:
        reasons.append("item JSON differs")
    if set(remote) - set(local):
        reasons.append(f"{len(set(remote) - set(local))} file(s) only in the bucket")
    if set(local) - set(remote):
        reasons.append(f"{len(set(local) - set(remote))} file(s) not yet in the bucket")
    changed = [
        key for key in set(local) & set(remote)
        if not _same_file(s3, bucket, key, local[key], remote[key])
    ]
    if changed:
        reasons.append(f"{len(changed)} file(s) with different content")
    return reasons, remote


def _delete(s3, bucket: str, keys: list[str]) -> int:
    deleted = 0
    for start in range(0, len(keys), 1000):
        batch = keys[start:start + 1000]
        response = s3.delete_objects(
            Bucket=bucket, Delete={"Objects": [{"Key": k} for k in batch], "Quiet": True}
        )
        errors = response.get("Errors", [])
        for error in errors:
            logger.error("Failed deleting %s: %s", error.get("Key"), error.get("Message"))
        if errors:
            raise RuntimeError(f"Could not delete {len(errors)} object(s) in {bucket}")
        deleted += len(batch)
    return deleted


# ── upload ──────────────────────────────────────────────────────────────────


def upload_collection(
    collection_id: str,
    root: Path,
    bucket: str | None = None,
    year: str | None = None,
    overwrite: bool = False,
    execute: bool = False,
    s3_client=None,
    key_prefix: str | None = None,
    replace: bool = False,
) -> dict:
    """Upload a staged collection tree to S3. Dry run unless execute=True.

    Items are compared with what is already published (item JSON, file names,
    sizes and checksums):
    - not in the bucket: its data is uploaded, then its JSON;
    - identical: skipped, so a repeated or resumed upload is harmless;
    - different (e.g. a re-run of the same experiment): a conflict. Without
      `replace` the whole upload stops before anything is sent. With `replace`
      the item is unpublished (JSON deleted), files the new version no longer
      has are deleted, changed and new files uploaded, and the JSON last.
    Collection metadata and loose data files are skipped when they exist,
    unless `overwrite`. The dry run does not look at the bucket.
    """
    root = Path(root).expanduser().resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Collection root not found: {root}")

    bucket_name = bucket or get_default_bucket_name(collection_id)
    plan = build_upload_plan(root, collection_id, year=year, key_prefix=key_prefix)
    pairs = list(plan.pairs())

    if not pairs:
        logger.warning(
            "--year %s matched no files; check the year or the directory structure.",
            year,
        )

    stats = {
        "matched": len(pairs), "uploaded": 0, "skipped_existing": 0, "failed": 0,
        "deleted": 0, "items_new": 0, "items_unchanged": 0, "items_replaced": 0,
        "conflicts": 0,
    }

    if not execute:
        for file_path, object_key in pairs:
            logger.info("[DRY RUN] %s -> s3://%s/%s", file_path, bucket_name, object_key)
        logger.info(
            "[DRY RUN] %s file(s) in %s item(s) would be uploaded to bucket '%s' "
            "(the bucket is not checked in a dry run). Re-run with --execute to upload.",
            stats["matched"], len(plan.items), bucket_name,
        )
        return stats

    s3 = s3_client if s3_client is not None else _make_s3_client()

    # 1. Check every item against the bucket before sending anything.
    states: list[tuple[ItemUpload, str, dict[str, int]]] = []
    conflicts = []
    for item in plan.items:
        if _head(s3, bucket_name, item.json_key) is None:
            remote = _list_sizes(s3, bucket_name, item.data_prefix) if item.data_prefix else {}
            states.append((item, "new", remote))
            continue
        reasons, remote = _item_differences(s3, bucket_name, item)
        if not reasons:
            states.append((item, "unchanged", remote))
        else:
            states.append((item, "changed", remote))
            conflicts.append((item, reasons))

    if conflicts:
        for item, reasons in conflicts:
            logger.log(
                logging.WARNING if replace else logging.ERROR,
                "Item %s is already published and differs: %s",
                item.item_id, "; ".join(reasons),
            )
        if not replace:
            stats["conflicts"] = len(conflicts)
            logger.error(
                "%s published item(s) differ from the local ones. Nothing was uploaded. "
                "Re-run with --replace to replace them (old files they no longer "
                "have are deleted).", len(conflicts),
            )
            return stats

    def put(path: Path, key: str) -> bool:
        try:
            s3.upload_file(
                str(path), bucket_name, key, Config=TRANSFER_CONFIG,
                ExtraArgs={"Metadata": {"md5": _md5(path)}},
            )
        except Exception as e:  # noqa: BLE001 — count and continue with the rest
            logger.error("Failed uploading %s: %s", key, e)
            stats["failed"] += 1
            return False
        logger.info("Uploaded: s3://%s/%s", bucket_name, key)
        stats["uploaded"] += 1
        return True

    def put_unless_exists(path: Path, key: str) -> None:
        if not overwrite and _head(s3, bucket_name, key) is not None:
            logger.info("Exists, skipping: %s", key)
            stats["skipped_existing"] += 1
            return
        put(path, key)

    # 2. Collection metadata
    for path, key in plan.collection_files:
        put_unless_exists(path, key)

    # 3. Items: data first, JSON last
    for item, state, remote in states:
        if state == "unchanged" and not overwrite:
            logger.info("Item already published and identical, skipping: %s", item.item_id)
            stats["items_unchanged"] += 1
            stats["skipped_existing"] += len(item.files) + 1
            continue

        local_keys = {key for _, key in item.files}
        stale = sorted(set(remote) - local_keys)
        if state == "changed":
            # Unpublish first, so the catalog never lists a half-replaced item
            stats["deleted"] += _delete(s3, bucket_name, [item.json_key])
            logger.info("Unpublished %s for replacement", item.item_id)
        if stale:
            if state == "new" and not replace:
                logger.warning(
                    "Item %s: %s file(s) in the bucket that it does not list are left "
                    "in place (--replace removes them): %s",
                    item.item_id, len(stale), ", ".join(stale),
                )
            else:
                stats["deleted"] += _delete(s3, bucket_name, stale)

        ok = True
        for path, key in item.files:
            if not overwrite and _same_file(s3, bucket_name, key, path, remote.get(key)):
                logger.info("Exists, skipping: %s", key)
                stats["skipped_existing"] += 1
                continue
            ok = put(path, key) and ok
        if not ok:
            logger.error(
                "Item %s not published: some of its files failed to upload. "
                "Re-run the upload to retry.", item.item_id,
            )
            continue
        if put(item.json_path, item.json_key):
            stats["items_replaced" if state == "changed" else "items_new"] += 1

    # 4. Loose data files
    for path, key in plan.loose_files:
        put_unless_exists(path, key)

    if stats["failed"]:
        logger.error(
            "Upload finished with errors. failed=%s uploaded=%s skipped_existing=%s",
            stats["failed"], stats["uploaded"], stats["skipped_existing"],
        )
    else:
        logger.info(
            "Done. matched=%s uploaded=%s skipped_existing=%s deleted=%s "
            "items new=%s unchanged=%s replaced=%s",
            stats["matched"], stats["uploaded"], stats["skipped_existing"], stats["deleted"],
            stats["items_new"], stats["items_unchanged"], stats["items_replaced"],
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
        "--key-prefix",
        help="Top-level key prefix inside the bucket. Defaults to the configured "
             "value for this collection ('' for most, the collection ID for HydroLand). "
             "Pass an empty string to force objects to the bucket root.",
    )
    parser.add_argument(
        "--year",
        help="Only upload the items under data/<year>/ (collection metadata always included).",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Re-upload objects that already exist in the bucket, also of identical items.",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Replace published items that differ from the local ones (e.g. a re-run "
             "of the same experiment): unpublish, delete files the new version no "
             "longer has, upload the new files and publish again. Without it, such "
             "items stop the upload before anything is sent.",
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
        key_prefix=args.key_prefix,
        replace=args.replace,
    )
    if stats.get("failed") or stats.get("conflicts"):
        sys.exit(1)


if __name__ == "__main__":
    main()
