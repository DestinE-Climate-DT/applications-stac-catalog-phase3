"""Shared `update.py` logic: generate STAC item metadata for a staged collection.

Used by every app's `staging/update.py` (a thin wrapper that just calls
`main(app_dir)`). Runs `ItemGenerator`, which writes a STAC item JSON for
every folder under `data/` — including empty skeleton folders that have no
asset yet (those get `assets: {}`). Empty-asset item JSONs are removed
afterwards, so the published catalog only lists items that actually have data.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from stac_dedl_core import ItemGenerator
from stac_dedl_core.appconfig import load_app_config
from stac_dedl_core.staging import setup_logging


def remove_empty_items(items_dir: Path) -> int:
    """Delete generated item JSONs whose folder had no asset. Returns count removed."""
    if not items_dir.is_dir():
        return 0
    removed = 0
    for item_path in items_dir.glob("*.json"):
        with item_path.open(encoding="utf-8") as fh:
            payload = json.load(fh)
        if not payload.get("assets"):
            item_path.unlink()
            removed += 1
    return removed


def main(app_dir: Path, log_level: str = "INFO") -> int:
    cfg = load_app_config(app_dir)
    logger = setup_logging(f"{cfg.id}-update", log_level)
    logger.info("Generating STAC item metadata for %s", cfg.id)

    # ItemGenerator resolves paths relative to the current working directory.
    os.chdir(cfg.catalog_home_dir)
    ItemGenerator(cfg.id).run()

    items_dir = cfg.collection_dir / "metadata" / "items"
    removed = remove_empty_items(items_dir)
    n_items = len(list(items_dir.glob("*.json"))) if items_dir.is_dir() else 0
    logger.info(
        "Done. %s item JSON(s) with data in %s (%s empty items removed)",
        n_items, items_dir, removed,
    )
    return 0


def run_cli(app_dir: Path) -> int:
    """Entry point for an app's `staging/update.py` wrapper script."""
    parser = argparse.ArgumentParser(
        description="Generate STAC item metadata for the staged collection."
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"],
    )
    args = parser.parse_args()
    return main(app_dir, args.log_level)
