# Shared Staging Foundation + HydroLand Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the shared staging/upload foundation in `stac_dedl_core` (per spec `docs/superpowers/specs/2026-06-11-shared-staging-upload-design.md`) and migrate hydroland onto it as the first consumer.

**Architecture:** Four new modules in `stac_dedl_core` (`appconfig`, `staging`, `collection_builder`, `upload`) plus a shared `apps/_shared/simulations.yaml`. HydroLand's staging is rewritten as a thin `staging/stage.py` that consumes the shared modules; its collection metadata moves from `run_hydroland_data_preparation.sh` into `catalog_config.yaml`. Energy/hydromet/fwi migrations are **separate follow-up plans**.

**Tech Stack:** Python ≥3.10, PyYAML, pystac (existing), boto3 1.35.99 (pinned), pytest. Conda env `stac-catalog` with `pip install -e .`.

**Conventions used throughout:**
- All commands run from the repo root: `/Users/lealroja/Documents/UFZ/Climate DT/stac-catalog-project/applications-stac-catalog-phase3` (quote the path — it contains a space).
- Canonical experiment spellings: `hist`, `cont`, `SSP3-7.0`, `Tplus2.0K` (per spec).
- Timestamps in item folder names: `<YYYY>0101T000000` / `<YYYY>1231T230000`.

---

### Task 1: Test infrastructure

**Files:**
- Modify: `pyproject.toml`
- Create: `tests/__init__.py` (empty)

- [ ] **Step 1: Add pyyaml to runtime deps and pytest as dev extra**

In `pyproject.toml`, change the `dependencies` list and add an optional group:

```toml
dependencies = [
    "pystac",
    "pystac[validation]",
    "pystac[orjson]",
    "shapely",
    "python-magic",
    "requests",
    "beautifulsoup4",
    "netCDF4",
    "boto3==1.35.99",
    "botocore==1.35.99",
    "python-dotenv",
    "pyyaml",
]

[project.optional-dependencies]
dev = ["pytest"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

(Keep the existing `[build-system]` and `[tool.setuptools.packages.find]` sections unchanged.)

- [ ] **Step 2: Create empty `tests/__init__.py`**

```bash
mkdir -p tests && touch tests/__init__.py
```

- [ ] **Step 3: Install and verify pytest runs**

Run: `cd "/Users/lealroja/Documents/UFZ/Climate DT/stac-catalog-project/applications-stac-catalog-phase3" && pip install -e ".[dev]" -q && python -m pytest -q`
Expected: `no tests ran` (exit code 5 is fine at this stage).

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml tests/__init__.py
git commit -m "chore: add pytest + pyyaml, test scaffolding"
```

---

### Task 2: Shared simulations file

**Files:**
- Create: `apps/_shared/simulations.yaml`
- Test: `tests/test_simulations_file.py`

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_simulations_file.py -v`
Expected: FAIL — `FileNotFoundError` (simulations.yaml does not exist yet).

- [ ] **Step 3: Create `apps/_shared/simulations.yaml`**

```yaml
# Shared Climate DT simulation definitions for all STAC apps.
# Keys are referenced from each app's catalog_config.yaml `simulations:` list.
# Canonical experiment spellings: hist / cont / SSP3-7.0 (follow hydroland's
# published items). Values here must be identical wherever the run is used;
# app-specific fields (e.g. resolution high vs 5km) belong in each app's
# `overrides:` section instead.

# ── Generation 2: historical / control / projection ──────────────────

ifs-nemo_generation-2_historical:
  model: IFS-NEMO
  experiment: hist
  generation: 2
  realization: 1
  activity: baseline
  start_year: 1990
  end_year: 2014

ifs-nemo_generation-2_control:
  model: IFS-NEMO
  experiment: cont
  generation: 2
  realization: 1
  activity: baseline
  start_year: 1990
  end_year: 2014

ifs-nemo_generation-2_projection:
  model: IFS-NEMO
  experiment: SSP3-7.0
  generation: 2
  realization: 1
  activity: projections
  start_year: 2015
  end_year: 2049

ifs-fesom_generation-2_historical:
  model: IFS-FESOM
  experiment: hist
  generation: 2
  realization: 1
  activity: baseline
  start_year: 1990
  end_year: 2014

ifs-fesom_generation-2_control:
  model: IFS-FESOM
  experiment: cont
  generation: 2
  realization: 1
  activity: baseline
  start_year: 1990
  end_year: 2014

ifs-fesom_generation-2_projection:
  model: IFS-FESOM
  experiment: SSP3-7.0
  generation: 2
  realization: 1
  activity: projections
  start_year: 2015
  end_year: 2049

icon_generation-2_historical:
  model: ICON
  experiment: hist
  generation: 2
  realization: 1
  activity: baseline
  start_year: 1990
  end_year: 2014

icon_generation-2_control:
  model: ICON
  experiment: cont
  generation: 2
  realization: 1
  activity: baseline
  start_year: 1990
  end_year: 2014

icon_generation-2_projection:
  model: ICON
  experiment: SSP3-7.0
  generation: 2
  realization: 1
  activity: projections
  start_year: 2015
  end_year: 2049

# ── Storyline runs (IFS-FESOM, story nudging, 5 realizations) ─────────

storylines-hist:
  model: IFS-FESOM
  experiment: hist
  generation: 2
  realization: [1, 2, 3, 4, 5]
  activity: story-nudging
  resolution: standard
  start_year: 2017
  end_year: 2026

storylines-cont:
  model: IFS-FESOM
  experiment: cont
  generation: 2
  realization: [1, 2, 3, 4, 5]
  activity: story-nudging
  resolution: standard
  start_year: 2017
  end_year: 2026

storylines-plus2K:
  model: IFS-FESOM
  experiment: Tplus2.0K
  generation: 2
  realization: [1, 2, 3, 4, 5]
  activity: story-nudging
  resolution: standard
  start_year: 2017
  end_year: 2026
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_simulations_file.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add apps/_shared/simulations.yaml tests/test_simulations_file.py
git commit -m "feat: add shared simulations.yaml (gen-2 hist/cont/projection + storylines)"
```

---

### Task 3: `stac_dedl_core/staging.py` — canonical naming + file materialisation

**Files:**
- Create: `stac_dedl_core/staging.py`
- Test: `tests/test_staging.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_staging.py
from pathlib import Path

