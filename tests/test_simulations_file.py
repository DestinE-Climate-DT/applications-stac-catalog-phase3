# tests/test_simulations_file.py
from pathlib import Path

import yaml

SIMULATIONS_FILE = (
    Path(__file__).resolve().parents[1] / "apps" / "_shared" / "simulations.yaml"
)

EXPECTED_GEN2_KEYS = {
    f"{model}_generation-2_{kind}"
    for model in ("ifs-nemo", "ifs-fesom", "icon")
    for kind in ("historical", "control", "projection")
}
EXPECTED_STORYLINE_KEYS = {"storylines-hist", "storylines-cont", "storylines-plus2K"}


def load():
    with SIMULATIONS_FILE.open() as f:
        return yaml.safe_load(f)


def test_file_exists_and_parses():
    data = load()
    assert isinstance(data, dict)


def test_all_expected_keys_present():
    data = load()
    assert set(data) == EXPECTED_GEN2_KEYS | EXPECTED_STORYLINE_KEYS


def test_every_entry_has_required_fields():
    required = {"model", "experiment", "generation", "realization",
                "activity", "start_year", "end_year"}
    for key, entry in load().items():
        assert required.issubset(entry), f"{key} missing {required - set(entry)}"


def test_canonical_spellings():
    data = load()
    assert data["ifs-nemo_generation-2_historical"]["experiment"] == "hist"
    assert data["ifs-nemo_generation-2_control"]["experiment"] == "cont"
    assert data["ifs-nemo_generation-2_projection"]["experiment"] == "SSP3-7.0"
    assert data["storylines-plus2K"]["experiment"] == "Tplus2.0K"


def test_control_runs_match_historical_except_experiment():
    data = load()
    for model in ("ifs-nemo", "ifs-fesom", "icon"):
        hist = dict(data[f"{model}_generation-2_historical"])
        cont = dict(data[f"{model}_generation-2_control"])
        assert cont.pop("experiment") == "cont"
        assert hist.pop("experiment") == "hist"
        assert hist == cont


def test_storylines_have_five_realizations_and_2026_end():
    data = load()
    for key in ("storylines-hist", "storylines-cont", "storylines-plus2K"):
        assert data[key]["realization"] == [1, 2, 3, 4, 5]
        assert data[key]["start_year"] == 2017
        assert data[key]["end_year"] == 2026
        assert data[key]["resolution"] == "standard"
        assert data[key]["activity"] == "story-nudging"
