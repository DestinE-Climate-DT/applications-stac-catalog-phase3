# tests/test_hydroland_stage.py
import importlib.util
from pathlib import Path

import pytest
import yaml

from stac_dedl_core.appconfig import load_app_config

REPO_ROOT = Path(__file__).resolve().parents[1]
STAGE_PY = REPO_ROOT / "apps" / "hydroland" / "staging" / "stage.py"


def load_stage_module():
    spec = importlib.util.spec_from_file_location("hydroland_stage", STAGE_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SIMS = {
    "ifs-nemo_generation-2_historical": {
        "model": "IFS-NEMO", "experiment": "hist", "generation": 2,
        "realization": 1, "activity": "baseline",
        "start_year": 1990, "end_year": 2014,
    },
}


@pytest.fixture
def app_dir(tmp_path, monkeypatch):
    app = tmp_path / "apps" / "hydroland"
    shared = tmp_path / "apps" / "_shared"
    app.mkdir(parents=True)
    shared.mkdir(parents=True)
    (shared / "simulations.yaml").write_text(yaml.safe_dump(SIMS))
    home = tmp_path / "home"
    home.mkdir()
    (app / "catalog_config.yaml").write_text(yaml.safe_dump({
        "id": "EO.UFZ.DAT.HYDROLAND",
        "title": "t", "description": "d", "short_description": "s",
        "license": "LGPL-3.0-or-later",
        "bbox": [-180, -56, 180, 84],
        "item_folder_level": "MM",
        "item_config_optional": True,
        "split_data_type_items": True,
        "app_data_dir": str(tmp_path / "raw"),
        "catalog_home_dir": str(home),
        "simulations": ["ifs-nemo_generation-2_historical"],
    }))
    monkeypatch.delenv("APP_DATA_DIR", raising=False)
    monkeypatch.delenv("CATALOG_HOME_DIR", raising=False)
    monkeypatch.delenv("SIMULATIONS_FILE", raising=False)
    return app


def test_parse_monthly_asset_filename():
    stage = load_stage_module()
    parsed = stage.parse_monthly_asset_filename(
        "1990_01_01_T00_00_to_1990_01_31_T23_00_mHM_Fluxes_States.nc"
    )
    assert parsed == {
        "year": "1990", "month": "01",
        "start_timestamp": "19900101T000000",
        "end_timestamp": "19900131T230000",
        "data_type": "mhm",
    }
    parsed_daily = stage.parse_monthly_asset_filename(
        "1990_01_01_to_1990_01_31_daily_mHM_Fluxes_States.nc"
    )
    assert parsed_daily == {
        "year": "1990", "month": "01",
        "start_timestamp": "19900101T000000",
        "end_timestamp": "19900131T230000",
        "data_type": "mhm",
    }
    parsed_mrm = stage.parse_monthly_asset_filename(
        "1990_01_01_T00_00_to_1990_01_31_T23_00_mRM_Fluxes_States.nc"
    )
    assert parsed_mrm["data_type"] == "mrm"
    assert stage.parse_monthly_asset_filename("random.nc") is None


def test_parse_indicator_filename():
    stage = load_stage_module()
    ym = stage.parse_indicator_filename("1990_01_2014_12_aridity_index.nc")
    assert ym == {
        "start_timestamp": "19900101T000000",
        "end_timestamp": "20141231T230000",
        "start_year": "1990",
        "token": "aridity_index",
    }
    perc = stage.parse_indicator_filename(
        "1990_01_2014_12_95th_percentile_discharge_indicators.nc"
    )
    assert perc["token"] == "95th_percentile_discharge_indicators"
    yy = stage.parse_indicator_filename(
        "1990_2049_soil_moisture_deficit_scen_SWC_L01.nc"
    )
    assert yy == {
        "start_timestamp": "19900101T000000",
        "end_timestamp": "20491231T230000",
        "start_year": "1990",
        "token": "soil_moisture_deficit_scen_SWC_L01",
    }
    assert stage.parse_indicator_filename("random.nc") is None


def test_stage_indicators_maps_ref_and_scen(app_dir, tmp_path):
    stage = load_stage_module()
    # add the projection sim + indicators config to the app config
    cfg_path = app_dir / "catalog_config.yaml"
    cfg_dict = yaml.safe_load(cfg_path.read_text())
    cfg_dict["simulations"] = [
        "ifs-nemo_generation-2_historical",
        "ifs-nemo_generation-2_projection",
    ]
    src = tmp_path / "indicators"
    src.mkdir()
    (src / "1990_01_2014_12_aridity_index.nc").write_text("x")
    (src / "1990_2049_soil_moisture_deficit_scen_SWC_L01.nc").write_text("x")
    cfg_dict["indicators"] = {
        "source_dir": str(src),
        "reference_simulation": "ifs-nemo_generation-2_historical",
        "scenario_simulation": "ifs-nemo_generation-2_projection",
        "scenario_markers": ["scen", "percent_change"],
    }
    cfg_path.write_text(yaml.safe_dump(cfg_dict))
    # the shared sims file needs the projection entry too
    shared = app_dir.parent / "_shared" / "simulations.yaml"
    sims = yaml.safe_load(shared.read_text())
    sims["ifs-nemo_generation-2_projection"] = {
        "model": "IFS-NEMO", "experiment": "SSP3-7.0", "generation": 2,
        "realization": 1, "activity": "projections",
        "start_year": 2015, "end_year": 2049,
    }
    shared.write_text(yaml.safe_dump(sims))

    cfg = load_app_config(app_dir)
    stats = stage.stage_indicators(cfg, link_mode="copy", execute=True)
    assert stats["recognized"] == 2 and stats["created_links"] == 2

    items = {p.name for p in (cfg.collection_dir / "data").rglob("*") if p.is_dir()
             and p.name.startswith("EO.UFZ.DAT.HYDROLAND_")}
    assert any("hist" in n and n.endswith("__aridity_index") for n in items)
    assert any("SSP3-7.0" in n and n.endswith("__soil_moisture_deficit_scen_SWC_L01")
               for n in items)


def test_create_monthly_skeleton(app_dir):
    stage = load_stage_module()
    cfg = load_app_config(app_dir)
    stats = stage.create_monthly_skeleton(cfg, execute=True)
    # 1990-2014 = 25 years × 12 months × 2 data_types (mhm, mrm) = 600 folders
    assert stats["total"] == 600
    assert stats["created"] == 600
    assert stats["existing"] == 0
    expected = (
        cfg.collection_dir / "data" / "1990" / "01" /
        "EO.UFZ.DAT.HYDROLAND_19900101T000000_19900131T230000"
        "__IFS-NEMO__hist__generation-2__baseline__realization-1__mhm"
    )
    assert expected.is_dir()



def test_real_app_config_loads():
    """The committed hydroland catalog_config.yaml resolves against the real
    shared simulations.yaml."""
    cfg = load_app_config(REPO_ROOT / "apps" / "hydroland")
    assert cfg.id == "EO.UFZ.DAT.HYDROLAND"
    assert len(cfg.simulations) == 6
    assert cfg.property_order == [
        "model", "experiment", "generation", "activity", "realization", "data_type",
    ]
    assert cfg.temporal_start == "1990-01-01T00:00:00Z"
    assert cfg.temporal_end == "2049-12-31T23:00:00Z"
