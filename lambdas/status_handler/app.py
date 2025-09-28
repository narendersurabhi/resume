"""Lambda handler providing job execution status and validation metadata."""
from __future__ import annotations

import json
import os
from typing import Any, Dict

import boto3

dynamodb = boto3.resource("dynamodb")

TABLE_NAME = os.environ["TABLE_NAME"]


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
    path_params = event.get("pathParameters") or {}
    query_params = event.get("queryStringParameters") or {}
    job_id = path_params.get("jobId")
    tenant_id = query_params.get("tenantId")

    if not job_id or not tenant_id:
        return _response(400, {"message": "Both tenantId and jobId are required"})

    table = dynamodb.Table(TABLE_NAME)
    item = table.get_item(Key={"pk": f"TENANT#{tenant_id}", "sk": f"JOB#{job_id}"}).get("Item")
    if not item:
        return _response(404, {"message": "Job not found"})

    return _response(
        200,
        {
            "jobId": job_id,
            "status": item.get("status", "UNKNOWN"),
            "createdAt": item.get("createdAt"),
            "completedAt": item.get("completedAt"),
            "validationReport": item.get("validationReport"),
            "docxKey": item.get("docxKey"),
            "pdfKey": item.get("pdfKey"),
            "error": item.get("error"),
        },
    )
