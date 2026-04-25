@echo off
:: ****************************************
:: Launch script for Dental Agentic AI Assistant.
:: Always uses the project venv so langgraph and
:: all dependencies are guaranteed to be available.
:: ****************************************

set SCRIPT_DIR=%~dp0
set VENV_PYTHON=%SCRIPT_DIR%.venv\Scripts\python.exe

if not exist "%VENV_PYTHON%" (
    echo ERROR: Virtual environment not found at %VENV_PYTHON%
    echo Run: python -m venv .venv  then  .venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)

echo Starting Dental Agentic AI Assistant...
echo Using interpreter: %VENV_PYTHON%
echo.

"%VENV_PYTHON%" -m streamlit run "%SCRIPT_DIR%modern_clinic_ui.py"
