"""Lambda handler responsible for generating tailored resumes."""
from __future__ import annotations
import io, json, logging, os, uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional
import boto3
from botocore.exceptions import ClientError
from docx import Document

LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)

s3 = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")
bedrock = boto3.client("bedrock-runtime")
comprehend = boto3.client("comprehend")

BUCKET_NAME = os.environ["BUCKET_NAME"]
TABLE_NAME = os.environ["TABLE_NAME"]

# Use your active inference profile for Llama 3.3 70B Instruct
BEDROCK_MODEL_ID = os.environ.get(
    "BEDROCK_MODEL_ID",
    "arn:aws:bedrock:us-east-2:026654547457:application-inference-profile/zw6bj0p9104h",
)
OUTPUT_PREFIX = os.environ.get("OUTPUT_PREFIX", "generated")

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "*",
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
}


def _response(status: int, body: Dict[str, Any]) -> Dict[str, Any]:
    return {"statusCode": status, "headers": CORS_HEADERS, "body": json.dumps(body)}


def _read_s3_text(key: str) -> str:
    LOGGER.info("Fetching %s from %s", key, BUCKET_NAME)
    obj = s3.get_object(Bucket=BUCKET_NAME, Key=key)
    return obj["Body"].read().decode("utf-8")


def _read_s3_bytes(key: str) -> bytes:
    obj = s3.get_object(Bucket=BUCKET_NAME, Key=key)
    return obj["Body"].read()


def _invoke_bedrock(prompt: str) -> str:
    """Invoke Llama 3.3 70B Instruct model through its inference profile."""
    body = json.dumps(
        {
            "inputText": prompt,
            "textGenerationConfig": {
                "maxTokenCount": 4000,
                "temperature": 0.3,
                "topP": 0.9,
            },
        }
    )

    response = bedrock.invoke_model(modelId=BEDROCK_MODEL_ID, body=body)
    payload = json.loads(response["body"].read())
    return payload.get("outputText", "").strip()


def _apply_pii_screening(text: str) -> None:
    try:
        result = comprehend.contains_pii_entities(Text=text, LanguageCode="en")
        if result.get("Labels"):
            LOGGER.warning("PII detected in job description: %s", result["Labels"])
    except ClientError as exc:
        LOGGER.warning("PII detection failed: %s", exc)


def _build_docx(template_bytes: Optional[bytes], tailored_text: str) -> bytes:
    if template_bytes:
        document = Document(io.BytesIO(template_bytes))
        for paragraph in document.paragraphs:
            if "{{TAILORED_CONTENT}}" in paragraph.text:
                paragraph.text = tailored_text
                break
        else:
            document.add_page_break()
            document.add_paragraph(tailored_text)
    else:
        document = Document()
        for line in tailored_text.splitlines():
            document.add_paragraph(line)

    buffer = io.BytesIO()
    document.save(buffer)
    buffer.seek(0)
    return buffer.read()


def _pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _generate_pdf_bytes(tailored_text: str) -> bytes:
    escaped_text = _pdf_escape(tailored_text[:2000])
    stream = f"BT /F1 12 Tf 72 720 Td ({escaped_text}) Tj ET"
    objects = [
        "1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n",
        "2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj\n",
        "3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        "/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>endobj\n",
        "4 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj\n",
        f"5 0 obj<< /Length {len(stream)} >>stream\n{stream}\nendstream\nendobj\n",
    ]

    offsets = [0]
    pdf_body = bytearray(b"%PDF-1.4\n")
    for obj in objects:
        offsets.append(len(pdf_body))
        pdf_body.extend(obj.encode("utf-8"))
    xref_start = len(pdf_body)
    xref_entries = ["0000000000 65535 f \n"] + [f"{o:010} 00000 n \n" for o in offsets[1:]]
    pdf_body.extend(b"xref\n0 6\n")
    pdf_body.extend("".join(xref_entries).encode("utf-8"))
    pdf_body.extend(b"trailer<< /Size 6 /Root 1 0 R >>\nstartxref\n")
    pdf_body.extend(f"{xref_start}\n".encode("utf-8"))
    pdf_body.extend(b"%%EOF")
    return bytes(pdf_body)


def handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    try:
        payload = json.loads(event.get("body") or "{}")
        tenant_id = payload["tenantId"]
        resume_key = payload["resumeKey"]
        template_key = payload.get("templateKey")
        job_description = payload.get("jobDescription")
        job_description_key = payload.get("jobDescriptionKey")
    except (json.JSONDecodeError, KeyError) as exc:
        return _response(400, {"message": f"Invalid request payload: {exc}"})

    if not job_description and job_description_key:
        job_description = _read_s3_text(job_description_key)
    elif not job_description:
        return _response(400, {"message": "Job description is required"})

    resume_text = _read_s3_text(resume_key)
    template_bytes = _read_s3_bytes(template_key) if template_key else None

    _apply_pii_screening(job_description)

    prompt = (
        "You are an expert technical resume writer. Align the candidate’s experience "
        "and achievements from the approved resume to the job description. Maintain professional tone "
        "and ATS-friendly formatting.\n\nApproved resume:\n"
        + resume_text
        + "\n\nJob description:\n"
        + job_description
    )

    tailored_text = _invoke_bedrock(prompt)
    if not tailored_text:
        return _response(500, {"message": "No tailored resume generated"})

    docx_bytes = _build_docx(template_bytes, tailored_text)
    pdf_bytes = _generate_pdf_bytes(tailored_text)

    output_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()
    docx_key = f"{tenant_id}/{OUTPUT_PREFIX}/{output_id}.docx"
    pdf_key = f"{tenant_id}/{OUTPUT_PREFIX}/{output_id}.pdf"

    s3.put_object(Bucket=BUCKET_NAME, Key=docx_key, Body=docx_bytes)
    s3.put_object(Bucket=BUCKET_NAME, Key=pdf_key, Body=pdf_bytes)

    table = dynamodb.Table(TABLE_NAME)
    for fmt, key in [("docx", docx_key), ("pdf", pdf_key)]:
        table.put_item(
            Item={
                "tenantId": tenant_id,
                "resourceId": key,
                "category": "generated",
                "outputId": output_id,
                "format": fmt,
                "createdAt": timestamp,
            }
        )

    return _response(
        200,
        {"message": "Resume generated", "docxKey": docx_key, "pdfKey": pdf_key, "outputId": output_id},
    )
