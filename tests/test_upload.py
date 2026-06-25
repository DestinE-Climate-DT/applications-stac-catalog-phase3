# tests/test_upload.py
from pathlib import Path

import pytest
from botocore.exceptions import ClientError

from stac_dedl_core.upload import (
    get_default_bucket_name,
    iter_upload_pairs,
    upload_collection,
)


class FakeS3Client:
    def __init__(self, existing=(), expected_bucket=None):
        self.existing = set(existing)
        self.uploaded = []
        self.expected_bucket = expected_bucket

    def head_object(self, Bucket, Key):
        if self.expected_bucket is not None:
            assert Bucket == self.expected_bucket, f"unexpected bucket: {Bucket!r}"
        if Key not in self.existing:
            raise ClientError({"Error": {"Code": "404"}}, "HeadObject")
        return {}

    def upload_file(self, Filename, Bucket, Key):
        if self.expected_bucket is not None:
            assert Bucket == self.expected_bucket, f"unexpected bucket: {Bucket!r}"
        self.uploaded.append((Filename, Bucket, Key))


@pytest.fixture
def collection_root(tmp_path: Path) -> Path:
    root = tmp_path / "EO.TEST.DAT.DEMO"
    (root / "metadata" / "items").mkdir(parents=True)
    (root / "metadata" / "collection.json").write_text("{}")
    (root / "metadata" / "items" / "item1.json").write_text("{}")
    for year, month in (("1990", "01"), ("1990", "02"), ("2015", "01")):
        d = root / "data" / year / month / "ITEM_X"
        d.mkdir(parents=True)
        (d / f"file_{year}_{month}.nc").write_text("nc")
    return root


def test_default_bucket_name():
    assert get_default_bucket_name("EO.BSC.DAT.ENERGY_INDICATORS") == (
        "usergenerated-proposal-eo.bsc.dat.energy_indicators"
    )


def test_iter_upload_pairs_metadata_first_then_years(collection_root):
    keys = [key for _, key in iter_upload_pairs(collection_root, "EO.TEST.DAT.DEMO")]
    assert keys[0].startswith("EO.TEST.DAT.DEMO/metadata/")
    assert keys == [
        "EO.TEST.DAT.DEMO/metadata/collection.json",
        "EO.TEST.DAT.DEMO/metadata/items/item1.json",
        "EO.TEST.DAT.DEMO/data/1990/01/ITEM_X/file_1990_01.nc",
        "EO.TEST.DAT.DEMO/data/1990/02/ITEM_X/file_1990_02.nc",
        "EO.TEST.DAT.DEMO/data/2015/01/ITEM_X/file_2015_01.nc",
    ]


def test_iter_upload_pairs_year_filter_keeps_metadata(collection_root):
    keys = [k for _, k in iter_upload_pairs(collection_root, "EO.TEST.DAT.DEMO", year="2015")]
    assert keys == [
        "EO.TEST.DAT.DEMO/metadata/collection.json",
        "EO.TEST.DAT.DEMO/metadata/items/item1.json",
        "EO.TEST.DAT.DEMO/data/2015/01/ITEM_X/file_2015_01.nc",
    ]


def test_dry_run_uploads_nothing(collection_root):
    client = FakeS3Client()
    stats = upload_collection(
        "EO.TEST.DAT.DEMO", collection_root, execute=False, s3_client=client
    )
    assert stats == {"matched": 5, "uploaded": 0, "skipped_existing": 0, "failed": 0}
    assert client.uploaded == []


def test_execute_uploads_all(collection_root):
    client = FakeS3Client()
    stats = upload_collection(
        "EO.TEST.DAT.DEMO", collection_root, execute=True, s3_client=client
    )
    assert stats["uploaded"] == 5
    buckets = {b for _, b, _ in client.uploaded}
    assert buckets == {"usergenerated-proposal-eo.test.dat.demo"}


def test_execute_skips_existing_unless_overwrite(collection_root):
    existing = {"EO.TEST.DAT.DEMO/metadata/collection.json"}
    client = FakeS3Client(existing=existing)
    stats = upload_collection(
        "EO.TEST.DAT.DEMO", collection_root, execute=True, s3_client=client
    )
    assert stats == {"matched": 5, "uploaded": 4, "skipped_existing": 1, "failed": 0}

    client2 = FakeS3Client(existing=existing, expected_bucket="usergenerated-proposal-eo.test.dat.demo")
    stats2 = upload_collection(
        "EO.TEST.DAT.DEMO", collection_root, execute=True,
        overwrite=True, s3_client=client2,
    )
    assert stats2["uploaded"] == 5


def test_missing_root_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        upload_collection("EO.X.Y.Z", tmp_path / "nope", s3_client=FakeS3Client())


def test_cli_help_runs():
    import subprocess, sys
    result = subprocess.run(
        [sys.executable, "-m", "stac_dedl_core.upload", "--help"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert "--year" in result.stdout


def test_non_404_head_error_propagates(collection_root):
    class ErrorClient(FakeS3Client):
        def head_object(self, Bucket, Key):
            raise ClientError({"Error": {"Code": "403"}}, "HeadObject")
    with pytest.raises(ClientError):
        upload_collection(
            "EO.TEST.DAT.DEMO", collection_root, execute=True, s3_client=ErrorClient()
        )


def test_failed_upload_counted_and_continues(collection_root):
    class FlakyClient(FakeS3Client):
        def upload_file(self, Filename, Bucket, Key):
            if Key.endswith("file_1990_01.nc"):
                raise ClientError({"Error": {"Code": "503"}}, "PutObject")
            super().upload_file(Filename, Bucket, Key)
    client = FlakyClient()
    stats = upload_collection(
        "EO.TEST.DAT.DEMO", collection_root, execute=True, s3_client=client
    )
    assert stats["failed"] == 1
    assert stats["uploaded"] == 4
