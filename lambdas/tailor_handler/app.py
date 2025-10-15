import json
import os
import uuid
import time
from typing import Any, Dict, Optional, Tuple

import boto3
import urllib.request


S3_BUCKET = os.getenv("JOBS_BUCKET", "")
TABLE_NAME = os.getenv("JOBS_TABLE", "")
DEFAULT_PROVIDER = os.getenv("MODEL_PROVIDER", "openai")
DEFAULT_MODEL = os.getenv("MODEL_ID", "gpt-4o-mini")
OPENAI_SECRET_NAME = os.getenv("OPENAI_SECRET_NAME", "openai/api-key")
ENABLE_LLM = os.getenv("ENABLE_LLM", "false").lower() in ("1", "true", "yes")
ALLOWED_OPENAI = set((os.getenv("ALLOWED_OPENAI_MODELS", "gpt-4o-mini,gpt-4o,o4-mini").split(",")))
ALLOWED_BEDROCK = set((os.getenv("ALLOWED_BEDROCK_MODELS", "anthropic.claude-3-5-sonnet-2024-06-20").split(",")))
BEDROCK_REGION = os.getenv("BEDROCK_REGION", os.getenv("AWS_REGION", "us-east-1"))

s3 = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")
secrets = boto3.client("secretsmanager")
bedrock = boto3.client("bedrock-runtime", region_name=BEDROCK_REGION)
table = dynamodb.Table(TABLE_NAME) if TABLE_NAME else None


def _json_response(status: int, body: Dict[str, Any]):
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
    }


def _presign(bucket: str, key: str, expires: int = 900) -> str:
    return s3.generate_presigned_url(
        ClientMethod="get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=expires,
    )


def _choose_provider(req_provider: Optional[str], req_model: Optional[str]) -> Tuple[str, str]:
    provider = (req_provider or DEFAULT_PROVIDER).lower()
    model = (req_model or DEFAULT_MODEL)
    if provider == "openai":
        if model not in ALLOWED_OPENAI:
            raise ValueError("Unsupported OpenAI model")
    elif provider == "bedrock":
        if model not in ALLOWED_BEDROCK:
            raise ValueError("Unsupported Bedrock model")
    else:
        raise ValueError("Unsupported provider")
    return provider, model


def _system_prompt() -> str:
    return (
        "You are a resume tailoring assistant. Keep content truthful; align with the job description; "
        "prefer measurable impact; return ONLY a strict JSON object matching the requested schema."
    )


def _user_prompt(resume_text: str, job_desc: str) -> str:
    return (
        f"Resume:\n{resume_text}\n\nJob Description:\n{job_desc}\n\n"
        "Return JSON with keys: header{name,title,contact}, summary, skills[], "
        "experience[{ company,title,start,end,bullets[] }], education[{ school,degree,year }], extras? (object). No markdown."
    )


def _get_openai_key() -> str:
    val = secrets.get_secret_value(SecretId=OPENAI_SECRET_NAME)
    s = val.get("SecretString") or ""
    try:
        obj = json.loads(s)
        return obj.get("OPENAI_API_KEY") or obj.get("api_key") or s
    except Exception:
        return s


def _call_openai(model: str, resume_text: str, job_desc: str) -> Dict[str, Any]:
    key = _get_openai_key()
    url = "https://api.openai.com/v1/responses"
    payload = {
        "model": model,
        "input": [
            {"role": "system", "content": _system_prompt()},
            {"role": "user", "content": _user_prompt(resume_text, job_desc)},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.4,
    }
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"))
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {key}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    # Extract unified text (Responses API)
    # Prefer `output_text` if present (SDK helper); here we reconstruct
    text = ""
    for out in data.get("output", []):
        for c in out.get("content", []):
            if c.get("type") == "output_text" or c.get("type") == "text":
                text += c.get("text", "")
    if not text and "output_text" in data:
        text = data.get("output_text", "")
    return json.loads(text or "{}")


def _call_bedrock(model: str, resume_text: str, job_desc: str) -> Dict[str, Any]:
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 1500,
        "temperature": 0.4,
        "system": _system_prompt(),
        "messages": [
            {"role": "user", "content": [{"type": "text", "text": _user_prompt(resume_text, job_desc)}]}
        ],
    }
    result = bedrock.invoke_model(
        modelId=model,
        body=json.dumps(body),
        accept="application/json",
        contentType="application/json",
    )
    payload = json.loads(result["body"].read())
    text = ""
    for block in payload.get("content", []):
        if block.get("type") == "text":
            text += block.get("text", "")
    return json.loads(text or "{}")


