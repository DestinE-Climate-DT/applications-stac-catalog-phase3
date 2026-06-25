# tests/test_appconfig.py
from pathlib import Path

import pytest
import yaml

from stac_dedl_core.appconfig import AppConfig, load_app_config

REPO_ROOT = Path(__file__).resolve().parents[1]

MINIMAL_SIMS = {
    "test-sim_historical": {
        "model": "IFS-NEMO", "experiment": "hist", "generation": 2,
        "realization": 1, "activity": "baseline",
        "start_year": 1990, "end_year": 2014,
    },
    "test-sim_projection": {
        "model": "IFS-NEMO", "experiment": "SSP3-7.0", "generation": 2,
        "realization": 1, "activity": "projections",
        "start_year": 2015, "end_year": 2049,
    },
    "test-storyline": {
        "model": "IFS-FESOM", "experiment": "cont", "generation": 2,
        "realization": [1, 2, 3], "activity": "story-nudging",
        "resolution": "standard", "start_year": 2017, "end_year": 2026,
    },
}

MINIMAL_APP_YAML = {
    "id": "EO.TEST.DAT.DEMO",
    "title": "Demo",
    "description": "Demo description",
    "short_description": "Demo short",
    "license": "CC-BY-4.0",
    "bbox": [-12, 34.05, 45, 71.95],
    "item_folder_level": "MM",
    "app_data_dir": "/tmp/appdata",
    "catalog_home_dir": ".",
    "simulations": ["test-sim_historical", "test-sim_projection"],
}


def write_app(tmp_path: Path, app_yaml: dict, sims: dict = MINIMAL_SIMS) -> Path:
    app_dir = tmp_path / "apps" / "demo"
    shared = tmp_path / "apps" / "_shared"
    app_dir.mkdir(parents=True)
    shared.mkdir(parents=True)
    (app_dir / "catalog_config.yaml").write_text(yaml.safe_dump(app_yaml))
    (shared / "simulations.yaml").write_text(yaml.safe_dump(sims))
    return app_dir


def test_loads_minimal_config(tmp_path):
    cfg = load_app_config(write_app(tmp_path, MINIMAL_APP_YAML))
    assert isinstance(cfg, AppConfig)
    assert cfg.id == "EO.TEST.DAT.DEMO"
    assert len(cfg.simulations) == 2
    assert cfg.collection_dir.name == "EO.TEST.DAT.DEMO"


def test_temporal_extent_derived_t23(tmp_path):
    cfg = load_app_config(write_app(tmp_path, MINIMAL_APP_YAML))
    assert cfg.temporal_start == "1990-01-01T00:00:00Z"
    assert cfg.temporal_end == "2049-12-31T23:00:00Z"


def test_explicit_temporal_overrides_derivation(tmp_path):
    app = {**MINIMAL_APP_YAML, "temporal_start": "2000-01-01T00:00:00Z",
           "temporal_end": "2001-12-31T23:00:00Z"}
    cfg = load_app_config(write_app(tmp_path, app))
    assert cfg.temporal_start == "2000-01-01T00:00:00Z"
    assert cfg.temporal_end == "2001-12-31T23:00:00Z"


def test_overrides_merged_into_every_simulation(tmp_path):
    app = {**MINIMAL_APP_YAML, "overrides": {"resolution": "high"}}
    cfg = load_app_config(write_app(tmp_path, app))
    assert all(s.properties["resolution"] == "high" for s in cfg.simulations)
    assert "resolution" in cfg.property_order


def test_realization_list_expanded(tmp_path):
    app = {**MINIMAL_APP_YAML, "simulations": ["test-storyline"]}
    cfg = load_app_config(write_app(tmp_path, app))
    assert len(cfg.simulations) == 3
    assert [s.properties["realization"] for s in cfg.simulations] == [1, 2, 3]
    assert all(s.key == "test-storyline" for s in cfg.simulations)


def test_unknown_simulation_key_fails_loudly(tmp_path):
    app = {**MINIMAL_APP_YAML, "simulations": ["does-not-exist"]}
    with pytest.raises(KeyError, match="does-not-exist"):
        load_app_config(write_app(tmp_path, app))


