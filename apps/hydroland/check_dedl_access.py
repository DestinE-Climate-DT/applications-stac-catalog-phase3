#!/usr/bin/env python3
"""Quick DEDL S3 connectivity check for HydroLand. Read-only, writes nothing.

Usage:
    python apps/hydroland/check_dedl_access.py
"""
import os
import sys
from pathlib import Path

import boto3
from botocore.client import Config
from dotenv import load_dotenv

APP_DIR = Path(__file__).resolve().parent
BUCKET = "usergenerated-proposal-eo.ufz.dat.ifs-nemo-hydroland"
PREFIX = "EO.UFZ.DAT.HYDROLAND"
ENDPOINT = "https://s3.central.data.destination-earth.eu"

# .env first, then .env.example as a fallback
for candidate in (APP_DIR / ".env", APP_DIR / ".env.example"):
    if candidate.is_file():
        load_dotenv(candidate)
        print(f"credentials from : {candidate.name}")
        break

key = os.getenv("AWS_ACCESS_KEY_ID")
secret = os.getenv("AWS_SECRET_ACCESS_KEY")
if not key or not secret:
    sys.exit("No AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY found.")
print(f"access key id    : {key[:4]}...{key[-4:]}  (len {len(key)})")
print(f"endpoint         : {ENDPOINT}")
print(f"bucket           : {BUCKET}\n")

s3 = boto3.client(
    "s3",
    endpoint_url=ENDPOINT,
    aws_access_key_id=key,
    aws_secret_access_key=secret,
    config=Config(signature_version="s3v4", retries={"max_attempts": 2}),
)

failures = 0


def check(label, fn):
    global failures
    try:
        print(f"[ ok ] {label}: {fn()}")
    except Exception as e:
        failures += 1
        code = getattr(e, "response", {}).get("Error", {}).get("Code", type(e).__name__)
        print(f"[FAIL] {label}: {code}")


check("list objects", lambda: f"{s3.list_objects_v2(Bucket=BUCKET, MaxKeys=1).get('KeyCount', 0)} key(s) visible")
check("read collection.json",
      lambda: f"{len(s3.get_object(Bucket=BUCKET, Key=f'{PREFIX}/metadata/collection.json')['Body'].read())} bytes")
check("head an item",
      lambda: f"{s3.head_object(Bucket=BUCKET, Key=f'{PREFIX}/metadata/collection_config.json')['ContentLength']} bytes")

print()
if failures:
    print(f"{failures}/3 checks failed — credentials or permissions are the problem, "
          "not the pipeline. Worth raising with DEDL support (ticket DSD-1812).")
    sys.exit(1)
print("All read checks passed. Note: write (PutObject) access is NOT tested here.")
