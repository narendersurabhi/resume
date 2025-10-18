import json
import os
import uuid
import time
from typing import Any, Dict

import boto3
import io
import zipfile


S3_BUCKET = os.getenv("JOBS_BUCKET", "")
TABLE_NAME = os.getenv("JOBS_TABLE", "")

s3 = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(TABLE_NAME) if TABLE_NAME else None


def _json_response(status: int, body: Dict[str, Any]):
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body),
    }


def handler(event, context):
    try:
        body_str = event.get("body") or "{}"
        body = json.loads(body_str)

        job_id = body.get("jobId") or uuid.uuid4().hex
        user_id = (body.get("userId") or "anonymous").strip() or "anonymous"
        template_id = (body.get("templateId") or "default").strip() or "default"
        fmt = (body.get("format") or "docx").lower()

        resume_json = body.get("resumeJson")
        json_s3 = body.get("jsonS3")  # {bucket, key}

        if not S3_BUCKET or not TABLE_NAME:
            return _json_response(500, {"ok": False, "error": "Service not configured (bucket/table)"})

        ts = int(time.time())
        base_prefix = f"resume-jobs/{user_id}/{job_id}"
        outputs_prefix = f"{base_prefix}/outputs"

        # If a JSON object is provided inline, write it under outputs/wip.json for traceability
        if resume_json and isinstance(resume_json, dict):
            s3.put_object(Bucket=S3_BUCKET, Key=f"{outputs_prefix}/wip.json", Body=json.dumps(resume_json, ensure_ascii=False, indent=2).encode("utf-8"))
            json_s3 = {"bucket": S3_BUCKET, "key": f"{outputs_prefix}/wip.json"}

        # Load JSON for rendering
        if json_s3 and isinstance(json_s3, dict):
            b = s3.get_object(Bucket=json_s3["bucket"], Key=json_s3["key"]) ["Body"].read()
            data = json.loads(b.decode("utf-8"))
        elif resume_json and isinstance(resume_json, dict):
            data = resume_json
        else:
            return _json_response(400, {"ok": False, "error": "resumeJson or jsonS3 required"})

        # Minimal DOCX packer (no external libs): create a simple document with basic paragraphs
        def build_docx_bytes(d: Dict[str, Any]) -> bytes:
            docx_bytes = io.BytesIO()
            with zipfile.ZipFile(docx_bytes, mode="w", compression=zipfile.ZIP_DEFLATED) as z:
                z.writestr("[Content_Types].xml", (
                    "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
                    "<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\">"
                    "<Default Extension=\"rels\" ContentType=\"application/vnd.openxmlformats-package.relationships+xml\"/>"
                    "<Default Extension=\"xml\" ContentType=\"application/xml\"/>"
                    "<Override PartName=\"/word/document.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml\"/>"
                    "</Types>"
                ))
                z.writestr("_rels/.rels", (
                    "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
                    "<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\"></Relationships>"
                ))
                # Build document XML with extremely simple paragraphs
                def para(text: str) -> str:
                    esc = (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    return f"<w:p><w:r><w:t>{esc}</w:t></w:r></w:p>"
                lines = []
                h = d.get("header", {})
                name = h.get("name", "")
                title = h.get("title", "")
                contact = h.get("contact", "")
                if name or title:
                    lines.append(para(f"{name} â€” {title}".strip(" â€”")))
                if contact:
                    lines.append(para(contact))
                if d.get("summary"):
                    lines.append(para(""))
                    lines.append(para(d.get("summary", "")))
                if d.get("skills"):
                    lines.append(para(""))
                    lines.append(para("Skills: " + ", ".join(d.get("skills", []))))
                for exp in d.get("experience", []) or []:
                    lines.append(para(""))
                    lines.append(para(f"{exp.get('title','')} â€” {exp.get('company','')} ({exp.get('start','')} - {exp.get('end','')})"))
                    for b in exp.get("bullets", []) or []:
                        lines.append(para("â€¢ " + b))
                for edu in d.get("education", []) or []:
                    lines.append(para(""))
                    lines.append(para(f"{edu.get('degree','')} â€” {edu.get('school','')} ({edu.get('year','')})"))

                document_xml = (
                    "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
                    "<w:document xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\">"
                    + "".join(lines) + "</w:document>"
                )
                z.writestr("word/document.xml", document_xml)
            return docx_bytes.getvalue()

        if fmt not in ("docx", "pdf"):
            return _json_response(400, {"ok": False, "error": "format must be docx|pdf"})

        # Validate JSON shape before rendering
        def _expect(cond: bool, msg: str):
            if not cond:
                raise ValueError(msg)
        _expect(isinstance(data, dict), "resumeJson must be object")
        _expect("header" in data and isinstance(data["header"], dict), "missing header")
        _expect("experience" in data and isinstance(data["experience"], list), "missing experience")

        # Produce DOCX always; if PDF requested, write DOCX and mark pdf key placeholder
        docx_bytes = build_docx_bytes(data)
        docx_key = f"{outputs_prefix}/tailored.docx"
        s3.put_object(Bucket=S3_BUCKET, Key=docx_key, Body=docx_bytes)

        result = {"docx": {"bucket": S3_BUCKET, "key": docx_key}}
        if fmt == "pdf":
            # Placeholder: downstream worker could convert to PDF
            result["pdf"] = {"bucket": S3_BUCKET, "key": f"{outputs_prefix}/tailored.pdf"}

        if table is not None:
            upd = {
                ":st": "rendered",
                ":ts": int(time.time()),
                ":out": result,
            }
            dynamodb.Table(TABLE_NAME).update_item(
                Key={"jobId": job_id},
                UpdateExpression="SET #s=:st, outputs.render=:out, updatedAt=:ts",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues=upd,
            )

        return _json_response(200, {"ok": True, "jobId": job_id, "outputs": result})

    except Exception as e:
        return _json_response(400, {"ok": False, "error": str(e)})

