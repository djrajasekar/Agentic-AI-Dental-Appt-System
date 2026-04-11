"""
****************************************
Regression tests for the SQLite tools.
****************************************
"""

from __future__ import annotations

import shutil
import sqlite3
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from dental_agent.tools import sqllite_reader, sqllite_writer

# ****************************************
# Regression tests cover read and write tool behavior.
# ****************************************
class SQLiteToolsTests(unittest.TestCase):
    """Exercise the SQLite-backed appointment tools with isolated test data."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.repo_root = Path(__file__).resolve().parents[1]
        cls.source_db = cls.repo_root / "doctor_availability.db"
        if not cls.source_db.exists():
            raise FileNotFoundError(
                f"Database not found: {cls.source_db}. Run scripts/import_doctor_availability_to_sqlite.py first."
            )

    # ****************************************
    # Test fixtures isolate database mutations per test.
    # ****************************************
    def setUp(self) -> None:
        # Each test gets its own copied database so booking changes never touch the real app data.
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.temp_db = Path(self.temp_dir.name) / "doctor_availability.db"
        shutil.copy(self.source_db, self.temp_db)

        self.original_reader_db = sqllite_reader.DB_PATH
        self.original_writer_db = sqllite_writer.DB_PATH
        sqllite_reader.DB_PATH = self.temp_db
        sqllite_writer.DB_PATH = self.temp_db

    def tearDown(self) -> None:
        sqllite_reader.DB_PATH = self.original_reader_db
        sqllite_writer.DB_PATH = self.original_writer_db
        self.temp_dir.cleanup()

    def _fetch_rows(self, query: str, params: tuple = ()):
        """Run direct SQL against the isolated test database when a test needs setup or verification."""
        with sqlite3.connect(self.temp_db) as conn:
            conn.row_factory = sqlite3.Row
            return conn.execute(query, params).fetchall()

    def _fetch_one(self, query: str, params: tuple = ()):
        """Return one required setup row and fail loudly if the fixture data is missing."""
        rows = self._fetch_rows(query, params)
        self.assertTrue(rows, "Expected at least one matching row in the temp database.")
        return rows[0]

    # ****************************************
    # Happy path tests confirm expected successful flows.
    # ****************************************
    def test_get_available_slots_returns_matching_emergency_dentist(self) -> None:
        row = self._fetch_one(
            """
            SELECT date_slot, doctor_name
            FROM doctor_availability
            WHERE specialization = 'emergency_dentist'
              AND doctor_name = 'susan davis'
              AND is_available = 1
              AND date(date_slot) >= ?
            ORDER BY datetime(date_slot)
            LIMIT 1
            """,
            (datetime.now().date().isoformat(),),
        )
        parsed = datetime.fromisoformat(row["date_slot"])
        date_filter = f"{parsed.month}/{parsed.day}/{parsed.year}"
        expected_slot = sqllite_reader._format_date_slot(row["date_slot"])

        results = sqllite_reader.get_available_slots.invoke(
            {"specialization": "emergency dentists", "date_filter": date_filter}
        )

        self.assertTrue(results)
        self.assertTrue(
            any(item["doctor_name"] == "susan davis" and item["date_slot"] == expected_slot for item in results)
        )

    def test_show_available_slots_for_orthodontist_returns_only_today_or_future(self) -> None:
        with sqlite3.connect(self.temp_db) as conn:
            conn.execute(
                """
                INSERT INTO doctor_availability (
                    date_slot, specialization, doctor_name, is_available, patient_to_attend
                ) VALUES (?, ?, ?, ?, ?)
                """,
                ("2025-01-01 09:00:00", "orthodontist", "future filter test", 1, None),
            )
            conn.commit()

        results = sqllite_reader.get_available_slots.invoke({"specialization": "orthodontist"})

        self.assertTrue(results)
        today = datetime.now().date()
        for item in results:
            slot_date = datetime.strptime(item["date_slot"], "%m/%d/%Y %H:%M").date()
            self.assertGreaterEqual(slot_date, today)

    def test_book_reschedule_and_cancel_round_trip(self) -> None:
        doctor_row = self._fetch_one(
            """
            SELECT doctor_name
            FROM doctor_availability
            WHERE is_available = 1
            GROUP BY doctor_name
            HAVING COUNT(*) >= 2
            ORDER BY doctor_name
            LIMIT 1
            """
        )
        doctor_name = doctor_row["doctor_name"]
        slots = self._fetch_rows(
            """
            SELECT date_slot
            FROM doctor_availability
            WHERE doctor_name = ? AND is_available = 1
            ORDER BY datetime(date_slot)
            LIMIT 2
            """,
            (doctor_name,),
        )
        self.assertEqual(len(slots), 2)

        first_slot = sqllite_reader._format_date_slot(slots[0]["date_slot"])
        second_slot = sqllite_reader._format_date_slot(slots[1]["date_slot"])

        booked = sqllite_writer.book_appointment.invoke(
            {"patient_id": "TEST9001", "doctor_name": doctor_name, "date_slot": first_slot}
        )
        self.assertTrue(booked["success"])

        moved = sqllite_writer.reschedule_appointment.invoke(
            {
                "patient_id": "TEST9001",
                "current_date_slot": first_slot,
                "new_date_slot": second_slot,
                "doctor_name": doctor_name,
            }
        )
        self.assertTrue(moved["success"])

        patient_rows = sqllite_reader.get_patient_appointments.invoke({"patient_id": "TEST9001"})
        self.assertEqual(len(patient_rows), 1)
        self.assertEqual(patient_rows[0]["date_slot"], second_slot)

        cancelled = sqllite_writer.cancel_appointment.invoke(
            {"patient_id": "TEST9001", "date_slot": second_slot}
        )
        self.assertTrue(cancelled["success"])

        after_cancel = sqllite_reader.check_slot_availability.invoke(
            {"doctor_name": doctor_name, "date_slot": second_slot}
        )
        self.assertTrue(after_cancel["found"])
        self.assertTrue(after_cancel["is_available"])

    # ****************************************
    # Edge-case tests protect boundary and blank-input behavior.
    # ****************************************
    def test_get_available_slots_with_empty_filters_returns_capped_rows(self) -> None:
        results = sqllite_reader.get_available_slots.invoke(
            {"specialization": "", "doctor_name": "", "date_filter": ""}
        )

        self.assertTrue(results)
        self.assertLessEqual(len(results), 20)

    def test_get_available_slots_with_part_of_day_filters_to_morning_only(self) -> None:
        row = self._fetch_one(
            """
            SELECT date_slot, specialization, doctor_name
            FROM doctor_availability
            WHERE is_available = 1
              AND time(date_slot) >= '05:00:00'
              AND time(date_slot) < '12:00:00'
              AND date(date_slot) >= ?
            ORDER BY datetime(date_slot)
            LIMIT 1
            """,
            (datetime.now().date().isoformat(),),
        )
        parsed = datetime.fromisoformat(row["date_slot"])

        results = sqllite_reader.get_available_slots.invoke(
            {
                "specialization": row["specialization"],
                "doctor_name": row["doctor_name"],
                "date_filter": f"{parsed.month}/{parsed.day}/{parsed.year}",
                "part_of_day": "morning",
            }
        )

        self.assertTrue(results)
        for item in results:
            hour = datetime.strptime(item["date_slot"], "%m/%d/%Y %H:%M").hour
            self.assertGreaterEqual(hour, 5)
            self.assertLess(hour, 12)

    def test_get_patient_appointments_with_blank_input_returns_empty_list(self) -> None:
        results = sqllite_reader.get_patient_appointments.invoke({"patient_id": ""})
        self.assertEqual(results, [])

    # ****************************************
    # Error-handling tests confirm clear failure responses.
    # ****************************************
    def test_check_slot_availability_with_invalid_date_returns_not_found(self) -> None:
        result = sqllite_reader.check_slot_availability.invoke(
            {"doctor_name": "susan davis", "date_slot": "not-a-real-date"}
        )

        self.assertEqual(result, {"found": False, "is_available": False, "patient_to_attend": ""})

    def test_book_appointment_with_invalid_date_fails_cleanly(self) -> None:
        result = sqllite_writer.book_appointment.invoke(
            {"patient_id": "1000001", "doctor_name": "susan davis", "date_slot": "bad-date"}
        )

        self.assertFalse(result["success"])
        self.assertIn("Invalid date_slot format", result["message"])

    def test_book_first_available_appointment_books_earliest_matching_morning_slot(self) -> None:
        row = self._fetch_one(
            """
            SELECT date_slot, specialization, doctor_name
            FROM doctor_availability
            WHERE is_available = 1
              AND time(date_slot) >= '05:00:00'
              AND time(date_slot) < '12:00:00'
              AND date(date_slot) >= ?
            ORDER BY datetime(date_slot), doctor_name
            LIMIT 1
            """,
            (datetime.now().date().isoformat(),),
        )
        parsed = datetime.fromisoformat(row["date_slot"])
        expected_slot = sqllite_reader._format_date_slot(row["date_slot"])

        result = sqllite_writer.book_first_available_appointment.invoke(
            {
                "patient_id": "FLEX1001",
                "specialization": row["specialization"],
                "doctor_name": row["doctor_name"],
                "date_filter": f"{parsed.month}/{parsed.day}/{parsed.year}",
                "part_of_day": "morning",
            }
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["doctor_name"], row["doctor_name"])
        self.assertEqual(result["date_slot"], expected_slot)

        availability = sqllite_reader.check_slot_availability.invoke(
            {"doctor_name": row["doctor_name"], "date_slot": expected_slot}
        )
        self.assertTrue(availability["found"])
        self.assertFalse(availability["is_available"])
        self.assertEqual(availability["patient_to_attend"], "FLEX1001")

    def test_book_first_available_appointment_returns_clear_failure_when_no_match_exists(self) -> None:
        result = sqllite_writer.book_first_available_appointment.invoke(
            {
                "patient_id": "FLEX404",
                "specialization": "general dentist",
                "doctor_name": "john doe",
                "date_filter": "4/11/2026",
                "part_of_day": "morning",
            }
        )

        self.assertFalse(result["success"])
        self.assertIn("No available slot found on 4/11/2026", result["message"])

    def test_cancel_missing_booking_returns_expected_failure(self) -> None:
        result = sqllite_writer.cancel_appointment.invoke(
            {"patient_id": "DOES_NOT_EXIST", "date_slot": "4/9/2026 8:30"}
        )

        self.assertFalse(result["success"])
        self.assertIn("No booked appointment found", result["message"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