import pytest

from stac_dedl_core.staging import (
    build_item_folder_name,
    format_catalog_property,
    join_item_folder_name,
    materialize_file,
    ordered_properties,
    safe_slug,
)


def test_safe_slug_basic():
    assert safe_slug("IFS-NEMO") == "IFS-NEMO"
    assert safe_slug("SSP3-7.0") == "SSP3-7.0"
    assert safe_slug("a b/c") == "a-b-c"
    assert safe_slug("") == "NA"


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_staging.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'stac_dedl_core.staging'`.

- [ ] **Step 3: Implement `stac_dedl_core/staging.py`**

```python
"""Canonical item-folder naming and file materialisation, shared by all apps.

This is the ONE implementation of the DEDL item folder convention:
    <COLLECTION_ID>_<start_ts>_<end_ts>__<value1>__<value2>__...
Promoted from apps/hydroland/staging/hydroland_data_preparation.py.
"""
from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Any, Iterable, Mapping

_slug_re = re.compile(r"[^A-Za-z0-9._-]+")

MATERIALIZE_MODES = ("symlink", "hardlink", "copy", "move")

# Property keys whose values get a "<prefix>-" in folder names, so that bare
# numbers like generation "2" remain readable as "generation-2".
_PROPERTY_PREFIXES = {
    "generation": "generation",
    "realization": "realization",
    "simulation_id": "id",
}


def safe_slug(value: Any) -> str:
    """Sanitize a value for use in filesystem/item names."""
    s = str(value).strip().replace(" ", "-")
    s = _slug_re.sub("-", s)
    s = re.sub(r"-{2,}", "-", s).strip("-")
    return s or "NA"


def format_catalog_property(key: str, value: Any) -> str:
    """Format one property value for the item folder suffix."""
    value_slug = safe_slug(value)
    prefix = _PROPERTY_PREFIXES.get(key)
    if prefix and not value_slug.startswith(f"{prefix}-"):
        return f"{prefix}-{value_slug}"
    return value_slug


def join_item_folder_name(
    collection_id: str,
    start_timestamp: str,
    end_timestamp: str,
    suffix_parts: Iterable[str],
) -> str:
    """Join already-formatted suffix parts into an item folder name."""
    name = f"{safe_slug(collection_id)}_{start_timestamp}_{end_timestamp}"
    parts = list(suffix_parts)
    if parts:
        name = f"{name}__{'__'.join(parts)}"
    return name


def build_item_folder_name(
    collection_id: str,
    start_timestamp: str,
    end_timestamp: str,
    properties: Mapping[str, Any],
) -> str:
    """Build an item folder name from an ORDERED property mapping."""
    return join_item_folder_name(
        collection_id,
        start_timestamp,
        end_timestamp,
        [format_catalog_property(k, v) for k, v in properties.items()],
    )


def ordered_properties(
    properties: Mapping[str, Any], order: Iterable[str]
) -> dict[str, Any]:
    """Return properties reordered by `order`, dropping keys not present."""
    return {k: properties[k] for k in order if k in properties}


def materialize_file(
    source: Path, target: Path, mode: str = "symlink", execute: bool = False
) -> bool:
    """Create `target` from `source` via the given mode.

    Returns True if the target was (or would be, in dry run) created,
    False if it already exists. Dry run (execute=False) touches nothing.
    """
    if mode not in MATERIALIZE_MODES:
        raise ValueError(
            f"Unsupported materialize mode '{mode}'. Expected one of {MATERIALIZE_MODES}"
        )

    if target.exists():
        return False
    if not execute:
        return True

    target.parent.mkdir(parents=True, exist_ok=True)
    if mode == "symlink":
        target.symlink_to(os.path.relpath(source, target.parent))
    elif mode == "hardlink":
        os.link(source, target)
    elif mode == "copy":
        shutil.copy2(source, target)
    else:  # move
        shutil.move(str(source), str(target))
    return True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_staging.py -v`
Expected: 12 passed (the materialize test is parametrized over 4 modes).

- [ ] **Step 5: Commit**

```bash
git add stac_dedl_core/staging.py tests/test_staging.py
git commit -m "feat: add stac_dedl_core.staging — canonical item naming + materialize_file"
```

---

### Task 4: `stac_dedl_core/appconfig.py` — per-app config loader

**Files:**
- Create: `stac_dedl_core/appconfig.py`
- Test: `tests/test_appconfig.py`

- [ ] **Step 1: Write the failing tests**

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_appconfig.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'stac_dedl_core.appconfig'`.

- [ ] **Step 3: Implement `stac_dedl_core/appconfig.py`**

