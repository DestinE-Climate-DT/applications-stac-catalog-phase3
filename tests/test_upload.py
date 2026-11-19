# tests/test_upload.py
import hashlib
import io
import json
from pathlib import Path

import pytest
from botocore.exceptions import ClientError

from stac_dedl_core.upload import (
    build_upload_plan,
    get_default_bucket_name,
    iter_upload_pairs,
    upload_collection,
)


class FakeS3Client:
    """In-memory bucket: key -> (bytes, metadata)."""

    def __init__(self, existing=(), expected_bucket=None):
        self.objects = {key: (b"", {}) for key in existing}
        self.uploaded = []
        self.deleted = []
        self.expected_bucket = expected_bucket

    def _check(self, bucket):
        if self.expected_bucket is not None:
            assert bucket == self.expected_bucket, f"unexpected bucket: {bucket!r}"

    def head_object(self, Bucket, Key):
        self._check(Bucket)
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "404"}}, "HeadObject")
        body, meta = self.objects[Key]
        return {"ContentLength": len(body), "Metadata": meta}

    def get_object(self, Bucket, Key):
        self._check(Bucket)
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        return {"Body": io.BytesIO(self.objects[Key][0])}

    def list_objects_v2(self, Bucket, Prefix, ContinuationToken=None):
        self._check(Bucket)
        keys = sorted(k for k in self.objects if k.startswith(Prefix))
        start = int(ContinuationToken or 0)
        page = keys[start:start + 2]  # tiny pages to exercise pagination
        out = {"Contents": [{"Key": k, "Size": len(self.objects[k][0])} for k in page]}
        if start + 2 < len(keys):
            out.update(IsTruncated=True, NextContinuationToken=str(start + 2))
        return out

    def upload_file(self, Filename, Bucket, Key, Config=None, ExtraArgs=None):
        self._check(Bucket)
        # Multi-GB NetCDF assets need the tuned multipart chunk size, so the
        # caller is expected to pass one through rather than take boto3 defaults.
        assert Config is not None, "upload_file called without a TransferConfig"
        self.objects[Key] = (Path(Filename).read_bytes(), dict((ExtraArgs or {}).get("Metadata", {})))
        self.uploaded.append((Filename, Bucket, Key))

    def delete_objects(self, Bucket, Delete):
        self._check(Bucket)
        for obj in Delete["Objects"]:
            self.objects.pop(obj["Key"], None)
            self.deleted.append(obj["Key"])
        return {}


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


STATS_ZERO = {
    "matched": 0, "uploaded": 0, "skipped_existing": 0, "failed": 0, "deleted": 0,
    "items_new": 0, "items_unchanged": 0, "items_replaced": 0, "conflicts": 0,
}


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


def test_iter_upload_pairs_year_filter_keeps_collection_metadata(collection_root):
    keys = [k for _, k in iter_upload_pairs(collection_root, "EO.TEST.DAT.DEMO", year="2015")]
    assert keys == [
        "metadata/collection.json",
        "data/2015/01/ITEM_X/file_2015_01.nc",
    ]


def test_dry_run_uploads_nothing(collection_root):
    client = FakeS3Client()
    stats = upload_collection(
        "EO.TEST.DAT.DEMO", collection_root, execute=False, s3_client=client
    )
    assert stats == {**STATS_ZERO, "matched": 5}
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
    assert (stats["uploaded"], stats["skipped_existing"]) == (4, 1)

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
    assert "--year" in result.stdout and "--replace" in result.stdout


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
        def upload_file(self, Filename, Bucket, Key, Config=None, ExtraArgs=None):
            if Key.endswith("file_1990_01.nc"):
                raise ClientError({"Error": {"Code": "503"}}, "PutObject")
            super().upload_file(Filename, Bucket, Key, Config=Config, ExtraArgs=ExtraArgs)
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


# ── items: sequential uploads of separate workflow results ─────────────────

CID = "EO.TEST.DAT.DEMO"


