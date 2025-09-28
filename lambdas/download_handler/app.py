"""Lambda handler that returns pre-signed download URLs for generated resumes."""
from __future__ import annotations

import json
import os
from typing import Any, Dict

import boto3

s3 = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")

BUCKET_NAME = os.environ["BUCKET_NAME"]
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
    job = table.get_item(Key={"pk": f"TENANT#{tenant_id}", "sk": f"JOB#{job_id}"}).get("Item")
    if not job:
        return _response(404, {"message": "Job not found"})

    docx_key = job.get("docxKey")
    pdf_key = job.get("pdfKey")
    if not docx_key and not pdf_key:
        return _response(409, {"message": "Job is not ready for download"})

    urls = {}
    if docx_key:
        urls["docxUrl"] = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": BUCKET_NAME, "Key": docx_key},
            ExpiresIn=3600,
        )
    if pdf_key:
        urls["pdfUrl"] = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": BUCKET_NAME, "Key": pdf_key},
            ExpiresIn=3600,
        )

    return _response(200, {"jobId": job_id, **urls})