def test_dash_in_collection_id_rejected(tmp_path):
    app = {**MINIMAL_APP_YAML, "id": "EO.TEST.DAT.BAD-ID"}
    with pytest.raises(ValueError, match="dash"):
        load_app_config(write_app(tmp_path, app))


def test_property_order_default_and_split_data_type(tmp_path):
    app = {**MINIMAL_APP_YAML, "split_data_type_items": True}
    cfg = load_app_config(write_app(tmp_path, app))
    assert cfg.property_order == [
        "model", "experiment", "generation", "activity", "realization", "data_type",
    ]


def test_explicit_property_order_wins(tmp_path):
    app = {**MINIMAL_APP_YAML,
           "property_order": ["model", "experiment", "generation",
                              "realization", "activity"]}
    cfg = load_app_config(write_app(tmp_path, app))
    assert cfg.property_order == [
        "model", "experiment", "generation", "realization", "activity",
    ]


def test_env_vars_override_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_DATA_DIR", "/env/data")
    monkeypatch.setenv("CATALOG_HOME_DIR", str(tmp_path / "env-home"))
    cfg = load_app_config(write_app(tmp_path, MINIMAL_APP_YAML))
    assert cfg.app_data_dir == Path("/env/data")
    assert cfg.catalog_home_dir == tmp_path / "env-home"


def test_simulations_file_env_var(tmp_path, monkeypatch):
    app_dir = write_app(tmp_path, MINIMAL_APP_YAML)
    alt = tmp_path / "alt-sims.yaml"
    alt.write_text(yaml.safe_dump(MINIMAL_SIMS))
    monkeypatch.setenv("SIMULATIONS_FILE", str(alt))
    cfg = load_app_config(app_dir)
    assert len(cfg.simulations) == 2


def test_real_shared_simulations_file_resolves(tmp_path, monkeypatch):
    """The repo's actual simulations.yaml works with the loader."""
    monkeypatch.setenv(
        "SIMULATIONS_FILE",
        str(REPO_ROOT / "apps" / "_shared" / "simulations.yaml"),
    )
    app = {**MINIMAL_APP_YAML,
           "simulations": ["ifs-nemo_generation-2_historical", "storylines-plus2K"]}
    cfg = load_app_config(write_app(tmp_path, app))
    # 1 historical + 5 storyline realizations
    assert len(cfg.simulations) == 6


def test_missing_id_contextual_error(tmp_path):
    app = {k: v for k, v in MINIMAL_APP_YAML.items() if k != "id"}
    with pytest.raises(KeyError, match="missing required field 'id'"):
        load_app_config(write_app(tmp_path, app))


def test_missing_year_field_contextual_error(tmp_path):
    sims = {"broken-sim": {"model": "ICON", "experiment": "hist",
                           "generation": 2, "realization": 1,
                           "activity": "baseline", "start_year": 1990}}
    app = {**MINIMAL_APP_YAML, "simulations": ["broken-sim"]}
    with pytest.raises(KeyError, match="missing required field 'end_year'"):
        load_app_config(write_app(tmp_path, app, sims=sims))


def test_expanded_simulations_do_not_share_mutable_values(tmp_path):
    sims = {"multi": {"model": "ICON", "experiment": "hist", "generation": 2,
                      "realization": [1, 2], "activity": "baseline",
                      "tags": ["a"], "start_year": 1990, "end_year": 2014}}
    app = {**MINIMAL_APP_YAML, "simulations": ["multi"]}
    cfg = load_app_config(write_app(tmp_path, app, sims=sims))
    cfg.simulations[0].properties["tags"].append("mutated")
    assert cfg.simulations[1].properties["tags"] == ["a"]


def test_relative_app_data_dir_resolves_against_app_dir(tmp_path):
    app = {**MINIMAL_APP_YAML, "app_data_dir": "raw"}
    app_dir = write_app(tmp_path, app)
    cfg = load_app_config(app_dir)
    assert cfg.app_data_dir == (app_dir / "raw").resolve()