def make_run(tmp_path: Path, name: str, item_id: str, files: dict[str, str], year="1990") -> Path:
    """A collection root holding one item, as one workflow run produces it."""
    root = tmp_path / name / CID
    (root / "metadata" / "items").mkdir(parents=True)
    (root / "metadata" / "collection.json").write_text('{"id": "EO.TEST.DAT.DEMO"}')
    item_dir = root / "data" / year / item_id
    item_dir.mkdir(parents=True)
    for fname, content in files.items():
        (item_dir / fname).write_text(content)
    assets = {f: {"href": f"data/{year}/{item_id}/{f}"} for f in sorted(files)}
    (root / "metadata" / "items" / f"{item_id}.json").write_text(
        json.dumps({"id": item_id, "assets": assets})
    )
    return root


def upload(root, client, **kw):
    return upload_collection(CID, root, execute=True, s3_client=client, **kw)


def test_plan_groups_item_files_and_puts_json_last(tmp_path):
    root = make_run(tmp_path, "a", "ITEM_A", {"x.nc": "1", "y.csv": "2"})
    keys = [k for _, k in build_upload_plan(root, CID).pairs()]
    assert keys == [
        "metadata/collection.json",
        "data/1990/ITEM_A/x.nc",
        "data/1990/ITEM_A/y.csv",
        "metadata/items/ITEM_A.json",
    ]


def test_second_run_needs_nothing_from_the_first(tmp_path):
    client = FakeS3Client()
    s1 = upload(make_run(tmp_path, "a", "ITEM_A", {"x.nc": "1"}), client)
    s2 = upload(make_run(tmp_path, "b", "ITEM_B", {"x.nc": "2"}, year="2015"), client)
    assert (s1["items_new"], s2["items_new"], s2["conflicts"]) == (1, 1, 0)
    assert s2["skipped_existing"] == 1  # collection.json, identical
    assert {"metadata/items/ITEM_A.json", "metadata/items/ITEM_B.json"} <= set(client.objects)


def test_repeated_upload_is_skipped(tmp_path):
    client = FakeS3Client()
    root = make_run(tmp_path, "a", "ITEM_A", {"x.nc": "1", "y.csv": "2"})
    upload(root, client)
    client.uploaded.clear()
    stats = upload(root, client)
    assert (stats["items_unchanged"], stats["conflicts"], stats["uploaded"]) == (1, 0, 0)
    assert client.uploaded == []


def test_resume_after_failed_data_upload(tmp_path):
    """A failed file keeps the item unpublished; the retry completes it."""
    class FailOnce(FakeS3Client):
        failed = False
        def upload_file(self, Filename, Bucket, Key, Config=None, ExtraArgs=None):
            if Key.endswith("y.csv") and not self.failed:
                self.failed = True
                raise ClientError({"Error": {"Code": "503"}}, "PutObject")
            super().upload_file(Filename, Bucket, Key, Config=Config, ExtraArgs=ExtraArgs)

    client = FailOnce()
    root = make_run(tmp_path, "a", "ITEM_A", {"x.nc": "1", "y.csv": "2"})
    s1 = upload(root, client)
    assert s1["failed"] == 1 and "metadata/items/ITEM_A.json" not in client.objects
    s2 = upload(root, client)
    assert (s2["items_new"], s2["uploaded"], s2["skipped_existing"]) == (1, 2, 2)
    assert "metadata/items/ITEM_A.json" in client.objects


def test_changed_item_stops_upload_without_replace(tmp_path):
    client = FakeS3Client()
    upload(make_run(tmp_path, "a", "ITEM_A", {"x.nc": "1", "old.csv": "o"}), client)
    before = dict(client.objects)

    rerun = make_run(tmp_path, "b", "ITEM_A", {"x.nc": "2", "new.csv": "n"})
    stats = upload(rerun, client)
    assert stats["conflicts"] == 1 and stats["uploaded"] == 0
    assert client.objects == before  # nothing sent


def test_same_size_content_change_is_detected_by_md5(tmp_path):
    client = FakeS3Client()
    upload(make_run(tmp_path, "a", "ITEM_A", {"x.nc": "1"}), client)
    stats = upload(make_run(tmp_path, "b", "ITEM_A", {"x.nc": "2"}), client)
    assert stats["conflicts"] == 1


