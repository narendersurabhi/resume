"""Lambda handler for generating presigned URLs for downloads."""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from typing import Any, Dict

import boto3

s3 = boto3.client("s3")

BUCKET_NAME = os.environ["BUCKET_NAME"]

frontend_domain = "https://dbeuad68389xx.cloudfront.net"  # put your CF URL here

CORS_HEADERS = {
    "Access-Control-Allow-Origin": frontend_domain,          # or your CF domain
    "Access-Control-Allow-Headers": "*",
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
}

def _response(status: int, body: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "statusCode": status,
        "headers": CORS_HEADERS, #{"Content-Type": "application/json"},
        "body": json.dumps(body),
    }


def handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    """Return pre-signed URLs for generated resume documents."""
    params = event.get("queryStringParameters") or {}
    key = params.get("key")
    if not key:
        return _response(400, {"message": "Missing required 'key' parameter"})

    expires_in = int(params.get("expiresIn", 3600))
    try:
        url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": BUCKET_NAME, "Key": key},
            ExpiresIn=expires_in,
        )
    except Exception as exc:  # noqa: BLE001
        return _response(500, {"message": f"Failed to generate URL: {exc}"})

    return _response(200, {"url": url, "expiresAt": (datetime.utcnow() + timedelta(seconds=expires_in)).isoformat() + "Z"})
