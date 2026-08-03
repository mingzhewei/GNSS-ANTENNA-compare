@echo off
REM GNSS Antenna Compare - Windows Setup Script
REM This script sets up the complete environment for running the analysis on Windows.

setlocal enabledelayedexpansion

echo ==========================================
echo GNSS Antenna Compare - Windows Setup
echo ==========================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python 3.9 or later from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

echo [INFO] Python found:
python --version
echo.

REM Check if pip is available
pip --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] pip is not available.
    echo Please ensure pip is installed with Python.
    pause
    exit /b 1
)

echo [INFO] pip found:
pip --version
echo.

REM Create virtual environment
echo [INFO] Creating virtual environment...
if exist .venv (
    echo [INFO] Virtual environment already exists, skipping creation.
) else (
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo [INFO] Virtual environment created successfully.
)
echo.

REM Activate virtual environment
echo [INFO] Activating virtual environment...
call .venv\Scripts\activate.bat
if %errorlevel% neq 0 (
    echo [ERROR] Failed to activate virtual environment.
    pause
    exit /b 1
)
echo.

REM Upgrade pip
echo [INFO] Upgrading pip...
python -m pip install --upgrade pip
echo.

REM Install dependencies
echo [INFO] Installing dependencies...
pip install numpy pandas matplotlib pyyaml
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)
echo.

REM Verify installation
echo [INFO] Verifying installation...
python -c "import numpy; import pandas; import matplotlib; import yaml; print('All dependencies installed successfully.')"
if %errorlevel% neq 0 (
    echo [ERROR] Dependency verification failed.
    pause
    exit /b 1
)
echo.

echo ==========================================
echo Setup completed successfully!
echo ==========================================
echo.
echo To run the analysis:
echo   1. Activate the virtual environment:
echo      .venv\Scripts\activate.bat
echo.
echo   2. Run the analysis:
echo      python scripts\run_analysis.py
echo.
echo   3. View reports in the reports\ directory
echo.
pause
