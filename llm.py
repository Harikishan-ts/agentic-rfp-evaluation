import json
import os
import re

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


OPENROUTER_MODEL = _setting("OPENROUTER_MODEL", "openai/gpt-4.1-mini")


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

IMPORTANT OUTPUT RULES:
- Return one result for every active criterion.
- Return JSON only.
- Do NOT use Markdown.
- Do NOT wrap the JSON in ```json or ``` fences.
- Do NOT add any text before or after the JSON.
- evidence must be an array of strings.
- risks must be an array of strings.

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


def _parse_json_response(content):
    """Parse strict JSON, while tolerating common Markdown code fences."""
    if not content:
        raise ValueError("The LLM returned an empty response.")

    text = content.strip()

    # Preferred case: pure JSON.
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Common model behavior: ```json ... ```
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.IGNORECASE | re.DOTALL)
    if fenced:
        return json.loads(fenced.group(1).strip())

    # Last-resort recovery when a model adds a short sentence around JSON.
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return json.loads(text[start:end + 1])

    raise ValueError("No JSON object could be extracted from the LLM response.")


@traceable(name="Evaluation Agent - evaluate proposal", run_type="chain")
def evaluate_proposal(proposal_text, criteria):
    client = get_client()
    prompt = build_evaluation_prompt(proposal_text, criteria)

    base_messages = [
        {
            "role": "system",
            "content": (
                "You are a careful procurement evaluation analyst. "
                "Return ONLY a valid JSON object. Never use Markdown code fences."
            ),
        },
        {"role": "user", "content": prompt},
    ]

    last_error = None

    for attempt in range(2):
        messages = list(base_messages)

        if attempt == 1:
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Your previous response was not parseable as JSON. "
                        "Return the complete evaluation again as a single valid JSON object, "
                        "with no ``` fences and no explanatory text."
                    ),
                }
            )

        try:
            response = client.chat.completions.create(
                model=OPENROUTER_MODEL,
                messages=messages,
                temperature=0,
                max_tokens=4000,
                response_format={"type": "json_object"},
            )

            content = response.choices[0].message.content

            try:
                return _parse_json_response(content)
            except (json.JSONDecodeError, ValueError) as exc:
                last_error = (
                    f"The LLM returned invalid JSON. JSON error: {exc}. "
                    f"Raw response: {(content or '')[:1000]}"
                )

        except Exception as exc:
            last_error = f"LLM request failed: {exc}"

    raise RuntimeError(last_error or "LLM evaluation failed.")
