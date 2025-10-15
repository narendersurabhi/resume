import json
import os
import io
from typing import Any, Dict

import boto3
from docxtpl import DocxTemplate
from jsonschema import validate, Draft202012Validator


S3 = boto3.client("s3")
DDB = boto3.resource("dynamodb")

JOBS_BUCKET = os.getenv("JOBS_BUCKET", "")
JOBS_TABLE = os.getenv("JOBS_TABLE", "")
TEMPLATES_BUCKET = os.getenv("TEMPLATES_BUCKET", "")

TABLE = DDB.Table(JOBS_TABLE) if JOBS_TABLE else None


def _json_response(status: int, body: Dict[str, Any]):
    return {"statusCode": status, "headers": {"content-type": "application/json"}, "body": json.dumps(body)}


def _load_schema() -> Dict[str, Any]:
    schema_path = os.path.join(os.path.dirname(__file__), "schema.json")
    with open(schema_path, "r", encoding="utf-8") as f:
        return json.load(f)


SCHEMA = _load_schema()
Draft202012Validator.check_schema(SCHEMA)


def _download_s3(obj: Dict[str, str]) -> bytes:
    bkt, key = obj["bucket"], obj["key"]
    resp = S3.get_object(Bucket=bkt, Key=key)
    return resp["Body"].read()


def handler(event, context):
    try:
        body_str = event.get("body") or "{}"
        body = json.loads(body_str)

        job_id = body.get("jobId") or ""
        user_id = (body.get("userId") or "anonymous").strip() or "anonymous"
        template_id = (body.get("templateId") or "default").strip() or "default"
        fmt = (body.get("format") or "docx").lower()

        # Load JSON
        data = None
        if isinstance(body.get("jsonS3"), dict):
            data = json.loads(_download_s3(body["jsonS3"]).decode("utf-8"))
        elif isinstance(body.get("resumeJson"), dict):
            data = body.get("resumeJson")
        else:
            return _json_response(400, {"ok": False, "error": "resumeJson or jsonS3 required"})

        # Validate against JSON Schema
        validate(instance=data, schema=SCHEMA)

        # Load template
        if not TEMPLATES_BUCKET:
            return _json_response(500, {"ok": False, "error": "TEMPLATES_BUCKET not configured"})
        template_key = f"templates/{template_id}/resume.docx"
        tpl_bytes = _download_s3({"bucket": TEMPLATES_BUCKET, "key": template_key})

        # Render with docxtpl
        tpl_stream = io.BytesIO(tpl_bytes)
        tpl = DocxTemplate(tpl_stream)
        # Render context supports both root keys and nested under 'data'
        # so templates can use either {{ education }} or {{ data.education }}
        ctx = {"data": data}
        if isinstance(data, dict):
            ctx.update(data)
        tpl.render(ctx)
        out_stream = io.BytesIO()
        tpl.save(out_stream)
        out_bytes = out_stream.getvalue()

        # Store outputs
        base_prefix = f"resume-jobs/{user_id}/{job_id}" if job_id else f"resume-jobs/{user_id}/adhoc"
        outputs_prefix = f"{base_prefix}/outputs"
        docx_key = f"{outputs_prefix}/tailored.docx"
        S3.put_object(Bucket=JOBS_BUCKET, Key=docx_key, Body=out_bytes)

        outputs = {"docx": {"bucket": JOBS_BUCKET, "key": docx_key}}
        # PDF conversion could be added here with headless LibreOffice if installed in image.
        if fmt == "pdf":
            outputs["pdf"] = {"bucket": JOBS_BUCKET, "key": f"{outputs_prefix}/tailored.pdf"}

        if TABLE is not None and job_id:
            TABLE.update_item(
                Key={"jobId": job_id},
                UpdateExpression="SET #s=:st, outputs.render=:out, updatedAt=:ts",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={":st": "rendered", ":out": outputs, ":ts": int(os.getenv("AWS_LAMBDA_FUNCTION_MEMORY_SIZE", "0")) or int(__import__('time').time())},
            )

        return _json_response(200, {"ok": True, "jobId": job_id, "outputs": outputs})

    except Exception as e:
        return _json_response(400, {"ok": False, "error": str(e)})
