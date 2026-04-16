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
_FALLBACK_DEFAULT_MODEL = "gemini-2.5-flash"
_ALLOWED_EXACT_MODEL_NAMES = {
    "gemini-3.1-flash-lite-preview",
}
_ALLOWED_MODEL_PREFIXES = (
    "gemini-2.5-",
)


def _normalize_model_name(model_name: str) -> str:
    """Normalize model names so callers can pass either raw or `models/...` names."""
    model = (model_name or "").strip().lower()
    if model.startswith("models/"):
        return model.split("/", 1)[1]
    return model


def _is_allowed_model_name(model_name: str) -> bool:
    """Allow only Gemini 2.5 family or Gemini 3.1 Flash-Lite."""
    model = _normalize_model_name(model_name)
    if model in _ALLOWED_EXACT_MODEL_NAMES:
        return True
    return any(model.startswith(prefix) for prefix in _ALLOWED_MODEL_PREFIXES)


_configured_model = _normalize_model_name(os.getenv("MODEL_NAME", _FALLBACK_DEFAULT_MODEL))
_DEFAULT_MODEL_NAME = _configured_model if _is_allowed_model_name(_configured_model) else _FALLBACK_DEFAULT_MODEL
_ACTIVE_MODEL_NAME = _DEFAULT_MODEL_NAME
TEMPERATURE = float(os.getenv("TEMPERATURE", "0"))


def get_model_name() -> str:
    """Get the currently active model name (supports runtime switching on 503 errors)."""
    return _ACTIVE_MODEL_NAME


def set_model_name(model_name: str) -> None:
    """Set the active model name for all subsequent LLM calls."""
    global _ACTIVE_MODEL_NAME
    normalized_model = _normalize_model_name(model_name)
    if not _is_allowed_model_name(normalized_model):
        raise ValueError(
            "Unsupported model. Use Gemini 2.5 family or gemini-3.1-flash-lite-preview only."
        )
    _ACTIVE_MODEL_NAME = normalized_model


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
