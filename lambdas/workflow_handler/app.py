"""Lambda to start the resume tailoring Step Functions workflow."""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

import boto3

sfn = boto3.client("stepfunctions")
s3 = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")

BUCKET_NAME = os.environ["BUCKET_NAME"]
TABLE_NAME = os.environ["TABLE_NAME"]
STATE_MACHINE_ARN = os.environ["STATE_MACHINE_ARN"]


def _response(status: int, body: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body),
    }


def _load_job_description(key: str | None) -> str | None:
    if not key:
        return None
    obj = s3.get_object(Bucket=BUCKET_NAME, Key=key)
    return obj["Body"].read().decode("utf-8")


def handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    try:
        body = json.loads(event.get("body") or "{}")
        tenant_id = body["tenantId"]
        resume_key = body["resumeKey"]
        job_description_key = body.get("jobDescriptionKey")
        job_description_text = body.get("jobDescription")
        template_key = body.get("templateKey")
        options = body.get("options", {})
    except (json.JSONDecodeError, KeyError) as exc:
        return _response(400, {"message": f"Invalid request body: {exc}"})

    job_id = body.get("jobId") or str(uuid.uuid4())

    if not job_description_text:
        try:
            job_description_text = _load_job_description(job_description_key)
        except s3.exceptions.NoSuchKey:
            return _response(404, {"message": "Job description object not found"})
        except Exception as exc:  # noqa: BLE001 - return helpful message
            return _response(500, {"message": f"Failed to read job description: {exc}"})

    if not job_description_text:
        return _response(400, {"message": "Job description text is required"})

    table = dynamodb.Table(TABLE_NAME)
    job_item = {
        "pk": f"TENANT#{tenant_id}",
        "sk": f"JOB#{job_id}",
        "tenantId": tenant_id,
        "jobId": job_id,
        "status": "RUNNING",
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "resumeKey": resume_key,
        "jobDescriptionKey": job_description_key,
        "templateKey": template_key,
        "options": options,
    }
    table.put_item(Item=job_item)

    execution_input = {
        "tenantId": tenant_id,
        "jobId": job_id,
        "bucketName": BUCKET_NAME,
        "resumeKey": resume_key,
        "jobDescriptionKey": job_description_key,
        "jobDescription": job_description_text,
        "templateKey": template_key,
        "options": options,
    }

    execution_name = f"{job_id}-{int(datetime.now(timezone.utc).timestamp())}"

    response = sfn.start_execution(
        stateMachineArn=STATE_MACHINE_ARN,
        name=execution_name[:80],
        input=json.dumps(execution_input),
    )

    return _response(202, {"jobId": job_id, "executionArn": response["executionArn"]})
