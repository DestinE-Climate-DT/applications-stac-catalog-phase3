# tests/test_hydromet_workflow.py
"""HydroMet consumes the item folders the Climate DT workflow writes as they are."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from stac_dedl_core.appconfig import load_app_config

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "apps" / "hydromet"
STAGING = APP_DIR / "staging"
sys.path.insert(0, str(STAGING))

import workflow_items as wi  # noqa: E402

COLLECTION_ID = "EO.DWD.STAT.HYDROMET_EXTREMES"
ROOT_DIR = "EO.DWD.STAT.HYDROMET"
KEYS = ["model", "experiment", "generation", "realization", "activity", "resolution"]


def workflow_item_name(start="19900101", end="20141231", suffix="ifs-nemo__hist__2__1__baseline__high"):
    """Same format as get_stac_structure in the workflow's app_utils.sh."""
    return f"{COLLECTION_ID}_{start}T000000_{end}T230000__{suffix}"


def write_workflow_output(member: Path, start="19900101", end="20141231",
                          suffix="ifs-nemo__hist__2__1__baseline__high",
                          regions=("grl", "med")) -> Path:
    item = member / ROOT_DIR / "data" / start[:4] / workflow_item_name(start, end, suffix)
    item.mkdir(parents=True)
    fs, fe = f"{start[:4]}_{start[4:6]}_{start[6:]}", f"{end[:4]}_{end[4:6]}_{end[6:]}"
    (item / f"{fs}_T00_00_to_{end[:4]}_01_01_T00_00_KO_params.nc").write_bytes(b"nc")
    (item / f"{fs}_T00_00_to_{end[:4]}_01_01_T00_00_DDF.nc").write_bytes(b"nc")
    for region in regions:
        (item / f"{fs}_T00_00_to_{fe}_T23_00_events_T5_{region}.csv").write_text("a;b\n1;2\n")
    return item


# ── name parsing ──────────────────────────────────────────────────────────

def test_parse_workflow_item_name():
    start, end, props = wi.parse_item_name(workflow_item_name(), COLLECTION_ID, KEYS)
    assert (f"{start:%Y-%m-%d}", f"{end:%Y-%m-%d %H}") == ("1990-01-01", "2014-12-31 23")
    assert props == {
        "model": "ifs-nemo", "experiment": "hist", "generation": "2",
        "realization": "1", "activity": "baseline", "resolution": "high",
    }


def test_parse_keeps_any_period_and_values():
    # e.g. a storyline: neither 1990-2014 nor 2015-2049, values kept verbatim
    name = workflow_item_name("20170101", "20261231", "IFS-FESOM__Tplus2.0K__2__3__story-nudging__standard")
    start, end, props = wi.parse_item_name(name, COLLECTION_ID, KEYS)
    assert (start.year, end.year) == (2017, 2026)
    assert props["activity"] == "story-nudging" and props["realization"] == "3"


@pytest.mark.parametrize("name, reason", [
    (f"{ROOT_DIR}_19900101T000000_20141231T230000__a__b__c__d__e__f", "does not start"),
    (workflow_item_name(suffix="a__b__c__d__e"), "5 '__' suffix values"),
    (workflow_item_name(suffix="a__b____d__e__f"), "empty suffix values"),
    (workflow_item_name(start="19901301"), "invalid timestamp"),
    (workflow_item_name(start="20150101", end="20141231"), "ends before"),
])
def test_parse_rejects(name, reason):
    with pytest.raises(ValueError, match=reason):
        wi.parse_item_name(name, COLLECTION_ID, KEYS)


def test_load_item_checks_year_folder(tmp_path):
    item = tmp_path / "data" / "1991" / workflow_item_name()
    item.mkdir(parents=True)
    with pytest.raises(ValueError, match="year folder 1991"):
        wi.load_item(item, COLLECTION_ID, KEYS)


@pytest.mark.parametrize("given", ["member", "root", "data"])
def test_resolve_data_dir(tmp_path, given):
    write_workflow_output(tmp_path / "member")
    source = {"member": tmp_path / "member",
              "root": tmp_path / "member" / ROOT_DIR,
              "data": tmp_path / "member" / ROOT_DIR / "data"}[given]
    assert wi.resolve_data_dir(source, ROOT_DIR) == tmp_path / "member" / ROOT_DIR / "data"


# ── config ────────────────────────────────────────────────────────────────

def test_hydromet_config_matches_workflow(monkeypatch, tmp_path):
    monkeypatch.setenv("CATALOG_HOME_DIR", str(tmp_path))
    cfg = load_app_config(APP_DIR)
    assert cfg.id == COLLECTION_ID
    assert cfg.collection_dir == tmp_path / ROOT_DIR
    assert cfg.property_order == KEYS
    assert (cfg.temporal_start, cfg.temporal_end) == ("1990-01-01T00:00:00Z", "2049-12-31T23:00:00Z")


def test_collection_root_dir_must_be_a_folder_name(tmp_path):
    app = tmp_path / "apps" / "demo"
    (tmp_path / "apps" / "_shared").mkdir(parents=True)
    app.mkdir()
    (tmp_path / "apps" / "_shared" / "simulations.yaml").write_text(yaml.safe_dump(
        {"s": {"model": "M", "start_year": 1990, "end_year": 1991}}))
    (app / "catalog_config.yaml").write_text(yaml.safe_dump(
        {"id": "EO.TEST.DAT.DEMO", "simulations": ["s"], "collection_root_dir": "a/b"}))
    with pytest.raises(ValueError, match="single folder"):
        load_app_config(app)


