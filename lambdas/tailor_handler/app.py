import json
import os
import uuid
import time
import logging
from typing import Any, Dict, Optional, Tuple, List

import boto3
import urllib.request
import urllib.error
from boto3.dynamodb.conditions import Attr
import io
import zipfile
from xml.etree import ElementTree as ET


S3_BUCKET = os.getenv("JOBS_BUCKET", "")
TABLE_NAME = os.getenv("JOBS_TABLE", "")
STORAGE_BUCKET = os.getenv("STORAGE_BUCKET", "")
DEFAULT_PROVIDER = os.getenv("MODEL_PROVIDER", "openai")
DEFAULT_MODEL = os.getenv("MODEL_ID", "gpt-4o-mini")
OPENAI_SECRET_NAME = os.getenv("OPENAI_SECRET_NAME", "openai/api-key")
ENABLE_LLM = os.getenv("ENABLE_LLM", "false").lower() in ("1", "true", "yes")
ALLOWED_OPENAI = set((os.getenv("ALLOWED_OPENAI_MODELS", "*").split(",")))
ALLOWED_BEDROCK = set((os.getenv("ALLOWED_BEDROCK_MODELS", "anthropic.claude-3-5-sonnet-2024-06-20").split(",")))
BEDROCK_REGION = os.getenv("BEDROCK_REGION", os.getenv("AWS_REGION", "us-east-1"))

s3 = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")
secrets = boto3.client("secretsmanager")
bedrock = boto3.client("bedrock-runtime", region_name=BEDROCK_REGION)
table = dynamodb.Table(TABLE_NAME) if TABLE_NAME else None

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

_frontend_origin = (os.getenv("FRONTEND_ORIGIN") or "").strip() or "*"
_base_headers = {
    "content-type": "application/json",
    "Access-Control-Allow-Origin": "*" if _frontend_origin == "*" else _frontend_origin,
    "Access-Control-Allow-Headers": "*",
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
}


def _json_response(status: int, body: Dict[str, Any]):
    return {
        "statusCode": status,
        "headers": _base_headers,
        "body": json.dumps(body),
    }


