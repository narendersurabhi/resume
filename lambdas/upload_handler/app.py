"""Lambda to ingest files and persist metadata for resumes, job descriptions, and templates."""
from __future__ import annotations

import base64
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

import boto3

s3 = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")

BUCKET_NAME = os.environ["BUCKET_NAME"]
TABLE_NAME = os.environ["TABLE_NAME"]

CATEGORY_BY_RESOURCE = {
    "/uploadResume": "approved",
    "/uploadTemplate": "template",
    "/uploadJD": "jobs",
}


def _response(status: int, body: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body),
    }


def handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    try:
        body = json.loads(event.get("body") or "{}")
        tenant_id = body["tenantId"]
        file_name = body["fileName"]
        payload_b64 = body["content"]
        tags = body.get("tags", {})
    except (json.JSONDecodeError, KeyError) as exc:
        return _response(400, {"message": f"Invalid request payload: {exc}"})

    category = CATEGORY_BY_RESOURCE.get(event.get("resource")) or body.get("category") or "approved"
    object_key = f"{tenant_id}/{category}/{uuid.uuid4()}-{file_name}"

    try:
        binary = base64.b64decode(payload_b64)
    except Exception as exc:  # noqa: BLE001 - return descriptive error to caller
        return _response(400, {"message": f"Unable to decode file content: {exc}"})

    s3.put_object(
        Bucket=BUCKET_NAME,
        Key=object_key,
        Body=binary,
        Metadata={"tenantId": tenant_id, **{str(k): str(v) for k, v in tags.items()}},
    )

    table = dynamodb.Table(TABLE_NAME)
    table.put_item(
        Item={
            "pk": f"TENANT#{tenant_id}",
            "sk": f"ASSET#{category.upper()}#{uuid.uuid4()}",
            "tenantId": tenant_id,
            "category": category,
            "fileName": file_name,
            "objectKey": object_key,
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "tags": tags,
        }
    )

    return _response(200, {"message": "Upload successful", "key": object_key, "category": category})
