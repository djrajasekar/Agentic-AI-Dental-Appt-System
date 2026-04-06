"""
****************************************
SQLite write tools for booking changes.
****************************************
"""

from __future__ import annotations

import sqlite3
from contextlib import closing

import pandas as pd
from langchain_core.tools import tool

from dental_agent.config.settings import DB_PATH

# ****************************************
# Shared constants and private helpers support write tools.
# ****************************************
TABLE_NAME = "doctor_availability"


def _connect() -> sqlite3.Connection:
    """Open the shared database with dict-like rows so update logic is easy to follow."""
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"Database not found: {DB_PATH}. Run scripts/import_doctor_availability_to_sqlite.py first."
        )

    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def _parse_date_slot(value: str):
    """Normalize flexible date input before checking or updating appointment rows."""
    try:
        return pd.to_datetime(value, format="mixed", dayfirst=False).to_pydatetime()
    except Exception:
        return None


# ****************************************
# Public write tools change booking state in SQLite.
# ****************************************
@tool
def book_appointment(patient_id: str, doctor_name: str, date_slot: str) -> dict:
    """Book an appointment by updating the SQLite slot record.

    Args:
        patient_id: The patient identifier to attach to the booked slot.
        doctor_name: The doctor's name for the requested appointment.
        date_slot: The appointment date and time to reserve.

    Returns:
        dict: A status dictionary with `success` and `message` keys describing the result.
    """
    target_dt = _parse_date_slot(date_slot)
    if target_dt is None:
        return {"success": False, "message": f"Invalid date_slot format: {date_slot}"}

    query = f"""
        SELECT id, is_available
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
            return {"success": False, "message": "Slot not found for this doctor."}
        if not bool(row["is_available"]):
            return {"success": False, "message": "Slot is already booked."}

        conn.execute(
            f"""
            UPDATE {TABLE_NAME}
            SET is_available = 0, patient_to_attend = ?
            WHERE id = ?
            """,
            (str(patient_id).strip(), row["id"]),
        )
        conn.commit()

    return {
        "success": True,
        "message": f"Appointment booked for patient {patient_id} with {doctor_name} at {date_slot}.",
    }


@tool
def cancel_appointment(patient_id: str, date_slot: str) -> dict:
    """Cancel an appointment by freeing the SQLite slot record.

    Args:
        patient_id: The patient identifier tied to the booking.
        date_slot: The appointment date and time that should be cancelled.

    Returns:
        dict: A status dictionary with `success` and `message` keys describing the result.
    """
    target_dt = _parse_date_slot(date_slot)
    if target_dt is None:
        return {"success": False, "message": f"Invalid date_slot format: {date_slot}"}

    query = f"""
        SELECT id
        FROM {TABLE_NAME}
        WHERE TRIM(COALESCE(patient_to_attend, '')) = ?
          AND datetime(date_slot) = datetime(?)
          AND is_available = 0
        LIMIT 1
    """

    with closing(_connect()) as conn:
        row = conn.execute(
            query,
            (str(patient_id).strip(), target_dt.strftime("%Y-%m-%d %H:%M:%S")),
        ).fetchone()

        if row is None:
            return {
                "success": False,
                "message": f"No booked appointment found for patient {patient_id} at {date_slot}.",
            }

        conn.execute(
            f"""
            UPDATE {TABLE_NAME}
            SET is_available = 1, patient_to_attend = NULL
            WHERE id = ?
            """,
            (row["id"],),
        )
        conn.commit()

    return {
        "success": True,
        "message": f"Appointment at {date_slot} for patient {patient_id} has been cancelled.",
    }


@tool
def reschedule_appointment(
    patient_id: str,
    current_date_slot: str,
    new_date_slot: str,
    doctor_name: str,
) -> dict:
    """Reschedule an appointment by updating the old and new SQLite slots together.

    Args:
        patient_id: The patient identifier for the booking being moved.
        current_date_slot: The currently booked appointment date and time.
        new_date_slot: The new date and time the patient wants instead.
        doctor_name: The doctor associated with the target slot.

    Returns:
        dict: A status dictionary with `success` and `message` keys describing the result.
    """
    current_dt = _parse_date_slot(current_date_slot)
    new_dt = _parse_date_slot(new_date_slot)
    if current_dt is None or new_dt is None:
        return {"success": False, "message": "Invalid date format for the requested reschedule."}

    patient_value = str(patient_id).strip()
    doctor_value = doctor_name.lower().strip()

    with closing(_connect()) as conn:
        old_row = conn.execute(
            f"""
            SELECT id
            FROM {TABLE_NAME}
            WHERE TRIM(COALESCE(patient_to_attend, '')) = ?
              AND datetime(date_slot) = datetime(?)
              AND is_available = 0
            LIMIT 1
            """,
            (patient_value, current_dt.strftime("%Y-%m-%d %H:%M:%S")),
        ).fetchone()

        if old_row is None:
            return {
                "success": False,
                "message": f"No existing booking found for patient {patient_value} at {current_date_slot}.",
            }

        new_row = conn.execute(
            f"""
            SELECT id, is_available
            FROM {TABLE_NAME}
            WHERE lower(doctor_name) = ?
              AND datetime(date_slot) = datetime(?)
            LIMIT 1
            """,
            (doctor_value, new_dt.strftime("%Y-%m-%d %H:%M:%S")),
        ).fetchone()

        if new_row is None:
            return {"success": False, "message": f"Slot {new_date_slot} does not exist for {doctor_name}."}
        if not bool(new_row["is_available"]):
            return {"success": False, "message": f"Slot {new_date_slot} is already taken."}

        # Free the old slot first, then claim the new one inside the same transaction.
        conn.execute(
            f"""
            UPDATE {TABLE_NAME}
            SET is_available = 1, patient_to_attend = NULL
            WHERE id = ?
            """,
            (old_row["id"],),
        )
        conn.execute(
            f"""
            UPDATE {TABLE_NAME}
            SET is_available = 0, patient_to_attend = ?
            WHERE id = ?
            """,
            (patient_value, new_row["id"]),
        )
        conn.commit()

    return {
        "success": True,
        "message": (
            f"Appointment for patient {patient_value} rescheduled from "
            f"{current_date_slot} to {new_date_slot} with {doctor_name}."
        ),
    }
