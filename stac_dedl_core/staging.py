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
# Note: the `startswith(f"{prefix}-")` idempotency guard is prefix-value-specific.
# For example, simulation_id="identifier-42" would still gain the "id-" prefix
# (producing "id-identifier-42") because "identifier-42" does not start with "id-".
_PROPERTY_PREFIXES = {
    "generation": "generation",
    "realization": "realization",
    "simulation_id": "id",
}


def safe_slug(value: Any) -> str:
    """Sanitize a value for use in filesystem/item names."""
    if value is None:
        return "NA"
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
    """Return properties reordered by `order`, dropping keys not present.

    Keys present in `properties` but absent from `order` are also excluded.
    """
    return {k: properties[k] for k in order if k in properties}


def classify_data_type(
    path: "str | Path",
    rules: Iterable[Mapping[str, Any]],
    default: Any = None,
) -> Any:
    """Return the data_type for an asset path using config-driven rules.

    Each rule is a mapping with a ``match`` substring and a ``data_type`` value.
    The first rule whose ``match`` appears in ``str(path)`` wins; if none match,
    ``default`` is returned. This is how an app declares extra item dimensions
    (e.g. river_discharge / soil_moisture indicators) purely from config, without
    touching Python. Matching is a plain case-sensitive substring test against the
    asset's (relative) path, so it works for both filename tokens and subfolders.
    """
    text = str(path)
    for rule in rules or ():
        if str(rule.get("match", "")) in text:
            return rule.get("data_type", default)
    return default


def materialize_file(
    source: Path, target: Path, mode: str = "symlink", execute: bool = False
) -> bool:
    """Create `target` from `source` via the given mode.

    Returns True if the target was (or would be, in dry run) created,
    False if it already exists (including dangling symlinks). Dry run
    (execute=False) touches nothing and does not check whether `source` exists.

    Mode notes:
    - ``"move"`` uses ``shutil.move``, which falls back to copy+delete when
      source and target are on different filesystems (not an atomic rename).
    """
    if mode not in MATERIALIZE_MODES:
        raise ValueError(
            f"Unsupported materialize mode '{mode}'. Expected one of {MATERIALIZE_MODES}"
        )

    if target.exists() or target.is_symlink():
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
        shutil.move(source, target)
    return True