def _docx_bytes_to_text(blob: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            xml = z.read("word/document.xml")
    except Exception:
        return ""
    try:
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        root = ET.fromstring(xml)
        texts: List[str] = []
        for t in root.findall('.//w:t', ns):
            if t.text:
                texts.append(t.text)
        return " ".join(texts).strip()
    except Exception:
        return ""


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
        # If caller did not specify a model, prefer the first GPT-5 family model if accessible
        if not (req_model and str(req_model).strip()):
            try:
                models = _list_openai_models()
                gpt5 = [m for m in models if isinstance(m, str) and m.lower().startswith("gpt-5")]
                if gpt5:
                    model = gpt5[0]
            except Exception as e:
                logger.info("Model autodetect skipped: %s", e)

        if ("*" not in ALLOWED_OPENAI) and (model not in ALLOWED_OPENAI):
            raise ValueError("Unsupported OpenAI model")

    elif provider == "bedrock":
        if ("*" not in ALLOWED_BEDROCK) and (model not in ALLOWED_BEDROCK):
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
    # Prefer environment variable when present
    env_key = os.getenv("OPENAI_API_KEY")
    if env_key:
        return env_key
    try:
        val = secrets.get_secret_value(SecretId=OPENAI_SECRET_NAME)
        s = val.get("SecretString") or ""
        try:
            obj = json.loads(s)
            return obj.get("OPENAI_API_KEY") or obj.get("api_key") or s
        except Exception:
            return s
    except Exception:
        return os.getenv("OPENAI_API_KEY", "")


def _list_openai_models() -> List[str]:
    key = _get_openai_key()
    if not key:
        raise RuntimeError("OPENAI_API_KEY not configured")
    url = "https://api.openai.com/v1/models"
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {key}")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as err:
        detail = err.read().decode("utf-8", "ignore")
        logger.error("OpenAI list models HTTPError %s: %s", err.code, detail)
        raise RuntimeError(f"OpenAI error {err.code}: {detail}") from err
    data = json.loads(raw)
    models = [m.get("id") for m in (data.get("data") or []) if isinstance(m, dict) and m.get("id")]
    # Optional filter: if ALLOWED_OPENAI has explicit values (not *), intersect
    if "*" not in ALLOWED_OPENAI and len(ALLOWED_OPENAI) > 0:
        models = [m for m in models if m in ALLOWED_OPENAI]
    # Deduplicate and sort
    return sorted(set(models))


def _call_openai(model: str, resume_text: str, job_desc: str) -> Dict[str, Any]:
    key = _get_openai_key()
    if not key:
        raise RuntimeError("OPENAI_API_KEY not configured")

    url = "https://api.openai.com/v1/responses"
    payload = {
        "model": model,
        "input": [
            {"role": "system", "content": _system_prompt()},
            {"role": "user", "content": _user_prompt(resume_text, job_desc)},
        ],
        "temperature": 0.4,
    }

    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"))
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {key}")

    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as err:
        detail = err.read().decode("utf-8", "ignore")
        logger.error("OpenAI HTTPError %s: %s", err.code, detail)
        raise RuntimeError(f"OpenAI error {err.code}: {detail}") from err
    except urllib.error.URLError as err:
        logger.error("OpenAI URLError: %s", err)
        raise RuntimeError(f"OpenAI connection error: {err}") from err

    data = json.loads(raw)
    logger.debug("OpenAI raw response: %s", raw)

    text = ""
    for out in data.get("output", []) or []:
        for content in out.get("content", []) or []:
            if content.get("type") in ("output_text", "text"):
                text += content.get("text", "")

    if not text and "output_text" in data:
        text = data.get("output_text", "")

    if not text and data.get("response"):
        for content in data["response"].get("content", []) or []:
            if content.get("type") in ("output_text", "text"):
                text += content.get("text", "")

    if not text:
        logger.warning("OpenAI response lacked textual content; returning empty object")
        return {}

    try:
        return json.loads(text)
    except json.JSONDecodeError as err:
        logger.error("Failed to decode OpenAI JSON: %s | text=%s", err, text)
        raise RuntimeError(f"OpenAI response was not valid JSON: {err}") from err


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


def _validate_resume_json(data: Dict[str, Any]) -> None:
    """Lightweight schema validation without external deps."""
    def expect(cond: bool, msg: str):
        if not cond:
            raise ValueError(f"Schema error: {msg}")

    expect(isinstance(data, dict), "root must be object")
    for k in ["header", "summary", "skills", "experience", "education"]:
        expect(k in data, f"missing key {k}")
    expect(isinstance(data["header"], dict), "header must be object")
    expect(isinstance(data["summary"], str), "summary must be string")
    expect(isinstance(data["skills"], list), "skills must be array")
    expect(isinstance(data["experience"], list), "experience must be array")
    expect(isinstance(data["education"], list), "education must be array")
    for exp in data.get("experience", []):
        expect(isinstance(exp, dict), "experience entry must be object")
        expect("bullets" in exp and isinstance(exp["bullets"], list), "experience.bullets must be array")


def _append_event(job_id: str, user_id: str, action: str, meta: Optional[Dict[str, Any]] = None) -> None:
    if table is None:
        return
    ev = {"ts": int(time.time()), "userId": user_id, "action": action, "meta": meta or {}}
    table.update_item(
        Key={"jobId": job_id},
        UpdateExpression="SET events = list_append(if_not_exists(events, :empty), :e), updatedAt=:ts",
        ExpressionAttributeValues={":e": [ev], ":empty": [], ":ts": int(time.time())},
    )


def handler(event, context):
    try:
        # Identity (from Cognito authorizer if present)
        rc = (event.get("requestContext") or {}).get("authorizer") or {}
        claims = rc.get("claims") or {}
        claim_user = claims.get("sub") or claims.get("cognito:username")
        claim_groups = (claims.get("cognito:groups") or "").split(",") if claims.get("cognito:groups") else []

        # Routing by method + path
        http_method = (event.get("httpMethod") or "").upper()
        path = event.get("path") or ""
        qs = event.get("queryStringParameters") or {}
        headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}

        # GET /models?provider=openai|bedrock -> list available models
        if http_method == "GET" and path.endswith("/models"):
            prov = (qs.get("provider") or "").lower()
            try:
                if prov == "openai":
                    return _json_response(200, {"ok": True, "provider": prov, "models": _list_openai_models()})
                elif prov == "bedrock":
                    models = sorted(ALLOWED_BEDROCK) if ALLOWED_BEDROCK else []
                    if "*" in ALLOWED_BEDROCK:
                        # Best-effort: return a common set if wildcard; listing via Bedrock control plane is not wired here
                        models = ["anthropic.claude-3-5-sonnet-2024-06-20", "anthropic.claude-3-5-haiku-2024-06-20"]
                    return _json_response(200, {"ok": True, "provider": prov, "models": models})
                else:
                    return _json_response(400, {"ok": False, "error": "Unknown provider"})
            except Exception as e:
                return _json_response(400, {"ok": False, "error": str(e)})

        # GET /jobs -> list jobs for user
        if http_method == "GET" and path.endswith("/jobs") and table is not None:
            user_id_q = headers.get("x-user-id") or qs.get("userId") or "anonymous"
            # simple scan with filter (ok for low volume)
            resp = table.scan(FilterExpression=Attr("userId").eq(user_id_q))
            return _json_response(200, {"ok": True, "items": resp.get("Items", [])})

        # GET /jobs/{jobId}
        if http_method == "GET" and table is not None and "/jobs/" in path:
            parts = path.split("/jobs/")
            j = parts[1] if len(parts) > 1 else None
            if j:
                res = table.get_item(Key={"jobId": j})
                item = res.get("Item")
                # share token access (view-only)
                share = qs.get("share")
                if share and item and item.get("shareToken") == share:
                    return _json_response(200, {"ok": True, "job": item})
                # role-based from Cognito groups (fallback to headers)
                role = (headers.get("x-user-role") or ("admin" if "Admin" in claim_groups else ("manager" if "Manager" in claim_groups else "user"))).lower()
                user_id_h = headers.get("x-user-id") or claim_user or "anonymous"
                if item and (role in ("manager", "admin") or item.get("userId") == user_id_h):
                    return _json_response(200, {"ok": True, "job": item})
                return _json_response(403, {"ok": False, "error": "forbidden"})

        # POST /tailor/refine -> refine existing JSON using feedback
        if http_method == "POST" and path.endswith("/tailor/refine"):
            body_str = event.get("body") or "{}"
            body = json.loads(body_str)
            base_json = body.get("resumeJson") or {}
            feedback = body.get("feedback") or {}
            job_id = body.get("jobId") or uuid.uuid4().hex
            user_id = (body.get("userId") or claim_user or "anonymous").strip() or "anonymous"
            prov, mdl = _choose_provider(body.get("provider"), body.get("model"))
            # In a simple scaffold, append feedback to summary or bullets; if LLM enabled, ask model to revise
            if ENABLE_LLM:
                resume_text = json.dumps(base_json)
                job_desc = json.dumps(feedback)
                if prov == "openai":
                    revised = _call_openai(mdl, resume_text, job_desc)
                else:
                    revised = _call_bedrock(mdl, resume_text, job_desc)
            else:
                revised = base_json
            try:
                _validate_resume_json(revised)
            except Exception as ve:
                return _json_response(400, {"ok": False, "error": str(ve)})
            base_prefix = f"resume-jobs/{user_id}/{job_id}"
            outputs_prefix = f"{base_prefix}/outputs"
            key = f"{outputs_prefix}/tailored.json"
            s3.put_object(Bucket=S3_BUCKET, Key=key, Body=json.dumps(revised, ensure_ascii=False, indent=2).encode("utf-8"))
            _append_event(job_id, user_id, "refined", {"provider": prov, "model": mdl})
            return _json_response(200, {"ok": True, "jobId": job_id, "jsonS3": {"bucket": S3_BUCKET, "key": key}})

        body_str = event.get("body") or "{}"
        body = json.loads(body_str)

        # Inputs
        resume_text = (body.get("resumeText") or "").strip()
        job_desc = (body.get("jobDescription") or "").strip()
        resume_key = (body.get("resumeKey") or "").strip()
        job_key = (body.get("jobKey") or "").strip()
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

        # Resolve resume text: prefer resumeKey (DOCX in storage), else inline text
        if resume_key:
            if not STORAGE_BUCKET:
                return _json_response(400, {"ok": False, "error": "Storage bucket not configured for resumeKey"})
            try:
                blob = s3.get_object(Bucket=STORAGE_BUCKET, Key=resume_key)["Body"].read()
                resume_text = _docx_bytes_to_text(blob)
                s3.put_object(Bucket=S3_BUCKET, Key=f"{inputs_prefix}/reference-resume.txt", Body=resume_text.encode("utf-8"))
                resume_s3 = {"bucket": S3_BUCKET, "key": f"{inputs_prefix}/reference-resume.txt"}
            except Exception as e:
                return _json_response(400, {"ok": False, "error": f"Failed to read resumeKey: {str(e)}"})
        elif resume_text:
            s3.put_object(Bucket=S3_BUCKET, Key=f"{inputs_prefix}/reference-resume.txt", Body=resume_text.encode("utf-8"))
            resume_s3 = {"bucket": S3_BUCKET, "key": f"{inputs_prefix}/reference-resume.txt"}

        # Resolve job description: prefer jobKey (DOCX in storage), else inline text
        if job_key:
            if not STORAGE_BUCKET:
                return _json_response(400, {"ok": False, "error": "Storage bucket not configured for jobKey"})
            try:
                blob = s3.get_object(Bucket=STORAGE_BUCKET, Key=job_key)["Body"].read()
                job_desc = _docx_bytes_to_text(blob)
                s3.put_object(Bucket=S3_BUCKET, Key=f"{inputs_prefix}/jd.txt", Body=job_desc.encode("utf-8"))
                jd_s3 = {"bucket": S3_BUCKET, "key": f"{inputs_prefix}/jd.txt"}
            except Exception as e:
                return _json_response(400, {"ok": False, "error": f"Failed to read jobKey: {str(e)}"})
        elif job_desc:
            s3.put_object(Bucket=S3_BUCKET, Key=f"{inputs_prefix}/jd.txt", Body=job_desc.encode("utf-8"))
            jd_s3 = {"bucket": S3_BUCKET, "key": f"{inputs_prefix}/jd.txt"}

        if not resume_text:
            return _json_response(400, {"ok": False, "error": "Resume not provided (resumeKey or resumeText required)"})
        if not job_desc:
            return _json_response(400, {"ok": False, "error": "Job description not provided (jobKey or jobDescription required)"})

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

        try:
            _validate_resume_json(normalized)
        except Exception as ve:
            return _json_response(400, {"ok": False, "error": str(ve)})

        # Basic cache: if content identical exists, reuse key path
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
            # Create share token on first create
            item["shareToken"] = uuid.uuid4().hex[:16]
            table.put_item(Item=item)
            _append_event(job_id, user_id, "generated", {"provider": provider, "model": model})

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

