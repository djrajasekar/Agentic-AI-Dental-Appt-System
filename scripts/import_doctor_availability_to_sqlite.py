"""
****************************************
Import CSV data into the SQLite store.
****************************************
"""

from __future__ import annotations

import csv
import sqlite3
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
CSV_PATH = BASE_DIR / "doctor_availability.csv"
DB_PATH = BASE_DIR / "doctor_availability.db"
TABLE_NAME = "doctor_availability"

# ****************************************
# Normalizers keep imported CSV values SQLite-friendly.
# ****************************************
def normalize_bool(value: str) -> int:
    """Convert the CSV availability flag into the SQLite integer format used by the app."""
    return 1 if str(value).strip().upper() == "TRUE" else 0


def normalize_date_slot(value: str) -> str:
    """Store dates in a SQLite-friendly ISO format for reliable filtering."""
    text = str(value).strip()

    for fmt in ("%Y-%m-%d %H:%M:%S", "%m/%d/%Y %H:%M", "%m/%d/%Y %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue

    try:
        return datetime.fromisoformat(text).strftime("%Y-%m-%d %H:%M:%S")
    except ValueError as exc:
        raise ValueError(f"Unsupported date_slot format: {value}") from exc

# ****************************************
# Database rebuild logic refreshes the runtime store.
# ****************************************
def create_database() -> tuple[Path, int]:
    """Rebuild the SQLite file from the source CSV so the app starts from clean data."""
    if not CSV_PATH.exists():
        raise FileNotFoundError(f"CSV file not found: {CSV_PATH}")

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        # Recreate the table on each import so stale records do not survive data refreshes.
        cursor.execute(f"DROP TABLE IF EXISTS {TABLE_NAME}")
        cursor.execute(
            f"""
            CREATE TABLE {TABLE_NAME} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date_slot TEXT NOT NULL,
                specialization TEXT NOT NULL,
                doctor_name TEXT NOT NULL,
                is_available INTEGER NOT NULL CHECK (is_available IN (0, 1)),
                patient_to_attend TEXT
            )
            """
        )

        with CSV_PATH.open("r", newline="", encoding="utf-8") as csv_file:
            reader = csv.DictReader(csv_file)
            rows = [
                (
                    normalize_date_slot(row["date_slot"]),
                    row["specialization"].strip(),
                    row["doctor_name"].strip(),
                    normalize_bool(row["is_available"]),
                    (row.get("patient_to_attend") or "").strip() or None,
                )
                for row in reader
            ]

        cursor.executemany(
            f"""
            INSERT INTO {TABLE_NAME} (
                date_slot,
                specialization,
                doctor_name,
                is_available,
                patient_to_attend
            ) VALUES (?, ?, ?, ?, ?)
            """,
            rows,
        )

        # Add the most-used indexes so UI searches and tool lookups stay responsive.
        cursor.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_doctor_date ON {TABLE_NAME} (doctor_name, date_slot)"
        )
        cursor.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_specialization_available ON {TABLE_NAME} (specialization, is_available)"
        )
        conn.commit()

    return DB_PATH, len(rows)


if __name__ == "__main__":
    db_path, row_count = create_database()
    print(f"Created {db_path.name} with {row_count} imported rows in table '{TABLE_NAME}'.")
