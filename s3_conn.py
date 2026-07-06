"""S3-CONN: object storage bucket connector (env-configured, optional boto3)."""



from __future__ import annotations



import json

import os

from typing import Any





def _config() -> dict[str, str]:

    return {

        "endpoint": os.environ.get("AUDIOTHECA_S3_ENDPOINT", ""),

        "bucket": os.environ.get("AUDIOTHECA_S3_BUCKET", ""),

        "region": os.environ.get("AUDIOTHECA_S3_REGION", "us-east-1"),

        "prefix": os.environ.get("AUDIOTHECA_S3_PREFIX", ""),

    }





def connect_bucket(*, endpoint: str | None = None, bucket: str | None = None) -> dict[str, Any]:

    cfg = _config()

    endpoint = endpoint or cfg["endpoint"]

    bucket = bucket or cfg["bucket"]

    if not endpoint or not bucket:

        return {

            "endpoint": endpoint,

            "bucket": bucket,

            "connected": False,

            "objects_indexed": 0,

            "mode": "unconfigured",

            "hint": "Set AUDIOTHECA_S3_ENDPOINT and AUDIOTHECA_S3_BUCKET",

        }



    try:

        import boto3  # type: ignore[import-untyped]

    except ImportError:

        return {

            "endpoint": endpoint,

            "bucket": bucket,

            "connected": False,

            "objects_indexed": 0,

            "mode": "boto3_missing",

        }



    client = boto3.client("s3", endpoint_url=endpoint, region_name=cfg["region"])

    prefix = cfg["prefix"]

    response = client.list_objects_v2(Bucket=bucket, Prefix=prefix, MaxKeys=100)

    contents = response.get("Contents") or []

    keys = [item["Key"] for item in contents if item.get("Key")]

    return {

        "endpoint": endpoint,

        "bucket": bucket,

        "connected": True,

        "objects_indexed": len(keys),

        "sample_keys": keys[:20],

        "mode": "boto3",

    }





def save_index(keys: list[str], *, output: str) -> dict[str, Any]:

    from pathlib import Path



    target = Path(output)

    target.parent.mkdir(parents=True, exist_ok=True)

    target.write_text(json.dumps({"keys": keys}, indent=2), encoding="utf-8")

    return {"output": str(target), "count": len(keys), "ok": True}


def s3_status() -> dict[str, Any]:
    """Report S3 connector configuration without listing objects."""
    cfg = _config()
    configured = bool(cfg["endpoint"] and cfg["bucket"])
    try:
        import boto3  # type: ignore[import-untyped]

        boto3_available = True
    except ImportError:
        boto3_available = False
    return {
        "endpoint": cfg["endpoint"],
        "bucket": cfg["bucket"],
        "region": cfg["region"],
        "prefix": cfg["prefix"],
        "configured": configured,
        "boto3_available": boto3_available,
        "mode": "boto3" if configured and boto3_available else ("unconfigured" if not configured else "boto3_missing"),
    }

