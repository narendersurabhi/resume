from docx import Document 
from datetime import datetime
from urllib.parse import unquote_plus
import os, json, uuid, io, boto3, logging, re

log = logging.getLogger()
log.setLevel(logging.INFO)

BEDROCK_MODEL_ID = os.environ["BEDROCK_MODEL_ID"]
REGION = os.environ.get("CDK_DEFAULT_REGION", "us-east-1")
BUCKET_NAME = os.environ.get("BUCKET_NAME")
OUTPUT_PREFIX = os.environ.get("OUTPUT_PREFIX", "generated")

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

def _write_docx_to_s3(text: str, key: str):
    doc = Document()
    for line in text.splitlines():
        if not line.strip():
            doc.add_paragraph("")  # blank line
            continue
        if line.startswith("### "):
            doc.add_paragraph(line[4:].strip()).style = "Heading 2"
        elif line.startswith("**") and line.endswith("**") and len(line) < 80:
            p = doc.add_paragraph(line.strip("* ").strip())
            p.runs[0].bold = True
        elif line.startswith("|") and line.endswith("|"):
            # quick table fallback: keep as paragraph
            doc.add_paragraph(line)
        elif line.strip() == "---":
            doc.add_paragraph("")  # visual break
        else:
            doc.add_paragraph(line)

    buf = io.BytesIO()
    doc.save(buf); buf.seek(0)
    s3.put_object(
        Bucket=BUCKET_NAME,
        Key=key,
        Body=buf.getvalue(),
        ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        CacheControl="no-cache",
    )

REASONING_RE = re.compile(r"<reasoning>.*?</reasoning>\s*", re.DOTALL)

def _clean_llm_text(raw: str) -> str:
    # 1) remove reasoning block
    text = REASONING_RE.sub("", raw)

    # 2) collapse extra spaces
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()

def _invoke_bedrock(prompt: str) -> str:

    print("Invoke started")
    print("prompt: " + prompt)
    body = {
        "messages": [
            {"role": "user", "content": [{"type": "text", "text": prompt}]}
        ],
        "max_tokens": 8000,
        "temperature": 0.2
    }
    print(f"body: {body}")
    try:
        resp = bedrock.invoke_model(
            modelId=BEDROCK_MODEL_ID,
            body=json.dumps(body),
            contentType="application/json",
            accept="application/json",
        )
    except Exception as e:
        print(e)

    print("Invoke compelte")

    raw = resp["body"].read().decode("utf-8")
    print("Bedrock raw:", raw)
    out = json.loads(raw)

    # OpenAI-compatible extraction
    if "choices" in out and out["choices"]:
        msg = out["choices"][0].get("message", {})
        content = msg.get("content")
        if isinstance(content, str) and content.strip():
            print(content)
            return content

    # If we get here, the response isn't what we expected
    raise RuntimeError(f"Unexpected OpenAI-style response: {out}")

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
        "You are an expert resume writer. Tailor the resume using the job description. "
        "If a template is provided, follow its style and structure.\n\n"
        f"RESUME:\n{resume_text}\n\n"
        f"TEMPLATE (optional):\n{template_text or '[none]'}\n\n"
        f"JOB DESCRIPTION:\n{job_desc}\n\n"
        "Return only the improved resume content."
    )

    # prompt = (
    #     "You are a resume tailoring assistant.\n\n"
    #     f"JOB DESCRIPTION:\n{job_desc}\n\n"
    #     "RESUME:\n"
    #     f"{resume_text}\n\n"
    #     "TEMPLATE/STYLE GUIDANCE:\n"
    #     f"{template_text}\n\n"
    #     "Task: Rewrite and tailor the resume to the job, preserving factual accuracy.\n"
    #     "Return only the improved resume text."
    # )

    try:
        print("Before invoke")
        improved = _invoke_bedrock(prompt)
        print("Afte invoke")
        print(improved)



        output_id = uuid.uuid4().hex[:12]
        ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        base = f"{OUTPUT_PREFIX}/{tenant_id}/{output_id}-{ts}"

        docx_key = f"{base}.docx"

        clean = _clean_llm_text(improved)
        _write_docx_to_s3(clean, docx_key)


        # PDF optional: add later (another layer). For now, return None.
        result = {
            "outputId": output_id,
            "tenantId": tenant_id,
            "docxKey": docx_key,
            "pdfKey": None,
        }

        return {"statusCode": 200, "headers": _cors_headers(frontend_domain), "body": json.dumps({"result": result})}
    except Exception as e:
        log.exception("Bedrock invocation failed")
        return {
            "statusCode": 502,
            "headers": _cors_headers(frontend_domain),
            "body": json.dumps({"message": "Bedrock invocation failed", "error": str(e)}),
        }