# ── end to end: stage -> (move) -> update ─────────────────────────────────

def run(script, home, *args):
    env = {**os.environ, "CATALOG_HOME_DIR": str(home)}
    return subprocess.run(
        [sys.executable, str(STAGING / script), *args],
        cwd=APP_DIR, env=env, capture_output=True, text=True,
    )


def read_items(root: Path) -> dict[str, dict]:
    return {p.stem: json.loads(p.read_text()) for p in (root / "metadata" / "items").glob("*.json")}


def test_in_place_on_workflow_output(tmp_path):
    """CATALOG_HOME_DIR = member folder: no move.py, nothing renamed."""
    member = tmp_path / "member"
    write_workflow_output(member)

    assert run("stage.py", member, "--execute").returncode == 0
    result = run("update.py", member)
    assert result.returncode == 0, result.stderr

    root = member / ROOT_DIR
    collection = json.loads((root / "metadata" / "collection.json").read_text())
    assert collection["extent"]["temporal"]["interval"] == [["1990-01-01T00:00:00Z", "2049-12-31T23:00:00Z"]]
    assert not (member / COLLECTION_ID).exists()  # no second collection folder
    items = read_items(root)
    assert list(items) == [workflow_item_name()]
    item = items[workflow_item_name()]
    assert item["id"] == workflow_item_name()
    assert item["collection"] == COLLECTION_ID
    assert item["properties"]["resolution"] == "high"
    assert item["properties"]["start_datetime"] == "1990-01-01T00:00:00Z"
    assert len(item["assets"]) == 4
    # hrefs relative to the bucket root, without the local folder name
    assert all(a["href"].startswith(f"data/1990/{workflow_item_name()}/") for a in item["assets"].values())


def test_gather_several_experiments(tmp_path):
    hist = tmp_path / "hist"
    proj = tmp_path / "proj"
    write_workflow_output(hist)
    write_workflow_output(proj, "20150101", "20491231", "ifs-nemo__SSP3-7.0__2__1__projections__high")
    bad = proj / ROOT_DIR / "data" / "2015" / f"{COLLECTION_ID}_20150101T000000_20491231T230000__x"
    bad.mkdir()
    home = tmp_path / "catalog"
    home.mkdir()

    assert run("stage.py", home, "--execute").returncode == 0
    result = run("move.py", home, "--source-dir", str(hist), "--source-dir", str(proj / ROOT_DIR),
                 "--link", "--execute")
    assert result.returncode == 1  # the invalid item folder is reported
    assert "Skipping item folder" in result.stderr
    result = run("update.py", home)
    assert result.returncode == 0, result.stderr

    items = read_items(home / ROOT_DIR)
    assert sorted(items) == sorted([
        workflow_item_name(),
        workflow_item_name("20150101", "20491231", "ifs-nemo__SSP3-7.0__2__1__projections__high"),
    ])
    proj_item = items[workflow_item_name("20150101", "20491231", "ifs-nemo__SSP3-7.0__2__1__projections__high")]
    assert proj_item["properties"]["end_datetime"] == "2049-12-31T23:00:00Z"
    assert (home / ROOT_DIR / "data" / "2015").is_dir()


def test_check_data_script(tmp_path):
    write_workflow_output(tmp_path / "member")
    ok = subprocess.run(["bash", str(STAGING / "check_data.sh"), str(tmp_path / "member")],
                        capture_output=True, text=True)
    assert ok.returncode == 0, ok.stdout
    assert "1 item(s), 0 problem(s)" in ok.stdout

    (tmp_path / "member" / ROOT_DIR / "data" / "1990" / f"{COLLECTION_ID}_19900101T000000_20141231T230000__a__b").mkdir()
    bad = subprocess.run(["bash", str(STAGING / "check_data.sh"), str(tmp_path / "member")],
                         capture_output=True, text=True)
    assert bad.returncode != 0
    assert "INVALID NAME" in bad.stdout


def test_upload_target_is_confirmed_bucket_layout(tmp_path):
    """Confirmed by DWD: s3://usergenerated-proposal-eo.dwd.stat.hydromet-extremes/
    holds data/ and metadata/ at the bucket root. The local folder
    EO.DWD.STAT.HYDROMET is not a key level."""
    from stac_dedl_core.upload import upload_collection
    from tests.test_upload import FakeS3Client

    member = tmp_path / "member"
    write_workflow_output(member)
    assert run("stage.py", member, "--execute").returncode == 0
    assert run("update.py", member).returncode == 0

    bucket = "usergenerated-proposal-eo.dwd.stat.hydromet-extremes"
    client = FakeS3Client(expected_bucket=bucket)
    stats = upload_collection(COLLECTION_ID, member / ROOT_DIR, execute=True, s3_client=client)
    assert stats["items_new"] == 1 and stats["failed"] == 0
    keys = set(client.objects)
    assert {k.split("/")[0] for k in keys} == {"data", "metadata"}
    assert f"metadata/items/{workflow_item_name()}.json" in keys
    assert "metadata/collection.json" in keys
    assert any(k.startswith(f"data/1990/{workflow_item_name()}/") for k in keys)
