"""Lambda handler for uploading resumes, templates, and job descriptions."""
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


def _response(status: int, body: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }


def handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    """Persist uploaded file in S3 and metadata in DynamoDB."""
    try:
        payload = json.loads(event.get("body") or "{}")
        tenant_id = payload["tenantId"]
        file_category = payload.get("category", "approved")
        file_name = payload["fileName"]
        content_b64 = payload["content"]
        tags = payload.get("tags", {})
    except (json.JSONDecodeError, KeyError) as exc:
        return _response(400, {"message": f"Invalid request: {exc}"})

    content = base64.b64decode(content_b64)
    object_key = f"{tenant_id}/{file_category}/{uuid.uuid4()}-{file_name}"

    s3.put_object(
        Bucket=BUCKET_NAME,
        Key=object_key,
        Body=content,
        Metadata={"tenantId": tenant_id, **{str(k): str(v) for k, v in tags.items()}},
    )

    table = dynamodb.Table(TABLE_NAME)
    item = {
        "tenantId": tenant_id,
        "resourceId": object_key,
        "category": file_category,
        "fileName": file_name,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "tags": tags,
    }
    table.put_item(Item=item)

    return _response(200, {"message": "Upload successful", "key": object_key})