```python
"""Load an app's catalog_config.yaml and resolve shared simulation definitions.

The single entry point is load_app_config(app_dir). It reads:
- <app_dir>/catalog_config.yaml          (all per-app input)
- apps/_shared/simulations.yaml          (shared run definitions; path can be
                                          overridden via $SIMULATIONS_FILE or
                                          the simulations_file argument)
and returns a fully resolved AppConfig.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# Year fields are structural, not item properties.
RESERVED_SIMULATION_KEYS = {"start_year", "end_year"}

# Default ordering for additional_property_keys / folder-name suffixes.
# Matches hydroland's published convention. Apps that published with a
# different order set `property_order:` explicitly in their yaml.
PREFERRED_PROPERTY_ORDER = [
    "model",
    "experiment",
    "generation",
    "activity",
    "realization",
    "resolution",
    "simulation_id",
    "region",
]


@dataclass
class Simulation:
    """One resolved run definition (realization lists already expanded)."""

    key: str
    start_year: int
    end_year: int
    properties: dict[str, Any]


@dataclass
class AppConfig:
    id: str
    title: str
    description: str
    short_description: str
    license: str
    bbox: list[float]
    item_folder_level: str
    app_data_dir: Path
    catalog_home_dir: Path
    simulations: list[Simulation]
    property_order: list[str]
    temporal_start: str
    temporal_end: str
    keywords: list[str] = field(default_factory=list)
    providers: list[dict] = field(default_factory=list)
    thumbnail_url: str | None = None
    thumbnail_mime: str = "image/png"
    doi: dict | None = None
    license_url: str | None = None
    license_name: str | None = None
    related: dict | None = None
    item_config_optional: bool = True
    split_data_type_items: bool = False

    @property
    def collection_dir(self) -> Path:
        return self.catalog_home_dir / self.id


def _load_yaml(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"Config file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        payload = yaml.safe_load(f)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a YAML mapping in {path}")
    return payload


def find_simulations_file(app_dir: Path) -> Path:
    env_path = os.getenv("SIMULATIONS_FILE")
    if env_path:
        return Path(env_path).expanduser()
    return app_dir.parent / "_shared" / "simulations.yaml"


def _resolve_simulations(
    selected: list[str],
    shared: dict[str, dict],
    overrides: dict[str, Any],
) -> list[Simulation]:
    resolved: list[Simulation] = []
    for key in selected:
        if key not in shared:
            raise KeyError(
                f"Unknown simulation key '{key}'. "
                f"Available keys: {sorted(shared)}"
            )
        entry = {**shared[key], **overrides}
        realizations = entry.get("realization", 1)
        if not isinstance(realizations, list):
            realizations = [realizations]
        for realization in realizations:
            properties = {
                k: v for k, v in entry.items() if k not in RESERVED_SIMULATION_KEYS
            }
            properties["realization"] = realization
            resolved.append(
                Simulation(
                    key=key,
                    start_year=int(entry["start_year"]),
                    end_year=int(entry["end_year"]),
                    properties=properties,
                )
            )
    return resolved


def _derive_property_order(
    simulations: list[Simulation],
    explicit: list[str] | None,
    split_data_type_items: bool,
) -> list[str]:
    if explicit:
        order = list(explicit)
    else:
        all_keys: set[str] = set()
        for sim in simulations:
            all_keys.update(sim.properties)
        order = [k for k in PREFERRED_PROPERTY_ORDER if k in all_keys]
        order += sorted(all_keys - set(order))
    if split_data_type_items and "data_type" not in order:
        order.append("data_type")
    return order


def load_app_config(
    app_dir: str | Path, simulations_file: str | Path | None = None
) -> AppConfig:
    app_dir = Path(app_dir).expanduser().resolve()
    cfg = _load_yaml(app_dir / "catalog_config.yaml")

    collection_id = str(cfg["id"])
    if "-" in collection_id:
        raise ValueError(
            f"Collection id '{collection_id}' contains a dash. "
            "DEDL collection ids permit only letters, dots and underscores."
        )

    sims_path = (
        Path(simulations_file).expanduser()
        if simulations_file
        else find_simulations_file(app_dir)
    )
    shared = _load_yaml(sims_path)

    overrides = cfg.get("overrides") or {}
    simulations = _resolve_simulations(cfg.get("simulations") or [], shared, overrides)
    if not simulations:
        raise ValueError(
            f"{app_dir / 'catalog_config.yaml'} must select at least one "
            "simulation under `simulations:`"
        )

    split = bool(cfg.get("split_data_type_items", False))
    property_order = _derive_property_order(
        simulations, cfg.get("property_order"), split
    )

    temporal_start = cfg.get("temporal_start") or (
        f"{min(s.start_year for s in simulations)}-01-01T00:00:00Z"
    )
    temporal_end = cfg.get("temporal_end") or (
        f"{max(s.end_year for s in simulations)}-12-31T23:00:00Z"
    )

    app_data_dir = Path(
        os.getenv("APP_DATA_DIR") or cfg.get("app_data_dir", ".")
    ).expanduser()
    catalog_home_dir = Path(
        os.getenv("CATALOG_HOME_DIR") or cfg.get("catalog_home_dir", ".")
    ).expanduser()
    if not catalog_home_dir.is_absolute():
        catalog_home_dir = (app_dir / catalog_home_dir).resolve()

    return AppConfig(
        id=collection_id,
        title=cfg.get("title", collection_id),
        description=cfg.get("description", ""),
        short_description=cfg.get("short_description", ""),
        license=cfg.get("license", "proprietary"),
        bbox=[float(v) for v in cfg.get("bbox", [-180, -90, 180, 90])],
        item_folder_level=cfg.get("item_folder_level", "YYYY"),
        app_data_dir=app_data_dir,
        catalog_home_dir=catalog_home_dir,
        simulations=simulations,
        property_order=property_order,
        temporal_start=temporal_start,
        temporal_end=temporal_end,
        keywords=cfg.get("keywords") or [],
        providers=cfg.get("providers") or [],
        thumbnail_url=cfg.get("thumbnail_url"),
        thumbnail_mime=cfg.get("thumbnail_mime", "image/png"),
        doi=cfg.get("doi"),
        license_url=cfg.get("license_url"),
        license_name=cfg.get("license_name"),
        related=cfg.get("related"),
        item_config_optional=bool(cfg.get("item_config_optional", True)),
        split_data_type_items=split,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_appconfig.py -v`
Expected: 12 passed.

- [ ] **Step 5: Commit**

```bash
git add stac_dedl_core/appconfig.py tests/test_appconfig.py
git commit -m "feat: add stac_dedl_core.appconfig — yaml loader with shared simulation resolution"
```

---

### Task 5: `stac_dedl_core/collection_builder.py`

**Files:**
- Create: `stac_dedl_core/collection_builder.py`
- Test: `tests/test_collection_builder.py`

- [ ] **Step 1: Write the failing tests**

```python
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
    assert "stac_extensions" not in coll


def test_refuses_overwrite_by_default(cfg):
    write_collection_files(cfg)
    with pytest.raises(FileExistsError):
        write_collection_files(cfg)
    write_collection_files(cfg, overwrite=True)  # explicit overwrite works
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_collection_builder.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'stac_dedl_core.collection_builder'`.

- [ ] **Step 3: Implement `stac_dedl_core/collection_builder.py`**

