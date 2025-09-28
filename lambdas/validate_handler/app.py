"""Lambda handler that performs structural and semantic validation on tailored resume drafts."""
from __future__ import annotations

import re
from collections import Counter
from typing import Any, Dict, Iterable, List

def _normalize_tokens(text: str) -> List[str]:
    tokens = re.findall(r"[A-Za-z0-9]+", text.lower())
    return [token for token in tokens if len(token) > 2]


def _keyword_coverage(job_description: str, draft_text: str) -> Dict[str, Any]:
    jd_tokens = Counter(_normalize_tokens(job_description))
    draft_tokens = set(_normalize_tokens(draft_text))
    required = {token for token, count in jd_tokens.items() if count >= 2 or len(token) > 6}
    covered = sorted(token for token in required if token in draft_tokens)
    missing = sorted(required - draft_tokens)
    score = round(len(covered) / max(len(required), 1), 2)
    return {"score": score, "covered": covered, "missing": missing}


def _extract_entities(parsed_resume: Dict[str, Any]) -> Iterable[str]:
    for block in parsed_resume.get("Blocks", []):
        text = block.get("Text")
        if text:
            yield text.lower()


def _detect_new_entities(draft_sections: Dict[str, Any], parsed_resume: Dict[str, Any]) -> List[str]:
    source_entities = set(_extract_entities(parsed_resume))
    introduced = []
    for section, value in draft_sections.items():
        if isinstance(value, list):
            entries = value
        else:
            entries = [value]
        for entry in entries:
            lower_entry = str(entry).lower()
            if lower_entry and lower_entry not in source_entities:
                introduced.append(f"{section}: {entry}")
    return introduced[:50]


def _required_sections() -> List[str]:
    return ["Summary", "Skills", "Experience", "Education", "Certifications"]


def handler(event: Dict[str, Any], _context: Any) -> Dict[str, Any]:
    draft = event.get("draft") or {}
    draft_text = draft.get("draftText", "")
    sections = draft.get("sections", {})
    parsed_resume = event.get("parsedResume", {})
    job_description = event.get("jobDescription", "")

    coverage = _keyword_coverage(job_description, draft_text)
    introduced_entities = _detect_new_entities(sections, parsed_resume)

    present_sections = [section for section in _required_sections() if sections.get(section)]
    missing_sections = sorted(set(_required_sections()) - set(present_sections))

    status = "PASS"
    if coverage["score"] < 0.6 or missing_sections or introduced_entities:
        status = "REVIEW"

    change_log = [
        {
            "change": "keyword_coverage",
            "details": coverage,
            "rationale": "Ensure the tailored resume aligns with employer language.",
        }
    ]
    if introduced_entities:
        change_log.append(
            {
                "change": "new_entities_detected",
                "details": introduced_entities,
                "rationale": "Flag entries not present in source resume for manual verification.",
            }
        )
    if missing_sections:
        change_log.append(
            {
                "change": "sections_missing",
                "details": missing_sections,
                "rationale": "All required resume sections must be populated before delivery.",
            }
        )

    return {
        "status": status,
        "keywordCoverage": coverage,
        "missingSections": missing_sections,
        "introducedEntities": introduced_entities,
        "changeLog": change_log,
    }
