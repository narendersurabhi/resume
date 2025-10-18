"""Lambda handler for generating presigned URLs for downloads."""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from typing import Any, Dict

import boto3

s3 = boto3.client("s3")

BUCKET_NAME = os.environ["BUCKET_NAME"]
JOBS_BUCKET = os.getenv("JOBS_BUCKET", "")
CF_DIST_ID = os.getenv("CF_DIST_ID")
origin = os.getenv("FRONTEND_ORIGIN", "*")

def _cors_headers(origin="*"):
    return {
        "Access-Control-Allow-Origin": origin,   # use your exact CF origin in prod
        "Access-Control-Allow-Headers": "*",
        "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
    }

def _response(status: int, body: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "statusCode": status,
        "headers": _cors_headers(origin), #{"Content-Type": "application/json"},
        "body": json.dumps(body),
    }


def handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    """Return pre-signed URLs for generated resume documents."""
    params = event.get("queryStringParameters") or {}
    key = params.get("key")
    if not key:
        return _response(400, {"message": "Missing required 'key' parameter"})

    expires_in = int(params.get("expiresIn", 3600))
    # Choose bucket: use jobs bucket for job artifacts, otherwise default uploads bucket
    bucket = BUCKET_NAME
    if key.startswith("resume-jobs/") and JOBS_BUCKET:
        bucket = JOBS_BUCKET

    try:
        url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=expires_in,
        )
    except Exception as exc:  # noqa: BLE001
        return _response(500, {"message": f"Failed to generate URL: {exc}"})

    return _response(200, {"url": url, "expiresAt": (datetime.utcnow() + timedelta(seconds=expires_in)).isoformat() + "Z"})