```python
"""Write metadata/collection.json + metadata/collection_config.json from an AppConfig.

Generalised from apps/hydroland/staging/hydroland_data_preparation.py so that
every app produces identical collection-level metadata structure.
"""
from __future__ import annotations

import json
from pathlib import Path

from stac_dedl_core.appconfig import AppConfig
from stac_dedl_core.config import STAC_VERSION

SCIENTIFIC_EXTENSION = "https://stac-extensions.github.io/scientific/v1.0.0/schema.json"


def build_collection_dict(cfg: AppConfig) -> dict:
    links = []
    if cfg.license_url:
        links.append(
            {
                "rel": "license",
                "href": cfg.license_url,
                "title": cfg.license_name or cfg.license,
            }
        )
    if cfg.doi:
        links.append(
            {
                "rel": "cite-as",
                "href": cfg.doi.get("url"),
                "title": cfg.doi.get("title"),
            }
        )
    if cfg.related:
        links.append(
            {
                "rel": "describedby",
                "href": cfg.related.get("url"),
                "title": cfg.related.get("title"),
            }
        )

    collection: dict = {
        "type": "Collection",
        "id": cfg.id,
        "stac_version": STAC_VERSION,
        "description": cfg.description,
        "links": links,
        "dedl:short_description": cfg.short_description,
        "title": cfg.title,
        "extent": {
            "spatial": {"bbox": [cfg.bbox]},
            "temporal": {"interval": [[cfg.temporal_start, cfg.temporal_end]]},
        },
        "license": cfg.license,
        "keywords": cfg.keywords,
        "providers": cfg.providers,
    }

    if cfg.doi:
        collection["stac_extensions"] = [SCIENTIFIC_EXTENSION]
        collection["sci:publications"] = [
            {
                "sci:doi": cfg.doi.get("code"),
                "sci:citation": cfg.doi.get("citation") or cfg.doi.get("title"),
            }
        ]

    if cfg.thumbnail_url:
        collection["assets"] = {
            "thumbnail": {
                "href": cfg.thumbnail_url,
                "type": cfg.thumbnail_mime,
                "title": "overview",
                "roles": ["thumbnail"],
            }
        }

    return collection


def build_collection_config_dict(cfg: AppConfig) -> dict:
    return {
        "id": cfg.id,
        "item_asset_ignore_list": ["item_config.json"],
        "item_config_optional": cfg.item_config_optional,
        "item_folder_level": cfg.item_folder_level,
        "thumbnail_regex": "^thumbnail",
        "overview_regex": "^overview",
        "additional_property_keys": cfg.property_order,
        "bbox": cfg.bbox,
    }


def _write_json(path: Path, payload: dict, overwrite: bool, indent: int) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"{path} already exists. Pass overwrite=True to replace.")
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=indent)
        f.write("\n")


def write_collection_files(
    cfg: AppConfig, overwrite: bool = False, indent: int = 2
) -> tuple[Path, Path]:
    """Create <collection>/data and <collection>/metadata, write both JSON files."""
    metadata_dir = cfg.collection_dir / "metadata"
    (cfg.collection_dir / "data").mkdir(parents=True, exist_ok=True)
    metadata_dir.mkdir(parents=True, exist_ok=True)

    collection_path = metadata_dir / "collection.json"
    config_path = metadata_dir / "collection_config.json"
    _write_json(collection_path, build_collection_dict(cfg), overwrite, indent)
    _write_json(config_path, build_collection_config_dict(cfg), overwrite, indent)
    return collection_path, config_path
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_collection_builder.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add stac_dedl_core/collection_builder.py tests/test_collection_builder.py
git commit -m "feat: add stac_dedl_core.collection_builder"
```

---

### Task 6: `stac_dedl_core/upload.py` — shared upload command

**Files:**
- Create: `stac_dedl_core/upload.py`
- Modify: `stac_dedl_core/__init__.py`
- Test: `tests/test_upload.py`

- [ ] **Step 1: Write the failing tests**

```python
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
    def __init__(self, existing=()):
        self.existing = set(existing)
        self.uploaded = []

    def head_object(self, Bucket, Key):
        if Key not in self.existing:
            raise ClientError({"Error": {"Code": "404"}}, "HeadObject")
        return {}

    def upload_file(self, Filename, Bucket, Key):
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
    assert stats == {"matched": 5, "uploaded": 0, "skipped_existing": 0}
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
    assert stats == {"matched": 5, "uploaded": 4, "skipped_existing": 1}

    client2 = FakeS3Client(existing=existing)
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_upload.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'stac_dedl_core.upload'`.

- [ ] **Step 3: Implement `stac_dedl_core/upload.py`**

