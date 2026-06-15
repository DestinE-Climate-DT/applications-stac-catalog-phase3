"""Load an app's catalog_config.yaml and resolve shared simulation definitions.

The single entry point is load_app_config(app_dir). It reads:
- <app_dir>/catalog_config.yaml          (all per-app input)
- apps/_shared/simulations.yaml          (shared run definitions; path can be
                                          overridden via $SIMULATIONS_FILE or
                                          the simulations_file argument;
                                          the simulations_file argument takes
                                          precedence over $SIMULATIONS_FILE)
and returns a fully resolved AppConfig.
"""
from __future__ import annotations

import copy
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


def _json_number(value) -> int | float:
    """Coerce a numeric value to int if it is whole, otherwise float.

    Mirrors hydroland's json_number so that bbox coordinates such as -180
    serialise as -180 (not -180.0) in JSON output.
    """
    numeric = float(value)
    return int(numeric) if numeric.is_integer() else numeric


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
    # Optional: staging of period-level "indicator" products that don't follow the
    # monthly layout (HydroLand floods/droughts/soil-moisture indicators). A mapping
    # with: source_dir, reference_simulation, scenario_simulation, scenario_markers.
    # See apps/hydroland/staging/stage.py:stage_indicators.
    indicators: dict | None = None
    # Optional, config-driven classification of an asset into a data_type token
    # (e.g. mhm / mrm / river_discharge_indicators). Each rule is a mapping with
    # a "match" substring (tested against the asset's relative path) and the
    # "data_type" to assign. First match wins; see staging.classify_data_type.
    # Any app can use this; it only takes effect when split_data_type_items is true.
    data_type_rules: list = field(default_factory=list)

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
        for required in ("start_year", "end_year"):
            if required not in entry:
                raise KeyError(
                    f"Simulation '{key}' is missing required field '{required}'"
                )
        realizations = entry.get("realization", 1)
        if not isinstance(realizations, list):
            realizations = [realizations]
        for realization in realizations:
            properties = {
                k: copy.deepcopy(v)
                for k, v in entry.items()
                if k not in RESERVED_SIMULATION_KEYS
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

    if "id" not in cfg:
        raise KeyError(
            f"{app_dir / 'catalog_config.yaml'} is missing required field 'id'"
        )
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

    data_type_rules = cfg.get("data_type_rules") or []
    for rule in data_type_rules:
        if not isinstance(rule, dict) or "match" not in rule or "data_type" not in rule:
            raise ValueError(
                "Each data_type_rules entry must be a mapping with 'match' and "
                f"'data_type' keys. Got: {rule!r}"
            )

    temporal_start = cfg.get("temporal_start") or (
        f"{min(s.start_year for s in simulations)}-01-01T00:00:00Z"
    )
    # Data is hourly; the last timestep is at 23:00, matching published hydroland item timestamps.
    temporal_end = cfg.get("temporal_end") or (
        f"{max(s.end_year for s in simulations)}-12-31T23:00:00Z"
    )

    app_data_dir = Path(
        os.getenv("APP_DATA_DIR") or cfg.get("app_data_dir", ".")
    ).expanduser()
    if not app_data_dir.is_absolute():
        app_data_dir = (app_dir / app_data_dir).resolve()
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
        bbox=[_json_number(v) for v in cfg.get("bbox", [-180, -90, 180, 90])],
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
        data_type_rules=data_type_rules,
        indicators=cfg.get("indicators"),
    )
