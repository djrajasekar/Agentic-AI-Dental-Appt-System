"""
****************************************
SQLite read tools for appointment lookups.
****************************************
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import date

import pandas as pd
from langchain_core.tools import tool

from dental_agent.config.settings import DB_PATH

# ****************************************
# Shared constants and private helpers support read-only tools.
# ****************************************
TABLE_NAME = "doctor_availability"


def _connect() -> sqlite3.Connection:
    """Open the shared database with dict-like rows so the tool code stays readable."""
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"Database not found: {DB_PATH}. Run scripts/import_doctor_availability_to_sqlite.py first."
        )

    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def _parse_date_slot(value: str):
    """Accept flexible user date formats and normalize them for SQLite comparisons."""
    try:
        return pd.to_datetime(value, format="mixed", dayfirst=False).to_pydatetime()
    except Exception:
        return None


def _normalize_specialization(value: str) -> str:
    """Tolerate spaces, hyphens, and plurals from natural-language requests."""
    normalized = str(value).strip().lower().replace("_", " ").replace("-", " ")
    normalized = " ".join(normalized.split())
    if normalized.endswith("s"):
        normalized = normalized[:-1]
    return normalized.replace(" ", "_")


def _format_date_slot(value: str) -> str:
    parsed = _parse_date_slot(value)
    if parsed is None:
        return str(value)
    return f"{parsed.month}/{parsed.day}/{parsed.year} {parsed.hour}:{parsed.minute:02d}"


# ****************************************
# Public read tools expose appointment lookup behavior.
# ****************************************
@tool
def get_available_slots(
    specialization: str = "",
    doctor_name: str = "",
    date_filter: str = "",
) -> list:
    """Return available appointment slots from SQLite.

    Args:
        specialization: Optional dentist specialty filter such as `orthodontist`.
        doctor_name: Optional doctor name filter for narrowing the results.
        date_filter: Optional date text used to match one day of appointments.

    Returns:
        list: A list of dictionaries containing `date_slot`, `specialization`, and `doctor_name`.
    """
    # Default to future-facing open slots so the agent never suggests expired times.
    clauses = ["is_available = 1", "date(date_slot) >= ?"]
    params: list[object] = [date.today().isoformat()]

    if specialization:
        clauses.append("lower(specialization) = ?")
        params.append(_normalize_specialization(specialization))
    if doctor_name:
        clauses.append("lower(doctor_name) = ?")
        params.append(doctor_name.lower().strip())
    if date_filter:
        parsed_date = _parse_date_slot(date_filter)
        if parsed_date is not None:
            clauses.append("date(date_slot) = ?")
            params.append(parsed_date.date().isoformat())

    query = f"""
        SELECT date_slot, specialization, doctor_name
        FROM {TABLE_NAME}
        WHERE {' AND '.join(clauses)}
        ORDER BY datetime(date_slot), doctor_name
        LIMIT 20
    """

    with closing(_connect()) as conn:
        rows = conn.execute(query, params).fetchall()

    return [
        {
            "date_slot": _format_date_slot(row["date_slot"]),
            "specialization": row["specialization"],
            "doctor_name": row["doctor_name"],
        }
        for row in rows
    ]


@tool
def get_patient_appointments(patient_id: str) -> list:
    """Return booked appointments for a patient from SQLite.

    Args:
        patient_id: The patient identifier used to find booked slots.

    Returns:
        list: A list of appointment dictionaries for the patient, or an empty list when none are found.
    """
    patient_value = str(patient_id or "").strip()
    if not patient_value:
        return []

    query = f"""
        SELECT date_slot, specialization, doctor_name, COALESCE(patient_to_attend, '') AS patient_to_attend
        FROM {TABLE_NAME}
        WHERE TRIM(COALESCE(patient_to_attend, '')) = ?
        ORDER BY datetime(date_slot)
    """

    with closing(_connect()) as conn:
        rows = conn.execute(query, (patient_value,)).fetchall()

    return [
        {
            "date_slot": _format_date_slot(row["date_slot"]),
            "specialization": row["specialization"],
            "doctor_name": row["doctor_name"],
            "patient_to_attend": row["patient_to_attend"],
        }
        for row in rows
    ]


@tool
def check_slot_availability(doctor_name: str, date_slot: str) -> dict:
    """Check whether a specific doctor slot is still available in SQLite.

    Args:
        doctor_name: The doctor's name for the slot being checked.
        date_slot: The requested appointment date and time.

    Returns:
        dict: A status dictionary with `found`, `is_available`, and `patient_to_attend` keys.
    """
    target_dt = _parse_date_slot(date_slot)
    if target_dt is None:
        return {"found": False, "is_available": False, "patient_to_attend": ""}

    query = f"""
        SELECT is_available, COALESCE(patient_to_attend, '') AS patient_to_attend
        FROM {TABLE_NAME}
        WHERE lower(doctor_name) = ?
          AND datetime(date_slot) = datetime(?)
        LIMIT 1
    """

    with closing(_connect()) as conn:
        row = conn.execute(
            query,
            (doctor_name.lower().strip(), target_dt.strftime("%Y-%m-%d %H:%M:%S")),
        ).fetchone()

    if row is None:
        return {"found": False, "is_available": False, "patient_to_attend": ""}

    return {
        "found": True,
        "is_available": bool(row["is_available"]),
        "patient_to_attend": row["patient_to_attend"],
    }


@tool
def list_doctors_by_specialization(specialization: str) -> list:
    """Return doctor names for a specialization from SQLite.

    Args:
        specialization: The dentist specialty to look up.

    Returns:
        list: A sorted list of doctor names that match the specialization.
    """
    query = f"""
        SELECT DISTINCT doctor_name
        FROM {TABLE_NAME}
        WHERE lower(specialization) = ?
        ORDER BY doctor_name
    """

    with closing(_connect()) as conn:
        rows = conn.execute(query, (_normalize_specialization(specialization),)).fetchall()

    return [row["doctor_name"] for row in rows]
