import os
import boto3
from botocore.client import Config
from dotenv import load_dotenv

load_dotenv()


def should_fetch_real_file(key: str) -> bool:
    parts = key.split("/")
    return key.endswith("item_config.json") or "metadata" in parts


def mirror_s3_structure(
    bucket_name: str,
    endpoint_url: str | None = None,
    region_name: str | None = None,
    aws_access_key_id: str | None = None,
    aws_secret_access_key: str | None = None,
    local_root: str = "structure",
):
    """
    Mirror the structure of an S3 bucket locally, downloading only specific files.

    Downloads item_config.json files and files under 'metadata' directories;
    creates empty placeholder files for everything else. Useful for regenerating
    metadata without downloading all data.
    """
    s3 = boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        region_name=region_name,
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        config=Config(signature_version="s3v4"),
    )

    paginator = s3.get_paginator("list_objects_v2")
    os.makedirs(local_root, exist_ok=True)

    for page in paginator.paginate(Bucket=bucket_name):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            local_path = os.path.join(local_root, key)

            if key.endswith("/"):
                os.makedirs(local_path, exist_ok=True)
                continue

            parent_dir = os.path.dirname(local_path)
            if parent_dir:
                os.makedirs(parent_dir, exist_ok=True)

            if should_fetch_real_file(key):
                if not os.path.exists(local_path):
                    s3.download_file(bucket_name, key, local_path)
            else:
                if not os.path.exists(local_path):
                    open(local_path, "a").close()


def main():
    print("Starting S3 structure mirroring...")

    endpoint_url: str = "https://s3.central.data.destination-earth.eu"
    access_key: str | None = os.getenv("AWS_ACCESS_KEY_ID")
    secret_key: str | None = os.getenv("AWS_SECRET_ACCESS_KEY")

    # Edit these for your collection
    bucket = "usergenerated-proposal-eo.xxx.yyy.zzz"
    output = "EO.XXX.YYY.ZZZ"

    if not access_key or not secret_key:
        raise RuntimeError(
            "AWS credentials not found.\n"
            "Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY in .env or environment variables."
        )

    mirror_s3_structure(
        bucket_name=bucket,
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        local_root=output,
    )

    print("Finished S3 structure mirroring.")


if __name__ == "__main__":
    main()
