import json
import os

from dotenv import load_dotenv
from openai import OpenAI
from langsmith import traceable

load_dotenv()


def _setting(name, default=None):
    value = os.getenv(name)
    if value:
        return value
    try:
        import streamlit as st
        value = st.secrets.get(name)
        if value:
            return value
    except Exception:
        pass
    return default


OPENROUTER_MODEL = _setting("OPENROUTER_MODEL", "openrouter/free")


def get_client():
    api_key = _setting("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not configured.")
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
    )


def build_evaluation_prompt(proposal_text, criteria):
    criteria_text = "\n".join(
        f"{c['criterion_id']}. {c['name']} (weight={c['weight']}%, max_score={c['max_score']}): {c['description']}"
        for c in criteria
    )

    return f"""
You are an RFP evaluation analyst.

Evaluate the supplier proposal ONLY using information contained in the proposal text.
Do not invent facts, evidence, certifications, experience, prices, timelines, or capabilities.

Evaluation criteria:
{criteria_text}

For EVERY active criterion, return criterion_id, score, justification, and evidence.
Also return risks (an array of proposal-specific risks) and overall_summary.
If evidence is missing or unclear, score conservatively.
Scores must be between 0 and the criterion's max_score.
Return ONLY valid JSON.

Required JSON structure:
{{
  "criteria": [
    {{
      "criterion_id": 1,
      "score": 0,
      "justification": "Reason for the score.",
      "evidence": ["Specific supporting statement from the proposal."]
    }}
  ],
  "risks": ["Risk stated or implied by the proposal evidence."],
  "overall_summary": "Concise evidence-grounded summary."
}}

SUPPLIER PROPOSAL:
------------------
{proposal_text}
------------------
"""


@traceable(name="Evaluation Agent - evaluate proposal", run_type="chain")
def evaluate_proposal(proposal_text, criteria):
    client = get_client()
    prompt = build_evaluation_prompt(proposal_text, criteria)
    messages = [
        {"role": "system", "content": "You are a careful procurement evaluation analyst. Return only valid JSON."},
        {"role": "user", "content": prompt},
    ]

    last_error = None
    for attempt in range(2):
        try:
            response = client.chat.completions.create(
                model=OPENROUTER_MODEL,
                messages=messages,
                temperature=0,
                max_tokens=2500,
                response_format={"type": "json_object"},
            )
        except Exception as exc:
            last_error = f"LLM request failed: {exc}"
            continue

        content = response.choices[0].message.content
        if not content:
            last_error = "The LLM returned an empty response."
            continue

        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            last_error = f"The LLM returned invalid JSON. JSON error: {exc}. Raw response: {content[:1000]}"

    raise RuntimeError(last_error or "LLM evaluation failed.")
