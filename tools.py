import json
import re
from typing import List

from pypdf import PdfReader
from pydantic import BaseModel, Field


class CriterionResult(BaseModel):
    criterion_id: int
    score: float = Field(ge=0)
    justification: str = ""
    evidence: List[str] = []


class EvaluationResponse(BaseModel):
    criteria: List[CriterionResult]
    risks: List[str] = []
    overall_summary: str = ""


def extract_pdf_text(pdf_path):
    """Extract all readable text from a supplier PDF."""
    reader = PdfReader(pdf_path)
    pages = []
    for page in reader.pages:
        text = page.extract_text() or ""
        pages.append(text)
    return "\n\n".join(pages).strip()


def extract_json_from_response(text):
    """Extract JSON from an LLM response."""
    text = text.strip()
    text = re.sub(r"^```json\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^```\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def validate_and_normalize(raw_response, criteria):
    """Validate, normalize, and complete an LLM evaluation response."""
    warnings = []

    if isinstance(raw_response, str):
        try:
            raw_response = extract_json_from_response(raw_response)
        except Exception as exc:
            return {
                "criteria": [
                    {
                        "criterion_id": c["criterion_id"],
                        "name": c["name"],
                        "score": 0.0,
                        "max_score": float(c["max_score"]),
                        "justification": "No valid LLM JSON was available.",
                        "evidence": [],
                        "weight": float(c["weight"]),
                    }
                    for c in criteria
                ],
                "warnings": [f"Invalid JSON response: {exc}"],
                "risks": [],
                "overall_summary": "",
            }

    if not isinstance(raw_response, dict):
        raw_response = {}
        warnings.append("LLM response was not a JSON object; all scores set to 0.")

    raw_items = raw_response.get("criteria", [])
    if not isinstance(raw_items, list):
        raw_items = []
        warnings.append("LLM 'criteria' field was not a list; all scores set to 0.")

    by_id = {c["criterion_id"]: c for c in criteria}
    normalized_by_id = {}
    seen_ids = set()

    for item in raw_items:
        if not isinstance(item, dict):
            warnings.append("Ignored a non-object criterion result.")
            continue

        try:
            criterion_id = int(item.get("criterion_id"))
        except Exception:
            warnings.append("Ignored result with invalid criterion_id.")
            continue

        if criterion_id not in by_id:
            warnings.append(f"Ignored unexpected criterion_id {criterion_id}.")
            continue

        if criterion_id in seen_ids:
            warnings.append(f"Duplicate criterion_id {criterion_id}; kept first result.")
            continue

        criterion = by_id[criterion_id]
        try:
            score = float(item.get("score"))
        except Exception:
            warnings.append(f"Criterion {criterion_id} had an invalid score; set to 0.")
            score = 0.0

        original_score = score
        score = max(0.0, min(score, float(criterion["max_score"])))
        if score != original_score:
            warnings.append(
                f"Criterion {criterion_id} score {original_score} was clipped to {score}."
            )

        evidence = item.get("evidence", [])
        if not isinstance(evidence, list):
            evidence = [evidence]
        evidence = [str(e).strip() for e in evidence if str(e).strip()]

        normalized_by_id[criterion_id] = {
            "criterion_id": criterion_id,
            "name": criterion["name"],
            "score": score,
            "max_score": float(criterion["max_score"]),
            "justification": str(item.get("justification", "")).strip(),
            "evidence": evidence,
            "weight": float(criterion["weight"]),
        }
        seen_ids.add(criterion_id)

    # Missing active criteria are explicitly filled with zero so every supplier
    # has a complete, comparable scorecard.
    normalized = []
    for criterion in criteria:
        criterion_id = criterion["criterion_id"]
        if criterion_id not in normalized_by_id:
            warnings.append(
                f"Missing evaluation for criterion {criterion_id}: {criterion['name']}; set to 0."
            )
            normalized_by_id[criterion_id] = {
                "criterion_id": criterion_id,
                "name": criterion["name"],
                "score": 0.0,
                "max_score": float(criterion["max_score"]),
                "justification": "No valid evaluation was returned for this criterion.",
                "evidence": [],
                "weight": float(criterion["weight"]),
            }
        normalized.append(normalized_by_id[criterion_id])

    risks = raw_response.get("risks", [])
    if not isinstance(risks, list):
        risks = [str(risks)] if risks else []
    risks = [str(r).strip() for r in risks if str(r).strip()]

    return {
        "criteria": normalized,
        "warnings": warnings,
        "risks": risks,
        "overall_summary": str(raw_response.get("overall_summary", "")).strip(),
    }
