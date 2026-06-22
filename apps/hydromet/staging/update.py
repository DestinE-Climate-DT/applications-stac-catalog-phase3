#!/usr/bin/env python3
"""Generate STAC item metadata for the staged HydroMet collection.

See stac_dedl_core/update.py for the shared implementation.
"""
from pathlib import Path

from stac_dedl_core.update import run_cli

if __name__ == "__main__":
    raise SystemExit(run_cli(Path(__file__).resolve().parents[1]))
