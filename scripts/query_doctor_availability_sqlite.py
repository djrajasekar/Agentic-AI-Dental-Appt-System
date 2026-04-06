"""
****************************************
SQLite query helper for appointment lookups.
****************************************
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DB_PATH = BASE_DIR / "doctor_availability.db"
TABLE_NAME = "doctor_availability"

# ****************************************
# Connection helpers keep manual DB inspection simple.
# ****************************************
def get_connection() -> sqlite3.Connection:
    """Open the local SQLite database and return rows by name."""
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"Database not found: {DB_PATH}. Run scripts/import_doctor_availability_to_sqlite.py first."
        )

    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def fetch_rows(query: str, params: tuple = ()) -> list[sqlite3.Row]:
    """Run a read-only query and return the matching rows."""
    with get_connection() as conn:
        cursor = conn.execute(query, params)
        return cursor.fetchall()


def print_section(title: str, rows: list[sqlite3.Row]) -> None:
    """Show query results in a simple terminal-friendly format."""
    print(f"\n=== {title} ===")
    if not rows:
        print("No rows found.")
        return

    for row in rows:
        print(dict(row))


def select_all(limit: int) -> list[sqlite3.Row]:
    """Preview the table with a small row sample."""
    return fetch_rows(
        f"""
        SELECT id, date_slot, specialization, doctor_name, is_available, patient_to_attend
        FROM {TABLE_NAME}
        ORDER BY date_slot, doctor_name
        LIMIT ?
        """,
        (limit,),
    )


def select_available_slots(limit: int) -> list[sqlite3.Row]:
    """Show open appointment slots across all doctors."""
    return fetch_rows(
        f"""
        SELECT date_slot, specialization, doctor_name
        FROM {TABLE_NAME}
        WHERE is_available = 1
        ORDER BY date_slot, doctor_name
        LIMIT ?
        """,
        (limit,),
    )


def select_by_doctor(doctor_name: str, limit: int) -> list[sqlite3.Row]:
    """Filter appointments for a specific doctor."""
    return fetch_rows(
        f"""
        SELECT date_slot, specialization, is_available, patient_to_attend
        FROM {TABLE_NAME}
        WHERE lower(doctor_name) = lower(?)
        ORDER BY date_slot
        LIMIT ?
        """,
        (doctor_name, limit),
    )


def select_by_specialization(specialization: str, limit: int) -> list[sqlite3.Row]:
    """Filter appointments for one specialization."""
    return fetch_rows(
        f"""
        SELECT date_slot, doctor_name, is_available, patient_to_attend
        FROM {TABLE_NAME}
        WHERE lower(specialization) = lower(?)
        ORDER BY date_slot, doctor_name
        LIMIT ?
        """,
        (specialization, limit),
    )


def select_by_patient(patient_id: str) -> list[sqlite3.Row]:
    """Look up booked appointments for one patient."""
    return fetch_rows(
        f"""
        SELECT date_slot, specialization, doctor_name
        FROM {TABLE_NAME}
        WHERE patient_to_attend = ?
        ORDER BY date_slot
        """,
        (patient_id,),
    )


def select_summary() -> list[sqlite3.Row]:
    """Return an availability summary by specialization."""
    return fetch_rows(
        f"""
        SELECT
            specialization,
            COUNT(*) AS total_slots,
            SUM(CASE WHEN is_available = 1 THEN 1 ELSE 0 END) AS available_slots,
            SUM(CASE WHEN is_available = 0 THEN 1 ELSE 0 END) AS booked_slots
        FROM {TABLE_NAME}
        GROUP BY specialization
        ORDER BY specialization
        """
    )

# ****************************************
# Query dispatch and CLI parsing drive the helper script.
# ****************************************
def run_query(query_type: str, limit: int, doctor: str, specialization: str, patient: str) -> None:
    """Route the CLI request to the matching example query so manual DB checks stay simple."""
    if query_type == "all":
        print_section("Sample Rows", select_all(limit))
    elif query_type == "available":
        print_section("Available Slots", select_available_slots(limit))
    elif query_type == "doctor":
        print_section(f"Appointments for Dr. {doctor}", select_by_doctor(doctor, limit))
    elif query_type == "specialization":
        print_section(
            f"Appointments for {specialization}",
            select_by_specialization(specialization, limit),
        )
    elif query_type == "patient":
        print_section(f"Appointments for patient {patient}", select_by_patient(patient))
    elif query_type == "summary":
        print_section("Availability Summary", select_summary())
    else:
        print_section("Sample Rows", select_all(limit))
        print_section("Available Slots", select_available_slots(limit))
        print_section(f"Appointments for Dr. {doctor}", select_by_doctor(doctor, limit))
        print_section(
            f"Appointments for {specialization}",
            select_by_specialization(specialization, limit),
        )
        print_section(f"Appointments for patient {patient}", select_by_patient(patient))
        print_section("Availability Summary", select_summary())


def build_parser() -> argparse.ArgumentParser:
    """Create a small CLI for the SELECT examples."""
    parser = argparse.ArgumentParser(description="Query doctor_availability.db with common SELECT examples.")
    parser.add_argument(
        "--query-type",
        choices=["all", "available", "doctor", "specialization", "patient", "summary", "examples"],
        default="examples",
        help="Choose which SELECT example to run.",
    )
    parser.add_argument("--limit", type=int, default=5, help="Limit the number of returned rows where supported.")
    parser.add_argument("--doctor", default="john doe", help="Doctor name for the doctor filter.")
    parser.add_argument(
        "--specialization",
        default="orthodontist",
        help="Specialization value for the specialization filter.",
    )
    parser.add_argument("--patient", default="1000048", help="Patient ID for the patient filter.")
    return parser


if __name__ == "__main__":
    args = build_parser().parse_args()
    run_query(args.query_type, args.limit, args.doctor, args.specialization, args.patient)
