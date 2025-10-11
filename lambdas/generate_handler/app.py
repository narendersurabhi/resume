import os
import json
import boto3
import logging
from urllib.parse import unquote_plus

# Optional: python-docx is loaded via your Lambda layer; if missing, we fall back to raw bytes
try:
    from docx import Document  # python-docx
except Exception:  # layer not present
    Document = None

log = logging.getLogger()
log.setLevel(logging.INFO)

BEDROCK_MODEL_ID = os.environ["BEDROCK_MODEL_ID"]
REGION = os.environ.get("CDK_DEFAULT_REGION", "us-east-1")
BUCKET_NAME = os.environ.get("BUCKET_NAME")

bedrock = boto3.client("bedrock-runtime", region_name=REGION)
s3 = boto3.client("s3", region_name=REGION)

log.info(f"BEDROCK_MODEL_ID: {BEDROCK_MODEL_ID}")
log.info(f"REGION: {REGION}")
print("Start")

CF_DIST_ID = os.getenv("CF_DIST_ID")
frontend_domain = f"https://{CF_DIST_ID}.cloudfront.net"  # put your CF URL here

def _cors_headers(origin="*"):
    return {
        "Access-Control-Allow-Origin": origin,   # use your exact CF origin in prod
        "Access-Control-Allow-Headers": "*",
        "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
    }

def _is_docx_key(key: str) -> bool:
    return key.lower().endswith(".docx")

def _read_docx_bytes(data: bytes) -> str:
    if Document is None:
        # Layer missing — return raw text best-effort
        try:
            return data.decode("utf-8", errors="ignore")
        except Exception:
            return ""
    from io import BytesIO
    doc = Document(BytesIO(data))
    return "\n".join(p.text for p in doc.paragraphs)

def _get_text_from_s3(key: str) -> str:
    key = unquote_plus(key)
    obj = s3.get_object(Bucket=BUCKET_NAME, Key=key)
    data = obj["Body"].read()
    if _is_docx_key(key):
        return _read_docx_bytes(data)
    # assume text-ish
    try:
        return data.decode("utf-8", errors="ignore")
    except Exception:
        return ""

def _invoke_bedrock(prompt: str) -> str:

    print("Invoke started")
    log.info("prompt: " + prompt)
    body = {
        "messages": [
            {"role": "user", "content": [{"type": "text", "text": prompt}]}
        ],
        "max_tokens": 8000,
        "temperature": 0.2
    }
    log.info(f"body: {body}")
    try:
        resp = bedrock.invoke_model(
            modelId=BEDROCK_MODEL_ID,
            body=json.dumps(body),
            contentType="application/json",
            accept="application/json",
        )
    except Exception as e:
        print(e)

    print(f"Response: {resp}")
    out = json.loads(resp["body"].read())
    print(f"Output: {out["output"]["message"]["content"][0]["text"]}")
    print("Invoke ended.")
    return out["output"]["message"]["content"][0]["text"]

def handler(event, context):
    # Expect a JSON body with a 'prompt' field. Adjust if your API contract differs.
    
    body = json.loads(event.get("body") or "{}")
    print("body: ", json.dumps(body))

    tenant_id = body.get("tenantId")
    resume_key = body.get("resumeKey")
    template_key = body.get("templateKey")
    job_desc = body.get("jobDescription") or body.get("jobDesc")

    # Basic validation
    missing = [k for k, v in {
        "tenantId": tenant_id,
        "resumeKey": resume_key,
        "templateKey": template_key,
        "jobDescription": job_desc,
    }.items() if not v]

    if missing:
        return {
            "statusCode": 400,
            "headers": _cors_headers(frontend_domain),
            "body": json.dumps({"message": f"Invalid request: missing {', '.join(missing)}"}),
        }

    try:
        resume_text = _get_text_from_s3(resume_key)
        template_text = _get_text_from_s3(template_key)
    except Exception as e:
        log.exception("Failed to read S3 objects")
        return {
            "statusCode": 500,
            "headers": _cors_headers(frontend_domain),
            "body": json.dumps({"message": "Failed to read S3 objects", "error": str(e)}),
        }

    if not resume_text or not job_desc:
        print("No resume or job")
        return {"statusCode": 400, "headers": _cors_headers(frontend_domain), "body": json.dumps({"message": "resumeText and jobDesc required"})}

    prompt = (
        "You are a resume tailoring assistant.\n\n"
        f"JOB DESCRIPTION:\n{job_desc}\n\n"
        "RESUME:\n"
        f"{resume_text}\n\n"
        "TEMPLATE/STYLE GUIDANCE:\n"
        f"{template_text}\n\n"
        "Task: Rewrite and tailor the resume to the job, preserving factual accuracy.\n"
        "Return only the improved resume text."
    )

    try:
        log.info("Invoking Bedrock via inference profile")
        print("Before invoke")
        improved = _invoke_bedrock(prompt)
        print("Afte invoke")
        log.info(improved)
        return {"statusCode": 200, "headers": _cors_headers(frontend_domain), "body": json.dumps({"result": improved})}
    except Exception as e:
        log.exception("Bedrock invocation failed")
        return {
            "statusCode": 502,
            "headers": _cors_headers(frontend_domain),
            "body": json.dumps({"message": "Bedrock invocation failed", "error": str(e)}),
        }
