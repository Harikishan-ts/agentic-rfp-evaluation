
import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path("data/rfp_evaluation.db")


DEFAULT_CRITERIA = [
    (
        1,
        "Technical Capability",
        "Ability of the proposed solution to meet technical requirements.",
        30.0,
        10.0,
        1,
    ),
    (
        2,
        "Implementation Plan",
        "Quality, feasibility, timeline, milestones, and delivery approach.",
        20.0,
        10.0,
        1,
    ),
    (
        3,
        "Commercial Value",
        "Value for money considering pricing, assumptions, and commercial terms.",
        20.0,
        10.0,
        1,
    ),
    (
        4,
        "Security & Compliance",
        "Security controls, privacy, compliance, and risk management.",
        20.0,
        10.0,
        1,
    ),
    (
        5,
        "Support & Experience",
        "Relevant experience, references, support model, and ongoing service.",
        10.0,
        10.0,
        1,
    ),
]


def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def initialize_database():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS evaluation_criteria (
            criterion_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT NOT NULL,
            weight REAL NOT NULL,
            max_score REAL NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS rfp_runs (
            rfp_run_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            status TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS supplier_results (
            rfp_run_id TEXT NOT NULL,
            supplier_name TEXT NOT NULL,
            submission_date TEXT NOT NULL,
            experience_rating REAL NOT NULL,
            absolute_score REAL,
            ppi REAL,
            final_rank INTEGER,
            result_json TEXT NOT NULL,
            PRIMARY KEY (rfp_run_id, supplier_name),
            FOREIGN KEY (rfp_run_id) REFERENCES rfp_runs(rfp_run_id)
        )
    """)

    conn.commit()
    conn.close()


def seed_criteria():
    conn = get_connection()
    cur = conn.cursor()

    count = cur.execute(
        "SELECT COUNT(*) FROM evaluation_criteria"
    ).fetchone()[0]

    if count == 0:
        cur.executemany("""
            INSERT INTO evaluation_criteria
            (criterion_id, name, description, weight, max_score, is_active)
            VALUES (?, ?, ?, ?, ?, ?)
        """, DEFAULT_CRITERIA)

    conn.commit()
    conn.close()


def load_active_criteria():
    conn = get_connection()
    rows = conn.execute("""
        SELECT criterion_id, name, description, weight, max_score, is_active
        FROM evaluation_criteria
        WHERE is_active = 1
        ORDER BY criterion_id
    """).fetchall()
    conn.close()

    return [
        {
            "criterion_id": row[0],
            "name": row[1],
            "description": row[2],
            "weight": row[3],
            "max_score": row[4],
            "is_active": row[5],
        }
        for row in rows
    ]


def create_run(rfp_run_id, status="RUNNING"):
    conn = get_connection()

    conn.execute("""
        INSERT INTO rfp_runs (rfp_run_id, created_at, status)
        VALUES (?, ?, ?)
    """, (
        rfp_run_id,
        datetime.utcnow().isoformat(),
        status,
    ))

    conn.commit()
    conn.close()


def update_run_status(rfp_run_id, status):
    conn = get_connection()

    conn.execute("""
        UPDATE rfp_runs
        SET status = ?
        WHERE rfp_run_id = ?
    """, (status, rfp_run_id))

    conn.commit()
    conn.close()


def save_supplier_result(
    rfp_run_id,
    supplier_name,
    submission_date,
    experience_rating,
    absolute_score,
    ppi,
    final_rank,
    result_json,
):
    conn = get_connection()

    conn.execute("""
        INSERT OR REPLACE INTO supplier_results
        (
            rfp_run_id,
            supplier_name,
            submission_date,
            experience_rating,
            absolute_score,
            ppi,
            final_rank,
            result_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        rfp_run_id,
        supplier_name,
        submission_date,
        experience_rating,
        absolute_score,
        ppi,
        final_rank,
        result_json,
    ))

    conn.commit()
    conn.close()


def get_supplier_results(rfp_run_id):
    conn = get_connection()

    rows = conn.execute("""
        SELECT
            supplier_name,
            submission_date,
            experience_rating,
            absolute_score,
            ppi,
            final_rank,
            result_json
        FROM supplier_results
        WHERE rfp_run_id = ?
        ORDER BY final_rank
    """, (rfp_run_id,)).fetchall()

    conn.close()

    return rows
