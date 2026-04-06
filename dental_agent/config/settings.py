"""
****************************************
Shared runtime settings for the dental app.
****************************************
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# ****************************************
# Load shared environment values once for the app.
# ****************************************
load_dotenv()

# ****************************************
# Path settings keep file access consistent across entrypoints.
# ****************************************
BASE_DIR = Path(__file__).resolve().parent.parent.parent  # Keeps paths stable across entrypoints.
CSV_PATH = str(BASE_DIR / "doctor_availability.csv")
DB_PATH = BASE_DIR / "doctor_availability.db"

# ****************************************
# Model settings centralize runtime configuration.
# ****************************************
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY", "")
MODEL_NAME = os.getenv("MODEL_NAME", "gemini-2.5-flash")
TEMPERATURE = float(os.getenv("TEMPERATURE", "0"))

# ****************************************
# Domain lists keep validation and UI choices aligned.
# ****************************************
VALID_SPECIALIZATIONS = [
    "general_dentist",
    "oral_surgeon",
    "orthodontist",
    "cosmetic_dentist",
    "prosthodontist",
    "pediatric_dentist",
    "emergency_dentist",
]

VALID_DOCTORS = [
    "john doe",
    "emily johnson",
    "sarah wilson",
    "jane smith",
    "michael green",
    "robert martinez",
    "lisa brown",
    "susan davis",
    "daniel miller",
    "kevin anderson",
]

DATE_FORMAT = "%m/%d/%Y %H:%M"
