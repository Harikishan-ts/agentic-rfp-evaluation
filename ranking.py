
from datetime import datetime


def calculate_absolute_score(criteria_results):
    """
    Absolute weighted score:

    sum((criterion score / max score) * weight)
    """

    total = 0.0

    for item in criteria_results:
        score = float(item["score"])
        max_score = float(item["max_score"])
        weight = float(item["weight"])

        if max_score <= 0:
            continue

        total += (score / max_score) * weight

    return round(total, 4)


def calculate_benchmarks(supplier_results, criteria):
    """
    Benchmark = highest valid score achieved by any supplier
    for each criterion.
    """

    benchmarks = {}

    for criterion in criteria:
        criterion_id = criterion["criterion_id"]

        scores = []

        for supplier in supplier_results:
            for item in supplier["criteria"]:
                if item["criterion_id"] == criterion_id:
                    score = float(item["score"])
                    max_score = float(item["max_score"])

                    if 0 <= score <= max_score:
                        scores.append(score)

        benchmarks[criterion_id] = (
            max(scores) if scores else 0.0
        )

    return benchmarks


def calculate_relative_performance(
    score,
    benchmark,
):
    """
    Relative performance:

    supplier score / benchmark * 100

    If benchmark is zero, return zero.
    """

    if benchmark == 0:
        return 0.0

    return (score / benchmark) * 100.0


def calculate_ppi(criteria_results, benchmarks):
    """
    Weighted Peer Performance Index.

    PPI is the weighted average of criterion-level
    relative performance.
    """

    weighted_total = 0.0
    weight_total = 0.0

    for item in criteria_results:
        criterion_id = item["criterion_id"]

        score = float(item["score"])
        weight = float(item["weight"])
        benchmark = float(
            benchmarks.get(criterion_id, 0.0)
        )

        relative = calculate_relative_performance(
            score,
            benchmark
        )

        weighted_total += relative * weight
        weight_total += weight

    if weight_total == 0:
        return 0.0

    return round(
        weighted_total / weight_total,
        4
    )


def enrich_supplier_results(
    supplier_results,
    criteria,
):
    """
    Add benchmark, gap, and relative performance
    to every criterion.
    """

    benchmarks = calculate_benchmarks(
        supplier_results,
        criteria
    )

    for supplier in supplier_results:

        for item in supplier["criteria"]:

            criterion_id = item["criterion_id"]

            score = float(item["score"])
            benchmark = float(
                benchmarks.get(criterion_id, 0.0)
            )

            item["benchmark"] = benchmark

            item["gap"] = round(
                score - benchmark,
                4
            )

            item["relative_performance"] = round(
                calculate_relative_performance(
                    score,
                    benchmark
                ),
                4
            )

        supplier["absolute_score"] = calculate_absolute_score(
            supplier["criteria"]
        )

        supplier["ppi"] = calculate_ppi(
            supplier["criteria"],
            benchmarks
        )

    return supplier_results


def ranking_key(supplier):
    """
    Deterministic tie-break order:

    1. Higher PPI
    2. Earlier submission date
    3. Higher historical experience
    4. Supplier name ascending
    """

    try:
        submission_date = datetime.strptime(
            supplier["submission_date"],
            "%Y-%m-%d"
        )
    except Exception:
        submission_date = datetime.max

    return (
        -float(supplier.get("ppi", 0.0)),
        submission_date,
        -float(supplier.get("experience_rating", 0.0)),
        supplier["supplier_name"].lower(),
    )


def rank_suppliers(supplier_results):
    """
    Sort suppliers according to the required
    deterministic tie-break rules.
    """

    ranked = sorted(
        supplier_results,
        key=ranking_key
    )

    for index, supplier in enumerate(
        ranked,
        start=1
    ):
        supplier["final_rank"] = index

    return ranked
