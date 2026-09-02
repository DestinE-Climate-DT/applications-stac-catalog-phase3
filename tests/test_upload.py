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
    # underscores in collection IDs must become hyphens (S3 bucket names forbid underscores)
    assert get_default_bucket_name("EO.BSC.DAT.ENERGY_INDICATORS") == (
        "usergenerated-proposal-eo.bsc.dat.energy-indicators"
    )
    assert get_default_bucket_name("EO.DWD.STAT.HYDROMET_EXTREMES") == (
        "usergenerated-proposal-eo.dwd.stat.hydromet-extremes"
    )


def test_iter_upload_pairs_metadata_first_then_years(collection_root):
    keys = [key for _, key in iter_upload_pairs(collection_root, "EO.TEST.DAT.DEMO")]
    assert keys[0].startswith("metadata/")
    assert keys == [
        "metadata/collection.json",
        "metadata/items/item1.json",
        "data/1990/01/ITEM_X/file_1990_01.nc",
        "data/1990/02/ITEM_X/file_1990_02.nc",
        "data/2015/01/ITEM_X/file_2015_01.nc",
    ]


def test_iter_upload_pairs_year_filter_keeps_metadata(collection_root):
    keys = [k for _, k in iter_upload_pairs(collection_root, "EO.TEST.DAT.DEMO", year="2015")]
    assert keys == [
        "metadata/collection.json",
        "metadata/items/item1.json",
        "data/2015/01/ITEM_X/file_2015_01.nc",
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
    existing = {"metadata/collection.json"}
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


def test_hydroland_bucket_override_matches_live_bucket():
    """HydroLand's bucket kept its original name; the collection ID changed later."""
    assert get_default_bucket_name("EO.UFZ.DAT.HYDROLAND") == (
        "usergenerated-proposal-eo.ufz.dat.ifs-nemo-hydroland"
    )


def test_upload_and_itemgen_agree_on_bucket():
    """The two modules must not drift apart again (they share one override map)."""
    from stac_dedl_core.generate_item_metadata import (
        get_default_bucket_name as itemgen_bucket,
    )
    for cid in ("EO.UFZ.DAT.HYDROLAND", "EO.UFZ.DAT.IFS_NEMO_HYDROLAND"):
        assert get_default_bucket_name(cid) == itemgen_bucket(cid)


def test_hydroland_keys_are_prefixed_with_collection_id(collection_root):
    """HydroLand stores objects under <collection_id>/ inside its bucket."""
    keys = [k for _, k in iter_upload_pairs(collection_root, "EO.UFZ.DAT.HYDROLAND")]
    assert all(k.startswith("EO.UFZ.DAT.HYDROLAND/") for k in keys)
    assert keys[0] == "EO.UFZ.DAT.HYDROLAND/metadata/collection.json"


def test_hydromet_keys_stay_unprefixed(collection_root):
    """HydroMet's manual layout has no prefix — this must not regress."""
    keys = [k for _, k in iter_upload_pairs(collection_root, "EO.DWD.STAT.HYDROMET_EXTREMES")]
    assert keys[0] == "metadata/collection.json"
    assert not any(k.startswith("EO.DWD") for k in keys)


def test_explicit_key_prefix_overrides_default(collection_root):
    keys = [k for _, k in iter_upload_pairs(collection_root, "EO.UFZ.DAT.HYDROLAND", key_prefix="")]
    assert keys[0] == "metadata/collection.json"
