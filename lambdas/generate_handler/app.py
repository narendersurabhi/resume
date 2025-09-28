"""Lambda handler that orchestrates multi-stage Bedrock prompting to craft a tailored resume draft."""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List

import boto3

LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)

s3 = boto3.client("s3")
bedrock = boto3.client("bedrock-runtime")

default_model = os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0")
BUCKET_NAME = os.environ["BUCKET_NAME"]


def _invoke_bedrock(messages: List[Dict[str, Any]], model_id: str | None = None, max_tokens: int = 3500) -> str:
    """Utility wrapper around Bedrock Anthropic-compatible API."""
    payload = json.dumps(
        {
            "anthropic_version": "bedrock-2023-05-31",
            "temperature": 0.3,
            "top_p": 0.9,
            "top_k": 250,
            "max_tokens": max_tokens,
            "messages": messages,
        }
    )
    LOGGER.info("Invoking Bedrock model %s", model_id or default_model)
    response = bedrock.invoke_model(modelId=model_id or default_model, body=payload)
    data = json.loads(response["body"].read())
    content = data.get("content", [])
    if not content:
        raise RuntimeError("Empty response from Bedrock")
    return content[0].get("text", "").strip()


def _textract_to_text(parsed_resume: Dict[str, Any]) -> str:
    blocks = parsed_resume.get("Blocks", [])
    lines = [block.get("Text", "") for block in blocks if block.get("BlockType") in {"LINE", "WORD"}]
    return "\n".join(filter(None, lines))


def _load_resume_text(resume_key: str) -> str:
    LOGGER.info("Loading resume text from %s", resume_key)
    obj = s3.get_object(Bucket=BUCKET_NAME, Key=resume_key)
    return obj["Body"].read().decode("utf-8", errors="ignore")


def _extract_competencies(job_description: str) -> Dict[str, Any]:
    prompt = (
        "You are assisting with resume tailoring. Read the job description and produce a structured JSON payload "
        "containing core competencies, mandatory qualifications, preferred qualifications, and critical keywords. "
        "Each property should be an array of short strings. Limit to 12 items per array."
    )
    response = _invoke_bedrock(
        [
            {"role": "user", "content": [{"type": "text", "text": f"{prompt}\n\nJob description:\n{job_description}"}]},
        ]
    )
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        LOGGER.warning("Competency extraction not valid JSON; returning text")
        return {"raw": response}


def _align_experience(resume_text: str, competencies: Dict[str, Any]) -> str:
    competency_text = json.dumps(competencies)
    prompt = (
        "Using the resume content and the extracted competencies, explain how each prior role demonstrates the required "
        "skills. Provide bullet-level mapping with quantified evidence when available."
    )
    return _invoke_bedrock(
        [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"{prompt}\n\nCompetencies:\n{competency_text}\n\nResume:\n{resume_text}"},
                ],
            }
        ],
        max_tokens=2500,
    )


def _rewrite_bullets(resume_text: str, job_description: str) -> str:
    prompt = (
        "Rewrite each experience bullet from the resume using STAR format and impact-focused language. Ensure bullets "
        "remain truthful to the original resume. Output should be organized by role with each bullet on its own line."
    )
    return _invoke_bedrock(
        [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"{prompt}\n\nResume:\n{resume_text}\n\nJob description:\n{job_description}",
                    },
                ],
            }
        ],
        max_tokens=2500,
    )


def _harmonize_skills(resume_text: str, job_description: str) -> str:
    prompt = (
        "List a comma-separated set of skills that should appear in the tailored resume. Prioritize overlapping keywords "
        "between the resume and job description and remove duplicates."
    )
    return _invoke_bedrock(
        [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"{prompt}\n\nResume:\n{resume_text}\n\nJob description:\n{job_description}",
                    }
                ],
            }
        ],
        max_tokens=600,
    )


def _consistency_pass(resume_text: str, job_description: str, rewritten_bullets: str) -> str:
    prompt = (
        "Review the tailored resume content for tone, tense, and formatting consistency. Confirm that no unverifiable claims "
        "are introduced. Highlight any risks or assumptions as a concise JSON list with fields 'issue' and 'recommendation'."
    )
    return _invoke_bedrock(
        [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            f"{prompt}\n\nOriginal resume summary:\n{resume_text[:2000]}"
                            f"\n\nRewritten bullets:\n{rewritten_bullets}\n\nJob description summary:\n{job_description[:2000]}"
                        ),
                    }
                ],
            }
        ],
        max_tokens=1200,
    )


def handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    LOGGER.info("Generating draft for event %s", event.get("jobId"))
    tenant_id = event["tenantId"]
    resume_key = event["resumeKey"]
    job_description = event.get("jobDescription")
    job_description_key = event.get("jobDescriptionKey")
    parsed_resume = event.get("parsedResume", {})
    options = event.get("options", {})

    resume_text = _textract_to_text(parsed_resume) or _load_resume_text(resume_key)
    if not resume_text:
        raise ValueError("Unable to derive resume text for tailoring")

    if not job_description and job_description_key:
        job_description_obj = s3.get_object(Bucket=BUCKET_NAME, Key=job_description_key)
        job_description = job_description_obj["Body"].read().decode("utf-8")

    if not job_description:
        raise ValueError("Job description text is required for generation")

    competencies = _extract_competencies(job_description)
    alignment_notes = _align_experience(resume_text, competencies)
    rewritten_bullets = _rewrite_bullets(resume_text, job_description)
    harmonized_skills = _harmonize_skills(resume_text, job_description)
    consistency_report = _consistency_pass(resume_text, job_description, rewritten_bullets)

    summary_prompt = (
        "Compose a complete resume in JSON with sections Summary, Skills, Experience, Education, and Certifications. "
        "Each section should have either a string or an array of bullet strings. Enforce professional tone, ATS-friendly "
        "formatting, and limit total length to two pages worth of content. Incorporate the rewritten bullets and skills "
        "list."
    )
    final_response = _invoke_bedrock(
        [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            f"{summary_prompt}\n\nCompetencies:{json.dumps(competencies)}"
                            f"\n\nAlignment notes:\n{alignment_notes}\n\nRewritten bullets:\n{rewritten_bullets}"
                            f"\n\nSkills:\n{harmonized_skills}"
                        ),
                    }
                ],
            }
        ],
        max_tokens=3200,
    )

    try:
        tailored_json = json.loads(final_response)
    except json.JSONDecodeError:
        LOGGER.warning("Final response not JSON; embedding as raw text")
        tailored_json = {"Summary": final_response}

    draft_text_lines: List[str] = []
    for section in ["Summary", "Skills", "Experience", "Education", "Certifications"]:
        value = tailored_json.get(section)
        if value:
            draft_text_lines.append(section.upper())
            if isinstance(value, list):
                draft_text_lines.extend(f"- {item}" for item in value)
            else:
                draft_text_lines.append(str(value))
            draft_text_lines.append("")

    harmonized_list = [skill.strip() for skill in harmonized_skills.split(",") if skill.strip()]
    pii_summary = event.get("piiAnalysis") or {}
    if isinstance(pii_summary, dict) and pii_summary.get("Entities"):
        LOGGER.warning("PII entities detected: %s", pii_summary["Entities"])

    return {
        "tenantId": tenant_id,
        "draftText": "\n".join(draft_text_lines).strip(),
        "sections": tailored_json,
        "competencies": competencies,
        "alignment": alignment_notes,
        "skills": harmonized_list,
        "consistency": consistency_report,
        "options": options,
    }