def test_replace_swaps_the_item(tmp_path):
    client = FakeS3Client()
    upload(make_run(tmp_path, "a", "ITEM_A", {"x.nc": "1", "keep.nc": "k", "old.csv": "o"}), client)
    upload(make_run(tmp_path, "c", "ITEM_C", {"z.nc": "z"}, year="2015"), client)

    rerun = make_run(tmp_path, "b", "ITEM_A", {"x.nc": "2", "keep.nc": "k", "new.csv": "n"})
    client.uploaded.clear()
    stats = upload(rerun, client, replace=True)

    assert (stats["items_replaced"], stats["conflicts"]) == (1, 0)
    keys = set(client.objects)
    assert "data/1990/ITEM_A/old.csv" not in keys          # stale file deleted
    assert "data/1990/ITEM_A/new.csv" in keys
    assert client.objects["data/1990/ITEM_A/x.nc"][0] == b"2"
    assert "data/2015/ITEM_C/z.nc" in keys                  # other items untouched
    uploaded = [k for _, _, k in client.uploaded]
    assert "data/1990/ITEM_A/keep.nc" not in uploaded       # identical file not resent
    assert uploaded[-1] == "metadata/items/ITEM_A.json"     # JSON last
    assert json.loads(client.objects["metadata/items/ITEM_A.json"][0])["assets"].keys() == {
        "keep.nc", "new.csv", "x.nc"}


def test_uploads_store_md5_metadata(tmp_path):
    client = FakeS3Client()
    upload(make_run(tmp_path, "a", "ITEM_A", {"x.nc": "1"}), client)
    assert client.objects["data/1990/ITEM_A/x.nc"][1]["md5"] == hashlib.md5(b"1").hexdigest()


def test_objects_without_md5_compare_by_size(tmp_path):
    """Objects uploaded before checksums were stored are compared by size only."""
    root = make_run(tmp_path, "a", "ITEM_A", {"x.nc": "1"})
    client = FakeS3Client()
    client.objects = {
        "metadata/collection.json": (b'{"id": "EO.TEST.DAT.DEMO"}', {}),
        "data/1990/ITEM_A/x.nc": (b"1", {}),
        "metadata/items/ITEM_A.json": (
            (root / "metadata" / "items" / "ITEM_A.json").read_bytes(), {}),
    }
    assert upload(root, client)["items_unchanged"] == 1


def test_new_item_leaves_unlisted_remote_files_unless_replace(tmp_path):
    root = make_run(tmp_path, "a", "ITEM_A", {"x.nc": "1"})
    client = FakeS3Client(existing={"data/1990/ITEM_A/leftover.nc"})
    upload(root, client)
    assert "data/1990/ITEM_A/leftover.nc" in client.objects

    client = FakeS3Client(existing={"data/1990/ITEM_A/leftover.nc"})
    upload(root, client, replace=True)
    assert "data/1990/ITEM_A/leftover.nc" not in client.objects


def test_year_filter_only_checks_that_years_items(tmp_path):
    client = FakeS3Client()
    upload(make_run(tmp_path, "a", "ITEM_A", {"x.nc": "1"}), client)
    # Changed 1990 item, but only 2015 is uploaded: no conflict
    root = make_run(tmp_path, "b", "ITEM_A", {"x.nc": "2"})
    item_b = root / "data" / "2015" / "ITEM_B"
    item_b.mkdir(parents=True)
    (item_b / "y.nc").write_text("y")
    (root / "metadata" / "items" / "ITEM_B.json").write_text('{"id": "ITEM_B"}')
    stats = upload(root, client, year="2015")
    assert (stats["conflicts"], stats["items_new"]) == (0, 1)


def test_two_data_folders_for_one_item_raise(tmp_path):
    root = make_run(tmp_path, "a", "ITEM_A", {"x.nc": "1"})
    (root / "data" / "2015" / "ITEM_A").mkdir(parents=True)
    with pytest.raises(ValueError, match="more than one data folder"):
        build_upload_plan(root, CID)


def test_cli_exits_non_zero_on_conflict(tmp_path, monkeypatch):
    import sys
    from stac_dedl_core import upload as upload_module
    client = FakeS3Client()
    upload(make_run(tmp_path, "a", "ITEM_A", {"x.nc": "1"}), client)
    rerun = make_run(tmp_path, "b", "ITEM_A", {"x.nc": "2"})
    monkeypatch.setattr(upload_module, "_make_s3_client", lambda: client)
    monkeypatch.setattr(sys, "argv", ["upload", CID, "--root", str(rerun), "--execute"])
    with pytest.raises(SystemExit) as exc:
        upload_module.main()
    assert exc.value.code == 1
