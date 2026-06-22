#!/usr/bin/env python3
"""Delete all objects under EO.DWD.STAT.HYDROMET_EXTREMES's prefix in the S3 bucket.

See stac_dedl_core/s3_cleanup.py for the shared implementation. Dry run by
default; pass --execute to actually delete.
"""
from stac_dedl_core.s3_cleanup import run_cli

if __name__ == "__main__":
    raise SystemExit(run_cli("EO.DWD.STAT.HYDROMET_EXTREMES"))
