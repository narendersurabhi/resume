import os, io, json, boto3, logging, re
from docx import Document
from docxtpl import DocxTemplate

log = logging.getLogger()
log.setLevel(logging.INFO)

BUCKET_NAME = os.environ["BUCKET_NAME"]
OUTPUT_PREFIX = os.environ.get("OUTPUT_PREFIX", "generated")
BEDROCK_MODEL_ID = os.environ["BEDROCK_MODEL_ID"]
REGION = os.environ.get("CDK_DEFAULT_REGION", os.environ.get("AWS_REGION", "us-east-1"))

s3 = boto3.client("s3")
bedrock = boto3.client("bedrock-runtime", region_name=REGION)

REQUIRED_KEYS = {
    "name",
    "title",
    "contact",
    "city",
    "state",
    "zip",
    "phone",
    "email",
    "summary",
    "skills",
    "experience",
    "education",
    "certification",   # singular (matches your template loop)
}


# ---------- helpers ----------
def _cors_headers(origin):
    return {
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Headers": "*",
        "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
    }

def _get_text_from_docx_bytes(data: bytes) -> str:
    bio = io.BytesIO(data)
    doc = Document(bio)
    return "\n".join(p.text for p in doc.paragraphs).strip()

def _download_s3_bytes(key: str) -> bytes:
    obj = s3.get_object(Bucket=BUCKET_NAME, Key=key)
    return obj["Body"].read()

def _upload_bytes(key: str, body: bytes, content_type: str):
    try:
        s3.put_object(
            Bucket=BUCKET_NAME, Key=key, Body=body,
            ContentType=content_type, CacheControl="no-cache",
        )
    except Exception as e:
        print("Upload failed: ", e)

def extract_text(payload: dict) -> str:
    # GPT-OSS (Bedrock OpenAI-compat): {"outputs":[{"text":"..."}], ...}
    if isinstance(payload, dict):
        if isinstance(payload.get("outputs"), list) and payload["outputs"]:
            t = payload["outputs"][0].get("text")
            if t: return t
        # Some models (e.g., Titan text) use "outputText"
        t = payload.get("outputText")
        if t: return t
        # Claude converse-style (fallback if you ever switch):
        msg = payload.get("output", {}).get("message", {})
        parts = msg.get("content")
        if isinstance(parts, list) and parts and "text" in parts[0]:
            return parts[0]["text"]
    return ""


def extract_structured(payload: dict) -> dict:
    # 1) get content string
    content = (
        payload.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
    )
    if not isinstance(content, str):
        raise ValueError("No textual content in model response")

    # 2) strip any <reasoning>… blocks
    content = re.sub(r"<reasoning>.*?</reasoning>\s*", "", content, flags=re.S)

    # 3) strip accidental markdown fences
    content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.MULTILINE)

    # 4) pull the JSON object from the string
    start = content.find("{")
    end   = content.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in content")
    json_str = content[start:end+1]

    # 5) parse JSON
    data = json.loads(json_str)

    # 6) basic schema check
    missing = REQUIRED_KEYS - set(data.keys())
    if missing:
        # raise ValueError(f"Missing keys in model output: {sorted(missing)}")
        print(f"Missing keys in model output: {sorted(missing)}")

    # optional: normalize types
    # for k in ("skills","certifications"):
    #     if isinstance(data.get(k), str):
    #         data[k] = [data[k]]
    print("Structured Data: ", data)
    return data