```python
"""Shared upload of a staged collection tree to the DEDL S3 bucket.

Replaces the per-app s3cmd scripts and the IS_UPLOAD_S3 config toggle.
Dry run by default; uploads metadata/ first, then data/ in year/month order
so an interrupted transfer can resume with --year.

Usage:
    python -m stac_dedl_core.upload EO.UFZ.DAT.HYDROLAND \
        --root /path/to/EO.UFZ.DAT.HYDROLAND [--year 2015] [--execute]
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Iterator, Tuple

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from stac_dedl_core.config import (
    S3_ENDPOINT_URL,
    S3_USER_GENERATED_BUCKET_PREFIX,
)
from stac_dedl_core.usergenerated.env_utils import validate_aws_credentials

logger = logging.getLogger("stac-dedl-upload")


def get_default_bucket_name(collection_id: str) -> str:
    return f"{S3_USER_GENERATED_BUCKET_PREFIX}-{collection_id.lower()}"


def iter_upload_pairs(
    collection_root: Path, collection_id: str, year: str | None = None
) -> Iterator[Tuple[Path, str]]:
    """Yield (file_path, object_key): metadata/ first, then data/ by year/month."""

    def key_for(fp: Path) -> str:
        return f"{collection_id}/{fp.relative_to(collection_root).as_posix()}"

    metadata_dir = collection_root / "metadata"
    if metadata_dir.is_dir():
        for fp in sorted(p for p in metadata_dir.rglob("*") if p.is_file()):
            yield fp, key_for(fp)

    data_dir = collection_root / "data"
    if data_dir.is_dir():
        for year_dir in sorted(p for p in data_dir.iterdir() if p.is_dir()):
            if year is not None and year_dir.name != str(year):
                continue
            for fp in sorted(p for p in year_dir.rglob("*") if p.is_file()):
                yield fp, key_for(fp)


def _make_s3_client():
    aws_access_key_id, aws_secret_access_key = validate_aws_credentials()
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


def upload_collection(
    collection_id: str,
    collection_root: str | Path,
    bucket_name: str | None = None,
    year: str | None = None,
    overwrite: bool = False,
    execute: bool = False,
    s3_client=None,
) -> dict:
    collection_root = Path(collection_root).expanduser().resolve()
    if not collection_root.is_dir():
        raise FileNotFoundError(f"Collection root not found: {collection_root}")

    bucket = bucket_name or get_default_bucket_name(collection_id)
    pairs = list(iter_upload_pairs(collection_root, collection_id, year=year))
    stats = {"matched": len(pairs), "uploaded": 0, "skipped_existing": 0}

    if not execute:
        for fp, key in pairs[:5]:
            logger.info("[DRY RUN] %s -> s3://%s/%s", fp, bucket, key)
        logger.info(
            "[DRY RUN] %s file(s) would be uploaded to bucket '%s'. "
            "Re-run with --execute to upload.",
            len(pairs),
            bucket,
        )
        return stats

    if s3_client is None:
        s3_client = _make_s3_client()

    for fp, key in pairs:
        if not overwrite:
            try:
                s3_client.head_object(Bucket=bucket, Key=key)
                stats["skipped_existing"] += 1
                logger.info("Exists, skipping: %s", key)
                continue
            except ClientError as e:
                if e.response["Error"]["Code"] != "404":
                    raise
        s3_client.upload_file(str(fp), bucket, key)
        stats["uploaded"] += 1
        logger.info("Uploaded: s3://%s/%s", bucket, key)

    logger.info(
        "Done. matched=%s uploaded=%s skipped_existing=%s",
        stats["matched"],
        stats["uploaded"],
        stats["skipped_existing"],
    )
    return stats


def main(argv: list[str] | None = None) -> int:
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
    parser.add_argument("--year", help="Only upload data/<year>/ (metadata always included).")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Re-upload objects that already exist in the bucket.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually upload. Without this flag, dry run only.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
    root = Path(args.root) if args.root else Path.cwd() / args.collection_id
    upload_collection(
        args.collection_id,
        root,
        bucket_name=args.bucket,
        year=args.year,
        overwrite=args.overwrite,
        execute=args.execute,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Export the new API from `stac_dedl_core/__init__.py`**

Replace the whole file with:

```python
from stac_dedl_core.appconfig import AppConfig, Simulation, load_app_config
from stac_dedl_core.collection_builder import write_collection_files
from stac_dedl_core.generate_item_metadata import ItemGenerator
from stac_dedl_core.staging import (
    build_item_folder_name,
    format_catalog_property,
    join_item_folder_name,
    materialize_file,
    ordered_properties,
    safe_slug,
)
from stac_dedl_core.upload import get_default_bucket_name, upload_collection
from stac_dedl_core.usergenerated.s3tools import S3Tools

__all__ = [
    "AppConfig",
    "ItemGenerator",
    "S3Tools",
    "Simulation",
    "build_item_folder_name",
    "format_catalog_property",
    "get_default_bucket_name",
    "join_item_folder_name",
    "load_app_config",
    "materialize_file",
    "ordered_properties",
    "safe_slug",
    "upload_collection",
    "write_collection_files",
]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_upload.py -v && python -m pytest -q`
Expected: 8 passed for test_upload.py, full suite green.

- [ ] **Step 6: Commit**

```bash
git add stac_dedl_core/upload.py stac_dedl_core/__init__.py tests/test_upload.py
git commit -m "feat: add shared upload command (python -m stac_dedl_core.upload)"
```

---

### Task 7: HydroLand `catalog_config.yaml` + new `staging/stage.py`

**Files:**
- Create: `apps/hydroland/catalog_config.yaml`
- Create: `apps/hydroland/staging/stage.py`
- Test: `tests/test_hydroland_stage.py`

- [ ] **Step 1: Create `apps/hydroland/catalog_config.yaml`**

Values are taken verbatim from `staging/run_hydroland_data_preparation.sh`:

```yaml
# All HydroLand input lives here. Machine-specific paths can be overridden
# with the APP_DATA_DIR / CATALOG_HOME_DIR environment variables.

id: EO.UFZ.DAT.HYDROLAND
title: "Hydroland - Land Surface Hydrology Simulations. Second generation IFS-NEMO, IFS-FESOM and ICON Historical 1990-2014 run and projection 2015-2049 run."
description: "This catalog contains results from Hydroland produced with the Mesoscale Hydrologic Model (mHM). mHM outputs were further processed to provide user-oriented indicators, including Soil Moisture, Aridity Index, and Discharge Indicators. The dataset also includes the original mHM outputs and additional figures documenting model validation and selected results."
short_description: "Hydroland dataset derived from mHM model, providing several fluxes like river discharge or soil moisture as well as indicators: Soil Moisture, Aridity Index, and Discharge."

license: LGPL-3.0-or-later
license_url: https://www.gnu.org/licenses/lgpl-3.0.en.html
license_name: GNU Lesser General Public License v3.0

doi:
  url: https://doi.org/10.5281/zenodo.15584779
  code: 10.5281/zenodo.15584779
  title: "Hydroland output fluxes and indicators 1990–2049"
  citation: "Hydroland output fluxes and indicators 1990–2049. Destination Earth Climate DT & Helmholtz-Zentrum für Umweltforschung GmbH (UFZ). Zenodo. https://doi.org/10.5281/zenodo.15584779"

related:
  url: https://github.com/DestinE-Climate-DT/hydroland
  title: Hydroland on Github

keywords:
  - Climate Change
  - Hydrology
  - mHM
  - Mesoscale Hydrologic Model
  - Hydrologic modelling
  - Rainfall–runoff
  - Streamflow simulation
  - Discharge indicators
  - Soil Moisture
  - Evapotranspiration
  - Aridity Index
  - Water balance
  - Catchment hydrology
  - Europe
  - Destination Earth
  - DestinE
  - Climate Digital Twin
  - Climate DT

providers:
  - name: "Destination Earth Climate DT & Helmholtz-Zentrum für Umweltforschung GmbH (UFZ)"
    roles: [producer, processor, licensor]
    url: https://destination-earth.eu
  - name: "Destination Earth Data Lake (DEDL)"
    roles: [host]
    url: https://data.destination-earth.eu/

thumbnail_url: https://s3.central.data.destination-earth.eu/swift/v1/dedl-public/collections/eo-ufz-dat-ifs_nemo_hydroland.png
thumbnail_mime: image/png

bbox: [-180, -56, 180, 84]

item_folder_level: MM
item_config_optional: true
split_data_type_items: true

