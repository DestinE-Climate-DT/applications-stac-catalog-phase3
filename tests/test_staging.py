# tests/test_staging.py
from pathlib import Path

import pytest

from stac_dedl_core.staging import (
    build_item_folder_name,
    classify_data_type,
    format_catalog_property,
    join_item_folder_name,
    materialize_file,
    ordered_properties,
    safe_slug,
)


def test_classify_data_type_first_match_wins():
    rules = [
        {"match": "_mHM_Fluxes_States", "data_type": "mhm"},
        {"match": "river_discharge", "data_type": "river_discharge_indicators"},
    ]
    assert classify_data_type("a/b/1990_01_river_discharge.nc", rules) == "river_discharge_indicators"
    assert classify_data_type("x/2020_to_x_mHM_Fluxes_States.nc", rules) == "mhm"


def test_classify_data_type_matches_subfolder_in_path():
    rules = [{"match": "soil_moisture", "data_type": "soil_moisture_indicators"}]
    assert classify_data_type("data/2020/soil_moisture/file.nc", rules) == "soil_moisture_indicators"


def test_classify_data_type_default_when_no_match():
    rules = [{"match": "river_discharge", "data_type": "rd"}]
    assert classify_data_type("data/foo.nc", rules, default="mhm") == "mhm"
    assert classify_data_type("data/foo.nc", [], default="mrm") == "mrm"


def test_safe_slug_basic():
    assert safe_slug("IFS-NEMO") == "IFS-NEMO"
    assert safe_slug("SSP3-7.0") == "SSP3-7.0"
    assert safe_slug("a b/c") == "a-b-c"
    assert safe_slug("") == "NA"
    assert safe_slug(None) == "NA"


def test_format_catalog_property_prefixes():
    assert format_catalog_property("generation", 2) == "generation-2"
    assert format_catalog_property("generation", "generation-2") == "generation-2"
    assert format_catalog_property("realization", 1) == "realization-1"
    assert format_catalog_property("simulation_id", "freeze-run") == "id-freeze-run"
    assert format_catalog_property("model", "IFS-NEMO") == "IFS-NEMO"


def test_join_item_folder_name():
    assert join_item_folder_name(
        "EO.UFZ.DAT.HYDROLAND", "19900101T000000", "20141231T230000",
        ["IFS-NEMO", "hist", "generation-2"],
    ) == "EO.UFZ.DAT.HYDROLAND_19900101T000000_20141231T230000__IFS-NEMO__hist__generation-2"


def test_join_item_folder_name_no_suffix():
    assert join_item_folder_name("EO.X.Y.Z", "A", "B", []) == "EO.X.Y.Z_A_B"


def test_build_item_folder_name_formats_properties():
    name = build_item_folder_name(
        "EO.UFZ.DAT.HYDROLAND", "19900101T000000", "20141231T230000",
        {"model": "IFS-NEMO", "experiment": "hist", "generation": 2,
         "activity": "baseline", "realization": 1},
    )
    assert name == (
        "EO.UFZ.DAT.HYDROLAND_19900101T000000_20141231T230000"
        "__IFS-NEMO__hist__generation-2__baseline__realization-1"
    )


def test_ordered_properties_follows_order_and_skips_missing():
    props = {"realization": 1, "model": "ICON", "experiment": "cont"}
    assert ordered_properties(props, ["model", "experiment", "resolution", "realization"]) == {
        "model": "ICON", "experiment": "cont", "realization": 1,
    }


@pytest.mark.parametrize("mode", ["symlink", "hardlink", "copy", "move"])
def test_materialize_file_modes(tmp_path: Path, mode: str):
    src = tmp_path / "src" / "file.nc"
    src.parent.mkdir()
    src.write_text("data")
    dst = tmp_path / "dst" / "file.nc"

    # dry run: reports True (would create) but creates nothing
    assert materialize_file(src, dst, mode=mode, execute=False) is True
    assert not dst.exists()

    assert materialize_file(src, dst, mode=mode, execute=True) is True
    assert dst.exists()
    assert dst.read_text() == "data"
    if mode == "symlink":
        assert dst.is_symlink()
    if mode == "move":
        assert not src.exists()
    else:
        assert src.exists()


def test_materialize_file_skips_existing(tmp_path: Path):
    src = tmp_path / "a.nc"
    src.write_text("new")
    dst = tmp_path / "out" / "a.nc"
    dst.parent.mkdir()
    dst.write_text("old")
    assert materialize_file(src, dst, mode="copy", execute=True) is False
    assert dst.read_text() == "old"


def test_materialize_file_rejects_unknown_mode(tmp_path: Path):
    with pytest.raises(ValueError):
        materialize_file(tmp_path / "a", tmp_path / "b", mode="teleport")


def test_materialize_file_skips_dangling_symlink(tmp_path: Path):
    src = tmp_path / "a.nc"
    src.write_text("data")
    dst = tmp_path / "out" / "a.nc"
    dst.parent.mkdir()
    dst.symlink_to(tmp_path / "gone.nc")  # dangling — target does not exist
    assert materialize_file(src, dst, mode="copy", execute=True) is False
