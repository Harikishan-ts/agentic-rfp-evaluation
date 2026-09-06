import json
from datetime import datetime, timezone
from uuid import uuid4

from database import (
    create_run,
    load_active_criteria,
    save_supplier_result,
    update_run_status,
)
from tools import extract_pdf_text, validate_and_normalize
from llm import evaluate_proposal
from ranking import enrich_supplier_results, rank_suppliers


def validate_weights(criteria):
    if not criteria:
        raise ValueError("At least one active evaluation criterion is required.")

    total = sum(float(c["weight"]) for c in criteria)

    if abs(total - 100.0) > 0.001:
        raise ValueError(
            f"Active criterion weights must total 100%. Current total: {total}%"
        )

    return True


def create_rfp_run(suppliers):
    """Run the complete evaluation workflow and return the persisted result."""
    criteria = load_active_criteria()
    validate_weights(criteria)

    if not suppliers:
        raise ValueError("At least one supplier is required.")

    names = [str(s["supplier_name"]).strip() for s in suppliers]
    if any(not name for name in names):
        raise ValueError("Supplier names cannot be blank.")
    if len(set(name.casefold() for name in names)) != len(names):
        raise ValueError("Supplier names must be unique within a run.")

    # UUID avoids collisions when two runs start within the same second.
    run_id = f"{datetime.now(timezone.utc):%Y%m%d_%H%M%S}_{uuid4().hex[:8]}"
    create_run(rfp_run_id=run_id, status="RUNNING")

    try:
        supplier_results = []
        for supplier in suppliers:
            supplier_results.append(
                evaluate_supplier(
                    rfp_run_id=run_id,
                    pdf_path=supplier["pdf_path"],
                    supplier_name=supplier["supplier_name"],
                    submission_date=supplier["submission_date"],
                    experience_rating=supplier["experience_rating"],
                )
            )

        ranked_results = finalize_run(run_id, supplier_results)
        return {
            "rfp_run_id": run_id,
            "suppliers": ranked_results,
        }
    except Exception:
        update_run_status(run_id, "FAILED")
        raise


def evaluate_supplier(
    rfp_run_id,
    pdf_path,
    supplier_name,
    submission_date,
    experience_rating,
):
    criteria = load_active_criteria()
    validate_weights(criteria)

    proposal_text = extract_pdf_text(pdf_path)
    if not proposal_text.strip():
        raise ValueError(f"No readable text was extracted from {pdf_path}.")

    raw_result = evaluate_proposal(
        proposal_text=proposal_text,
        criteria=criteria,
    )

    validation_result = validate_and_normalize(raw_result, criteria)

    return {
        "rfp_run_id": rfp_run_id,
        "supplier_name": str(supplier_name).strip(),
        "submission_date": submission_date,
        "experience_rating": float(experience_rating),
        "criteria": validation_result["criteria"],
        "warnings": validation_result["warnings"],
        "risks": validation_result.get("risks", []),
        "overall_summary": validation_result.get("overall_summary", ""),
    }


def finalize_run(rfp_run_id, supplier_results):
    criteria = load_active_criteria()
    enriched_results = enrich_supplier_results(supplier_results, criteria)
    ranked_results = rank_suppliers(enriched_results)

    for result in ranked_results:
        save_supplier_result(
            rfp_run_id=rfp_run_id,
            supplier_name=result["supplier_name"],
            submission_date=result["submission_date"],
            experience_rating=result["experience_rating"],
            absolute_score=result["absolute_score"],
            ppi=result["ppi"],
            final_rank=result["final_rank"],
            result_json=json.dumps(result),
        )

    update_run_status(rfp_run_id, "COMPLETED")
    return ranked_results