# HPC paths — override with env vars when running elsewhere
app_data_dir: /work/lealroja/ifs-nemo
catalog_home_dir: /work/lealroja/DestinE-DataLake-Lab/HDA/Usergenerated

simulations:
  - ifs-nemo_generation-2_historical
  - ifs-nemo_generation-2_projection
  - ifs-fesom_generation-2_historical
  - ifs-fesom_generation-2_projection
  - icon_generation-2_historical
  - icon_generation-2_projection
```

- [ ] **Step 2: Write the failing smoke test**

```python
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
    parsed_mrm = stage.parse_monthly_asset_filename(
        "1990_01_01_T00_00_to_1990_01_31_T23_00_mRM_Fluxes_States.nc"
    )
    assert parsed_mrm["data_type"] == "mrm"
    assert stage.parse_monthly_asset_filename("random.nc") is None


def test_create_catalog_folders(app_dir):
    stage = load_stage_module()
    cfg = load_app_config(app_dir)
    created = stage.create_catalog_folders(cfg, execute=True)
    assert len(created) == 1
    expected = (
        cfg.collection_dir / "data" / "1990" /
        "EO.UFZ.DAT.HYDROLAND_19900101T000000_20141231T230000"
        "__IFS-NEMO__hist__generation-2__baseline__realization-1"
    )
    assert created[0] == expected
    assert expected.is_dir()


def test_restructure_existing_data(app_dir):
    stage = load_stage_module()
    cfg = load_app_config(app_dir)
    # legacy year-level item folder with one monthly mHM file
    legacy = (
        cfg.collection_dir / "data" / "1990" /
        "EO.UFZ.DAT.HYDROLAND_19900101T000000_20141231T230000"
        "__IFS-NEMO__hist__generation-2__baseline__realization-1"
    )
    legacy.mkdir(parents=True)
    nc = legacy / "1990_01_01_T00_00_to_1990_01_31_T23_00_mHM_Fluxes_States.nc"
    nc.write_text("nc")

    stats = stage.restructure_existing_data(cfg, link_mode="symlink", execute=True)
    assert stats["recognized_files"] == 1
    assert stats["created_links"] == 1

    target = (
        cfg.collection_dir / "data" / "1990" / "01" /
        "EO.UFZ.DAT.HYDROLAND_19900101T000000_19900131T230000"
        "__IFS-NEMO__hist__generation-2__baseline__realization-1__mhm" /
        nc.name
    )
    assert target.is_symlink()
    assert target.read_text() == "nc"


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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_hydroland_stage.py -v`
Expected: FAIL — stage.py does not exist (`FileNotFoundError` from `spec_from_file_location`). `test_real_app_config_loads` should already PASS if Step 1 was done.

- [ ] **Step 4: Implement `apps/hydroland/staging/stage.py`**

```python
#!/usr/bin/env python3
"""HydroLand staging on top of stac_dedl_core.

Reads ../catalog_config.yaml, writes collection metadata, creates one
period-level catalog folder per simulation, and (with --restructure)
materialises monthly mHM/mRM NetCDF files into the data/YYYY/MM/<item>/
layout. Dry run by default; pass --execute to apply changes.

Only HydroLand-specific knowledge lives here: the mHM/mRM filename patterns
and the legacy year-level folder layout.
"""
from __future__ import annotations

import argparse
import logging
import re
from pathlib import Path

from stac_dedl_core.appconfig import AppConfig, load_app_config
from stac_dedl_core.collection_builder import write_collection_files
from stac_dedl_core.staging import (
    build_item_folder_name,
    join_item_folder_name,
    materialize_file,
    ordered_properties,
)

APP_DIR = Path(__file__).resolve().parents[1]

logger = logging.getLogger("hydroland-stage")

MHM_FILE_RE = re.compile(
    r"^(?P<start_year>\d{4})_(?P<start_month>\d{2})_(?P<start_day>\d{2})"
    r"_to_"
    r"(?P<end_year>\d{4})_(?P<end_month>\d{2})_(?P<end_day>\d{2})"
    r"_daily_mHM_Fluxes_States\.nc$"
)

MRM_FILE_RE = re.compile(
    r"^(?P<start_year>\d{4})_(?P<start_month>\d{2})_(?P<start_day>\d{2})"
    r"_T(?P<start_hour>\d{2})_(?P<start_minute>\d{2})"
    r"_to_"
    r"(?P<end_year>\d{4})_(?P<end_month>\d{2})_(?P<end_day>\d{2})"
    r"_T(?P<end_hour>\d{2})_(?P<end_minute>\d{2})"
    r"_mRM_Fluxes_States\.nc$"
)

MHM_WITH_TIME_RE = re.compile(
    r"^(?P<start_year>\d{4})_(?P<start_month>\d{2})_(?P<start_day>\d{2})"
    r"_T(?P<start_hour>\d{2})_(?P<start_minute>\d{2})"
    r"_to_"
    r"(?P<end_year>\d{4})_(?P<end_month>\d{2})_(?P<end_day>\d{2})"
    r"_T(?P<end_hour>\d{2})_(?P<end_minute>\d{2})"
    r"_mHM_Fluxes_States\.nc$"
)


def parse_monthly_asset_filename(file_name: str) -> dict[str, str] | None:
    """Parse one monthly mHM/mRM NetCDF filename into timestamps + data_type."""
    for pattern, data_type, has_time in (
        (MHM_WITH_TIME_RE, "mhm", True),
        (MHM_FILE_RE, "mhm", False),
        (MRM_FILE_RE, "mrm", True),
    ):
        match = pattern.match(file_name)
        if not match:
            continue
        p = match.groupdict()
        if has_time:
            start = (
                f"{p['start_year']}{p['start_month']}{p['start_day']}"
                f"T{p['start_hour']}{p['start_minute']}00"
            )
            end = (
                f"{p['end_year']}{p['end_month']}{p['end_day']}"
                f"T{p['end_hour']}{p['end_minute']}00"
            )
        else:
            start = f"{p['start_year']}{p['start_month']}{p['start_day']}T000000"
            end = f"{p['end_year']}{p['end_month']}{p['end_day']}T230000"
        return {
            "year": p["start_year"],
            "month": p["start_month"],
            "start_timestamp": start,
            "end_timestamp": end,
            "data_type": data_type,
        }
    return None