def _invoke_bedrock_structured(resume_text: str, job_text: str) -> dict:
    # JSON-only prompt
    prompt = f"""
You are an expert technical resume writer. Rewrite and tailor the following resume for the given job description.

Output
Return ONLY valid JSON matching this exact schema and key names:

{{
  "name": "",
  "title": "",
  "city": "",
  "state": "",
  "zip": "",
  "phone": "",
  "email": "",
  "links": ["..."],
  "summary": "",
  "skills": [
    {{"group": "", "items": ["...", "..."]}}
  ],
  "experience": [
    {{"role": "", "company": "", "location": "", "period": "", "bullets": ["..."], "initiatives": ["..."] }}
  ],
  "projects": [
    {{"name": "", "period": "", "bullets": ["..."] }}
  ],
  "education": [
    {{"degree": "", "school": "", "location": "", "period": "", "bullets": ["..."] }}
  ],
  "certifications": [
    {{"name": "", "issuer": "", "year": "" }}
  ],
  "awards": ["..."]
}}


Formatting rules
- Bullets are single-line, action-first, impact-focused. No markdown.
- “period” fields are compact, e.g., "2016-Present".
- Use at most 6-10 bullets per recent role, 3-5 for older roles.
- Group skills by theme with 5-12 items each. Use JOB_DESCRIPTION wording when truthful.
- Omit empty sections. Keep key names even if arrays are empty.

Validation
- Must be parseable JSON.
- Dates, employers, degrees, and certifications must match REFERENCE_RESUME_TEXT.
- Phone and email must match or be blank if absent.
- If REFERENCE_RESUME_TEXT lacks a section, emit an empty array for that section.

Do not include markdown, reasoning text, or commentary.
Return only valid JSON.

REFERENCE_RESUME_TEXT:
{resume_text}

JOB_DESCRIPTION:
{job_text}
""".strip()

    body = {
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt}
                ]
            }
        ],
        "max_tokens": 8000,
        "temperature": 0.3
    }

    resp = bedrock.invoke_model(
        modelId=BEDROCK_MODEL_ID,
        body=json.dumps(body),
        contentType="application/json",
        accept="application/json",
    )
    payload = json.loads(resp["body"].read())
    print("payload", payload)
    # GPT-OSS returns: {"outputs":[{"text":"<json>"}], ...}
    

    try:    
        data = extract_structured(payload)
        # docx_path = render_docx_from_json(data, template_path="/opt/resume_template.docx")
        return data
    except Exception as e:
        log.error("Model did not return valid JSON: %s", e)
        raise

def _render_docx(structured: dict, template_bytes: bytes) -> bytes:
    tpl_path = "/tmp/template.docx"
    out_path = "/tmp/out.docx"
    with open(tpl_path, "wb") as f:
        f.write(template_bytes)
    doc = DocxTemplate(tpl_path)
    doc.render(structured)
    doc.save(out_path)
    with open(out_path, "rb") as f:
        return f.read()

# ---------- handler ----------
def handler(event, context):
    origin = os.getenv("FRONTEND_ORIGIN", "*")
    if event.get("httpMethod") == "OPTIONS":
        return {"statusCode": 204, "headers": _cors_headers(origin), "body": ""}

    try:
        body = json.loads(event.get("body") or "{}")
        tenant = body.get("tenantId") or "default"
        resume_key = body.get("resumeKey")          # required (DOCX in S3)
        template_key = body.get("templateKey")      # required (DOCX in S3)
        job_text = body.get("jobDescription") or "" # optional inline
        job_key = body.get("jobKey")                # optional DOCX in S3

        if not resume_key or not template_key:
            return {
                "statusCode": 400,
                "headers": _cors_headers(origin),
                "body": json.dumps({"message": "resumeKey and templateKey are required"})
            }

        # Load resume text
        resume_bytes = _download_s3_bytes(resume_key)
        resume_text = _get_text_from_docx_bytes(resume_bytes)

        # Load job description (inline or from S3 DOCX)
        if not job_text and job_key:
            job_bytes = _download_s3_bytes(job_key)
            job_text = _get_text_from_docx_bytes(job_bytes)
        if not job_text:
            return {
                "statusCode": 400,
                "headers": _cors_headers(origin),
                "body": json.dumps({"message": "Provide jobDescription or jobKey"})
            }

        # Call Bedrock → structured JSON
        structured = _invoke_bedrock_structured(resume_text, job_text)

        # Render DOCX from template
        tpl_bytes = _download_s3_bytes(template_key)
        out_bytes = _render_docx(structured, tpl_bytes)

        # Write outputs to S3 (DOCX; PDF optional later)
        output_id = context.aws_request_id
        docx_key = f"{tenant}/{OUTPUT_PREFIX}/{output_id}.docx"
        _upload_bytes(docx_key, out_bytes,
                      "application/vnd.openxmlformats-officedocument.wordprocessingml.document")

        # (Optional) add PDF later (LibreOffice container or a service)

        resp = {
            "outputId": output_id,
            "docxKey": docx_key,
            # "pdfKey": pdf_key,
        }
        return {"statusCode": 200, "headers": _cors_headers(origin), "body": json.dumps(resp)}

    except Exception as e:
        log.exception("generation failed")
        return {"statusCode": 500, "headers": _cors_headers(origin), "body": json.dumps({"error": str(e)})}
