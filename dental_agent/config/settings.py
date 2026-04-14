"""
****************************************
Shared runtime settings for the dental app.
****************************************
"""

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*_args, **_kwargs):
        return False

try:
    import truststore
except ImportError:
    truststore = None

# ****************************************
# Load shared environment values once for the app.
# ****************************************
load_dotenv(override=True)


# ****************************************
# SSL bootstrap prefers the Windows trust store for outbound HTTPS.
# ****************************************
def configure_ssl() -> None:
    """Use the OS certificate store when truststore is available."""
    if truststore is None:
        return

    try:
        truststore.inject_into_ssl()
    except Exception:
        # Fall back to Python's default SSL behavior if truststore injection fails.
        return


configure_ssl()

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
_DEFAULT_MODEL_NAME = os.getenv("MODEL_NAME", "gemini-2.5-flash")
_ACTIVE_MODEL_NAME = _DEFAULT_MODEL_NAME
TEMPERATURE = float(os.getenv("TEMPERATURE", "0"))


def get_model_name() -> str:
    """Get the currently active model name (supports runtime switching on 503 errors)."""
    return _ACTIVE_MODEL_NAME


def set_model_name(model_name: str) -> None:
    """Set the active model name for all subsequent LLM calls."""
    global _ACTIVE_MODEL_NAME
    _ACTIVE_MODEL_NAME = model_name


# Maintain backward compatibility with direct MODEL_NAME access
MODEL_NAME = _DEFAULT_MODEL_NAME

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
