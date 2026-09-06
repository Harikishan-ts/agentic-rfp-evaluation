import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import load_active_criteria
from ranking import (
    calculate_absolute_score,
    calculate_benchmarks,
    calculate_ppi,
    calculate_relative_performance,
    rank_suppliers,
)
from tools import validate_and_normalize


def test_absolute_score():
    criteria = load_active_criteria()
    results = [{"criterion_id": c["criterion_id"], "score": 10, "max_score": c["max_score"], "weight": c["weight"]} for c in criteria]
    assert calculate_absolute_score(results) == 100.0


def test_benchmark():
    criteria = load_active_criteria()
    supplier_results = [
        {"supplier_name": "A", "criteria": [{"criterion_id": c["criterion_id"], "score": 7, "max_score": c["max_score"]} for c in criteria]},
        {"supplier_name": "B", "criteria": [{"criterion_id": c["criterion_id"], "score": 9, "max_score": c["max_score"]} for c in criteria]},
    ]
    benchmarks = calculate_benchmarks(supplier_results, criteria)
    assert all(value == 9 for value in benchmarks.values())


def test_relative_performance():
    assert calculate_relative_performance(8, 10) == 80.0
    assert calculate_relative_performance(8, 0) == 0.0


def test_ppi():
    criteria_results = [
        {"criterion_id": 1, "score": 8, "max_score": 10, "weight": 50},
        {"criterion_id": 2, "score": 10, "max_score": 10, "weight": 50},
    ]
    assert calculate_ppi(criteria_results, {1: 10, 2: 10}) == 90.0


def test_validation_fills_missing_criteria_and_clips_scores():
    criteria = load_active_criteria()
    raw = {"criteria": [{"criterion_id": criteria[0]["criterion_id"], "score": 999, "justification": "x", "evidence": ["e"]}]}
    result = validate_and_normalize(raw, criteria)
    assert len(result["criteria"]) == len(criteria)
    assert result["criteria"][0]["score"] == criteria[0]["max_score"]
    assert any("clipped" in w.lower() for w in result["warnings"])
    assert any("missing evaluation" in w.lower() for w in result["warnings"])


def test_deterministic_tie_break():
    suppliers = [
        {"supplier_name": "Beta", "ppi": 90, "submission_date": "2026-09-02", "experience_rating": 5},
        {"supplier_name": "Alpha", "ppi": 90, "submission_date": "2026-09-02", "experience_rating": 5},
    ]
    ranked = rank_suppliers(suppliers)
    assert [s["supplier_name"] for s in ranked] == ["Alpha", "Beta"]
    assert [s["final_rank"] for s in ranked] == [1, 2]