def handler(event, context):
    try:
        # Simple status endpoint reuse: GET /jobs/{jobId}
        if event.get("httpMethod") == "GET" and table is not None:
            path_params = event.get("pathParameters") or {}
            j = path_params.get("jobId")
            if j:
                res = table.get_item(Key={"jobId": j})
                return _json_response(200, {"ok": True, "job": res.get("Item")})

        body_str = event.get("body") or "{}"
        body = json.loads(body_str)

        # Inputs
        resume_text = (body.get("resumeText") or "").strip()
        job_desc = (body.get("jobDescription") or "").strip()
        resume_s3 = body.get("resumeS3")
        jd_s3 = body.get("jobDescS3")
        user_id = (body.get("userId") or "anonymous").strip() or "anonymous"
        job_id = body.get("jobId") or uuid.uuid4().hex
        provider = (body.get("provider") or DEFAULT_PROVIDER).lower()
        model = body.get("model") or DEFAULT_MODEL

        if not S3_BUCKET or not TABLE_NAME:
            return _json_response(500, {"ok": False, "error": "Service not configured (bucket/table)"})

        # Persist inputs to S3
        ts = int(time.time())
        base_prefix = f"resume-jobs/{user_id}/{job_id}"
        inputs_prefix = f"{base_prefix}/inputs"
        outputs_prefix = f"{base_prefix}/outputs"

        if resume_text:
            s3.put_object(Bucket=S3_BUCKET, Key=f"{inputs_prefix}/reference-resume.txt", Body=resume_text.encode("utf-8"))
            resume_s3 = {"bucket": S3_BUCKET, "key": f"{inputs_prefix}/reference-resume.txt"}
        if job_desc:
            s3.put_object(Bucket=S3_BUCKET, Key=f"{inputs_prefix}/jd.txt", Body=job_desc.encode("utf-8"))
            jd_s3 = {"bucket": S3_BUCKET, "key": f"{inputs_prefix}/jd.txt"}

        # Generate normalized JSON via selected provider (or fallback to stub)
        if ENABLE_LLM and (resume_text or job_desc):
            prov, mdl = _choose_provider(provider, model)
            if prov == "openai":
                normalized = _call_openai(mdl, resume_text, job_desc)
            elif prov == "bedrock":
                normalized = _call_bedrock(mdl, resume_text, job_desc)
            else:
                raise ValueError("Unsupported provider")
        else:
            normalized = {
                "header": {"name": "", "title": "", "contact": ""},
                "summary": "",
                "skills": [],
                "experience": [],
                "education": [],
                "extras": {},
            }

        json_key = f"{outputs_prefix}/tailored.json"
        s3.put_object(Bucket=S3_BUCKET, Key=json_key, Body=json.dumps(normalized, ensure_ascii=False, indent=2).encode("utf-8"))

        json_url = _presign(S3_BUCKET, json_key)

        # Record job in DynamoDB
        if table is not None:
            item = {
                "jobId": job_id,
                "userId": user_id,
                "createdAt": ts,
                "provider": provider,
                "model": model,
                "inputs": {"resume": resume_s3, "jobDesc": jd_s3},
                "outputs": {"json": {"bucket": S3_BUCKET, "key": json_key}},
                "status": "generated",
                "versions": [
                    {
                        "versionId": "v1",
                        "createdAt": ts,
                        "json": {"bucket": S3_BUCKET, "key": json_key},
                        "scores": None,
                        "accepted": False,
                    }
                ],
            }
            table.put_item(Item=item)

        return _json_response(
            200,
            {
                "ok": True,
                "jobId": job_id,
                "jsonS3": {"bucket": S3_BUCKET, "key": json_key},
                "urls": {"json": json_url},
                "provider": provider,
                "model": model,
            },
        )

    except Exception as e:
        return _json_response(400, {"ok": False, "error": str(e)})
