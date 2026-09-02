# tests/test_collection_builder.py
import json
from pathlib import Path

import pytest
import yaml

from stac_dedl_core.appconfig import load_app_config
from stac_dedl_core.collection_builder import write_collection_files

SIMS = {
    "test-sim_historical": {
        "model": "IFS-NEMO", "experiment": "hist", "generation": 2,
        "realization": 1, "activity": "baseline",
        "start_year": 1990, "end_year": 2014,
    },
}

APP_YAML = {
    "id": "EO.TEST.DAT.DEMO",
    "title": "Demo title",
    "description": "Demo description",
    "short_description": "Demo short",
    "license": "LGPL-3.0-or-later",
    "license_url": "https://example.org/license",
    "license_name": "Example License",
    "doi": {
        "url": "https://doi.org/10.1234/demo",
        "code": "10.1234/demo",
        "title": "Demo dataset",
        "citation": "Demo dataset citation.",
    },
    "related": {"url": "https://example.org/repo", "title": "Demo repo"},
    "keywords": ["Climate", "Demo"],
    "providers": [
        {"name": "UFZ", "roles": ["producer"], "url": "https://www.ufz.de"},
    ],
    "thumbnail_url": "https://example.org/thumb.png",
    "bbox": [-180, -56, 180, 84],
    "item_folder_level": "MM",
    "app_data_dir": "/tmp/appdata",
    "catalog_home_dir": ".",
    "simulations": ["test-sim_historical"],
    "split_data_type_items": True,
}


@pytest.fixture
def cfg(tmp_path):
    app_dir = tmp_path / "apps" / "demo"
    shared = tmp_path / "apps" / "_shared"
    app_dir.mkdir(parents=True)
    shared.mkdir(parents=True)
    (app_dir / "catalog_config.yaml").write_text(yaml.safe_dump(APP_YAML))
    (shared / "simulations.yaml").write_text(yaml.safe_dump(SIMS))
    return load_app_config(app_dir)


def test_writes_both_files(cfg):
    cpath, ccpath = write_collection_files(cfg)
    assert cpath == cfg.collection_dir / "metadata" / "collection.json"
    assert ccpath == cfg.collection_dir / "metadata" / "collection_config.json"
    assert (cfg.collection_dir / "data").is_dir()


def test_collection_json_content(cfg):
    cpath, _ = write_collection_files(cfg)
    coll = json.loads(cpath.read_text())
    assert coll["type"] == "Collection"
    assert coll["id"] == "EO.TEST.DAT.DEMO"
    assert coll["stac_version"] == "1.0.0"
    assert coll["title"] == "Demo title"
    assert coll["license"] == "LGPL-3.0-or-later"
    assert coll["dedl:short_description"] == "Demo short"
    assert coll["extent"]["spatial"]["bbox"] == [[-180.0, -56.0, 180.0, 84.0]]
    assert coll["extent"]["temporal"]["interval"] == [
        ["1990-01-01T00:00:00Z", "2014-12-31T23:00:00Z"]
    ]
    rels = {link["rel"] for link in coll["links"]}
    assert rels == {"license", "cite-as", "describedby"}
    assert coll["sci:publications"] == [
        {"sci:doi": "10.1234/demo", "sci:citation": "Demo dataset citation."}
    ]
    assert coll["assets"]["thumbnail"]["href"] == "https://example.org/thumb.png"
    assert coll["assets"]["thumbnail"]["roles"] == ["thumbnail"]
    assert coll["assets"]["thumbnail"]["type"] == "image/png"


def test_collection_config_content(cfg):
    _, ccpath = write_collection_files(cfg)
    config = json.loads(ccpath.read_text())
    assert config["id"] == "EO.TEST.DAT.DEMO"
    assert config["item_folder_level"] == "MM"
    assert config["item_asset_ignore_list"] == ["item_config.json"]
    assert config["item_config_optional"] is True
    assert config["additional_property_keys"] == [
        "model", "experiment", "generation", "activity", "realization", "data_type",
    ]
    assert config["bbox"] == [-180.0, -56.0, 180.0, 84.0]


def test_no_doi_no_scientific_extension(cfg, tmp_path):
    cfg.doi = None
    cfg.collection_dir.mkdir(parents=True, exist_ok=True)
    cpath, _ = write_collection_files(cfg, overwrite=True)
    coll = json.loads(cpath.read_text())
    assert "sci:publications" not in coll
    # stac_extensions must always be present (DEDL validation requires it),
    # but is empty when there is no DOI / scientific extension.
    assert coll["stac_extensions"] == []


def test_refuses_overwrite_by_default(cfg):
    write_collection_files(cfg)
    with pytest.raises(FileExistsError):
        write_collection_files(cfg)
    write_collection_files(cfg, overwrite=True)  # explicit overwrite works


def test_collection_json_key_order_matches_hydroland(cfg):
    cpath, _ = write_collection_files(cfg)
    coll = json.loads(cpath.read_text())
    assert list(coll) == [
        "type", "id", "stac_version", "description", "links",
        "stac_extensions", "dedl:short_description", "sci:publications",
        "title", "extent", "license", "keywords", "providers", "assets",
    ]


def test_bbox_whole_numbers_serialize_as_ints(cfg):
    cpath, ccpath = write_collection_files(cfg)
    for raw in (cpath.read_text(), ccpath.read_text()):
        assert "-180.0" not in raw
        assert "-56.0" not in raw


def test_no_related_no_describedby_link(cfg):
    cfg.related = None
    cfg.collection_dir.mkdir(parents=True, exist_ok=True)
    cpath, _ = write_collection_files(cfg, overwrite=True)
    coll = json.loads(cpath.read_text())
    assert {l["rel"] for l in coll["links"]} == {"license", "cite-as"}


def test_published_data_type_key_absent_by_default(cfg):
    """Without the option the published key stays 'data_type'."""
    _, ccpath = write_collection_files(cfg)
    keys = json.loads(ccpath.read_text())["additional_property_keys"]
    assert keys[-1] == "data_type"
    assert keys == cfg.property_order


def test_published_data_type_key_renames_only_published_key(tmp_path):
    """HydroLand case: rename the published key, leave property_order alone.

    Item folder names are built from property_order VALUES, so renaming the
    published key must not change property_order (or folder names would break).
    """
    app_dir = tmp_path / "apps" / "demo"
    shared = tmp_path / "apps" / "_shared"
    app_dir.mkdir(parents=True)
    shared.mkdir(parents=True)
    payload = dict(APP_YAML, published_data_type_key="collection_data_type")
    (app_dir / "catalog_config.yaml").write_text(yaml.safe_dump(payload))
    (shared / "simulations.yaml").write_text(yaml.safe_dump(SIMS))
    cfg = load_app_config(app_dir)

    # internal order is untouched -> folder names unaffected
    assert cfg.property_order[-1] == "data_type"

    _, ccpath = write_collection_files(cfg)
    keys = json.loads(ccpath.read_text())["additional_property_keys"]
    assert keys[-1] == "collection_data_type"
    # same length, so the positional zip against folder suffixes still lines up
    assert len(keys) == len(cfg.property_order)