def create_catalog_folders(cfg: AppConfig, execute: bool = False) -> list[Path]:
    """Create data/<start_year>/<period item folder> for every simulation."""
    created: list[Path] = []
    base_order = [k for k in cfg.property_order if k != "data_type"]
    for sim in cfg.simulations:
        name = build_item_folder_name(
            cfg.id,
            f"{sim.start_year}0101T000000",
            f"{sim.end_year}1231T230000",
            ordered_properties(sim.properties, base_order),
        )
        target = cfg.collection_dir / "data" / str(sim.start_year) / name
        logger.info("%sCatalog folder: %s", "" if execute else "[DRY RUN] ", target)
        if execute:
            target.mkdir(parents=True, exist_ok=True)
        created.append(target)
    return created


def restructure_existing_data(
    cfg: AppConfig, link_mode: str = "symlink", execute: bool = False
) -> dict[str, int]:
    """Materialise monthly files from year-level item folders into YYYY/MM items."""
    data_dir = cfg.collection_dir / "data"
    stats = {
        "source_item_folders": 0,
        "recognized_files": 0,
        "created_links": 0,
        "skipped_existing": 0,
        "ignored_files": 0,
    }

    for year_dir in sorted(p for p in data_dir.iterdir() if p.is_dir()):
        for source_item_dir in sorted(p for p in year_dir.iterdir() if p.is_dir()):
            if not source_item_dir.name.startswith(f"{cfg.id}_"):
                continue
            stats["source_item_folders"] += 1
            suffix_parts = source_item_dir.name.split("__")[1:]

            for asset_path in sorted(p for p in source_item_dir.rglob("*") if p.is_file()):
                parsed = parse_monthly_asset_filename(asset_path.name)
                if not parsed:
                    stats["ignored_files"] += 1
                    continue
                stats["recognized_files"] += 1

                item_suffix = list(suffix_parts)
                if cfg.split_data_type_items:
                    item_suffix.append(parsed["data_type"])

                target = (
                    data_dir
                    / parsed["year"]
                    / parsed["month"]
                    / join_item_folder_name(
                        cfg.id,
                        parsed["start_timestamp"],
                        parsed["end_timestamp"],
                        item_suffix,
                    )
                    / asset_path.name
                )
                if materialize_file(asset_path, target, mode=link_mode, execute=execute):
                    stats["created_links"] += 1
                    logger.info(
                        "%s%s -> %s", "" if execute else "[DRY RUN] ", asset_path, target
                    )
                else:
                    stats["skipped_existing"] += 1
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Apply changes. Without this flag everything is a dry run.",
    )
    parser.add_argument(
        "--restructure",
        action="store_true",
        help="Materialise monthly files from legacy year-level item folders.",
    )
    parser.add_argument(
        "--link-mode",
        default="symlink",
        choices=["symlink", "hardlink", "copy", "move"],
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"],
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level), format="%(levelname)s | %(message)s"
    )

    cfg = load_app_config(APP_DIR)
    logger.info("Collection: %s (%s simulations)", cfg.id, len(cfg.simulations))

    if args.execute:
        collection_path, config_path = write_collection_files(cfg, overwrite=True)
        logger.info("Wrote %s and %s", collection_path, config_path)
    else:
        logger.info("[DRY RUN] Would write collection.json + collection_config.json")

    create_catalog_folders(cfg, execute=args.execute)

    if args.restructure:
        stats = restructure_existing_data(
            cfg, link_mode=args.link_mode, execute=args.execute
        )
        logger.info("Restructure summary: %s", stats)

    if not args.execute:
        logger.info("Dry run complete. Re-run with --execute to apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_hydroland_stage.py -v`
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add apps/hydroland/catalog_config.yaml apps/hydroland/staging/stage.py tests/test_hydroland_stage.py
git commit -m "feat(hydroland): catalog_config.yaml + stage.py on shared core"
```

---

### Task 8: HydroLand cleanup — pipeline, helper imports, legacy removal

**Files:**
- Modify: `apps/hydroland/run_pipeline.sh` (full rewrite)
- Modify: `apps/hydroland/staging/move_hydroland_monthly_data.py:26-30`
- Modify: `apps/hydroland/staging/scaffold_hydroland_projection.py:19`
- Modify: `apps/hydroland/staging/delete_s3_collection_prefix.py:18-20`
- Delete: `apps/hydroland/staging/hydroland_data_preparation.py`
- Delete: `apps/hydroland/staging/run_hydroland_data_preparation.sh`

- [ ] **Step 1: Rewrite `apps/hydroland/run_pipeline.sh`**

This becomes the standard pipeline shared by all apps (energy/hydromet/fwi will copy it verbatim in their migration plans):

```bash
#!/usr/bin/env bash
# Standard 3-step STAC pipeline: stage → generate → upload.
# All input lives in catalog_config.yaml; credentials in .env.
#
#   bash run_pipeline.sh                    # stage (dry run) — show the plan
#   bash run_pipeline.sh --execute          # stage + generate items
#   bash run_pipeline.sh --execute --upload # stage + generate + upload
#   bash run_pipeline.sh --execute --upload --year 2015
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
fi

EXECUTE=0
UPLOAD=0
YEAR=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --execute) EXECUTE=1 ;;
    --upload)  UPLOAD=1 ;;
    --year)    YEAR="$2"; shift ;;
    *) echo "Unknown argument: $1" >&2; exit 1 ;;
  esac
  shift
done

COLLECTION_ID="$(python -c "import yaml; print(yaml.safe_load(open('catalog_config.yaml'))['id'])")"
CATALOG_HOME_DIR="${CATALOG_HOME_DIR:-$(python -c "import yaml; print(yaml.safe_load(open('catalog_config.yaml'))['catalog_home_dir'])")}"

echo "=== Step 1: Stage (${COLLECTION_ID}) ==="
STAGE_ARGS=(--restructure)
[ "${EXECUTE}" -eq 1 ] && STAGE_ARGS+=(--execute)
python staging/stage.py "${STAGE_ARGS[@]}"

if [ "${EXECUTE}" -eq 1 ]; then
  echo "=== Step 2: Generate STAC item metadata ==="
  (cd "${CATALOG_HOME_DIR}" && python -c "
from stac_dedl_core import ItemGenerator
ItemGenerator('${COLLECTION_ID}').run()
")
fi

if [ "${UPLOAD}" -eq 1 ]; then
  echo "=== Step 3: Upload to DEDL S3 ==="
  UPLOAD_ARGS=("${COLLECTION_ID}" --root "${CATALOG_HOME_DIR}/${COLLECTION_ID}" --execute)
  [ -n "${YEAR}" ] && UPLOAD_ARGS+=(--year "${YEAR}")
  python -m stac_dedl_core.upload "${UPLOAD_ARGS[@]}"
fi

echo "=== Pipeline complete ==="
```

- [ ] **Step 2: Update `move_hydroland_monthly_data.py` imports**

Replace lines 26–30:

```python
from hydroland_data_preparation import (
    build_month_item_folder_name,
    format_catalog_property,
    parse_monthly_asset_filename,
)
```

with:

```python
from stac_dedl_core.staging import (
    format_catalog_property,
    join_item_folder_name as build_month_item_folder_name,
)
from stage import parse_monthly_asset_filename
```

(The alias keeps the rest of the script unchanged — `build_month_item_folder_name(collection_id, start, end, suffix_parts)` has the same signature as `join_item_folder_name`.)

- [ ] **Step 3: Update `scaffold_hydroland_projection.py` import**

Replace line 19:

```python
from hydroland_data_preparation import build_month_item_folder_name
```

with:

```python
from stac_dedl_core.staging import join_item_folder_name as build_month_item_folder_name
```

- [ ] **Step 4: Update `delete_s3_collection_prefix.py` imports**

Replace lines 18–20:

```python
from config import S3_ENDPOINT_URL
from generate_item_metadata import get_default_bucket_name
from usergenerated.env_utils import validate_aws_credentials
```

with:

```python
from stac_dedl_core.config import S3_ENDPOINT_URL
from stac_dedl_core.upload import get_default_bucket_name
from stac_dedl_core.usergenerated.env_utils import validate_aws_credentials
```

- [ ] **Step 5: Delete the legacy files**

```bash
git rm apps/hydroland/staging/hydroland_data_preparation.py
git rm apps/hydroland/staging/run_hydroland_data_preparation.sh
```

- [ ] **Step 6: Verify everything still imports and the suite is green**

Run:
```bash
python -m pytest -q
python -c "import ast, pathlib; [ast.parse(p.read_text()) for p in pathlib.Path('apps/hydroland/staging').glob('*.py')]; print('hydroland staging scripts parse OK')"
bash -n apps/hydroland/run_pipeline.sh && echo "run_pipeline.sh syntax OK"
```
Expected: full suite green; both OK lines printed.

- [ ] **Step 7: Commit**

```bash
git add -A apps/hydroland
git commit -m "refactor(hydroland): standard run_pipeline.sh, shared-core imports, drop legacy prep script"
```

---

### Task 9: Documentation updates

**Files:**
- Modify: `apps/hydroland/README.md`
- Modify: `apps/APPS_OVERVIEW.md`

- [ ] **Step 1: Update `apps/hydroland/README.md`**

Replace the **Files** table and **Pipeline** section to match the new layout:

```markdown
## Files

| File | Purpose |
|---|---|
| `catalog_config.yaml` | ALL HydroLand input: collection metadata, paths, simulation keys |
| `staging/stage.py` | Stages data: writes collection files, creates catalog folders, restructures monthly files (uses `stac_dedl_core`) |
| `staging/move_hydroland_monthly_data.py` | Moves monthly NetCDF files into the STAC-ready `YYYY/MM/item/` layout |
| `staging/scaffold_hydroland_projection.py` | Scaffolds the projection data folder structure |
| `staging/delete_s3_collection_prefix.py` | Utility to delete a collection prefix from the S3 bucket |

## Pipeline

```bash
# 1. Set up credentials
cp .env.example .env       # add AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY

# 2. Check catalog_config.yaml (paths can be overridden with
#    APP_DATA_DIR / CATALOG_HOME_DIR env vars)

# 3. Run
bash run_pipeline.sh                    # dry run — shows the staging plan
bash run_pipeline.sh --execute          # stage + generate items
bash run_pipeline.sh --execute --upload # + upload to DEDL S3
```
```

Also update the **What the scripts do** section: remove the entries for
`hydroland_data_preparation.py` and `run_hydroland_data_preparation.sh`, and add:

```markdown
**`stage.py`** — loads `catalog_config.yaml` via `stac_dedl_core.load_app_config`
(simulation keys resolved against `apps/_shared/simulations.yaml`), writes
`metadata/collection.json` + `collection_config.json`, creates one period-level
catalog folder per simulation, and with `--restructure` materialises monthly
mHM/mRM files into `data/YYYY/MM/<item>/` (symlink/hardlink/copy/move via
`--link-mode`). Dry run by default; `--execute` applies.
```

- [ ] **Step 2: Update `apps/APPS_OVERVIEW.md`**

Add at the top, right after the intro pipeline diagram:

```markdown
> **Status (2026-06-11):** the shared foundation from the unification design
> (`docs/superpowers/specs/2026-06-11-shared-staging-upload-design.md`) is
> implemented: `apps/_shared/simulations.yaml`, `stac_dedl_core.{appconfig,
> staging,collection_builder,upload}`, and HydroLand has been migrated.
> Energy Indicators, HydroMet, and FWI still use their legacy staging and are
> covered by follow-up migration plans.
```

- [ ] **Step 3: Final verification + commit**

Run: `python -m pytest -q`
Expected: full suite green.

```bash
git add apps/hydroland/README.md apps/APPS_OVERVIEW.md
git commit -m "docs: update hydroland README + apps overview for shared foundation"
```

---

## Out of scope (follow-up plans)

Per the spec's migration order, these are separate plans once this foundation lands:

1. **energy_indicators migration** — `stage.py` rewrite, delete s3cmd script (incl. the `.py`→`.sh` typo), `catalog_config.yaml`.
2. **hydromet migration** — rewrite (kills the committed syntax errors), keep `parameters.json` datacube hook (requires a small `extra_collection_fields` extension to `collection_builder` at that point).
3. **fwi migration** — `read_nc_properties` flags merged into core `ItemGenerator`, fork deletion, collection-id TODO comment.
