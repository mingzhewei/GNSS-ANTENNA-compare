# GNSS Antenna Compare - Windows Setup Script (PowerShell)
# This script sets up the complete environment for running the analysis on Windows.

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "GNSS Antenna Compare - Windows Setup" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# Check if Python is installed
try {
    $pythonVersion = python --version 2>&1
    Write-Host "[INFO] Python found: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Python is not installed or not in PATH." -ForegroundColor Red
    Write-Host "Please install Python 3.9 or later from https://www.python.org/downloads/" -ForegroundColor Yellow
    Write-Host "Make sure to check 'Add Python to PATH' during installation." -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}

# Check if pip is available
try {
    $pipVersion = pip --version 2>&1
    Write-Host "[INFO] pip found: $pipVersion" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] pip is not available." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host ""

# Create virtual environment
Write-Host "[INFO] Creating virtual environment..." -ForegroundColor Cyan
if (Test-Path .venv) {
    Write-Host "[INFO] Virtual environment already exists, skipping creation." -ForegroundColor Yellow
} else {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] Failed to create virtual environment." -ForegroundColor Red
        Read-Host "Press Enter to exit"
        exit 1
    }
    Write-Host "[INFO] Virtual environment created successfully." -ForegroundColor Green
}
Write-Host ""

# Activate virtual environment
Write-Host "[INFO] Activating virtual environment..." -ForegroundColor Cyan
& .venv\Scripts\Activate.ps1
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Failed to activate virtual environment." -ForegroundColor Red
    Write-Host "You may need to run: Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser" -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}
Write-Host ""

# Upgrade pip
Write-Host "[INFO] Upgrading pip..." -ForegroundColor Cyan
python -m pip install --upgrade pip
Write-Host ""

# Install dependencies
Write-Host "[INFO] Installing dependencies..." -ForegroundColor Cyan
pip install numpy pandas matplotlib pyyaml
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Failed to install dependencies." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}
Write-Host ""

# Verify installation
Write-Host "[INFO] Verifying installation..." -ForegroundColor Cyan
python -c "import numpy; import pandas; import matplotlib; import yaml; print('All dependencies installed successfully.')"
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Dependency verification failed." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}
Write-Host ""

Write-Host "==========================================" -ForegroundColor Green
Write-Host "Setup completed successfully!" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host ""
Write-Host "To run the analysis:" -ForegroundColor Cyan
Write-Host "  1. Activate the virtual environment:" -ForegroundColor White
Write-Host "     .venv\Scripts\Activate.ps1" -ForegroundColor Yellow
Write-Host ""
Write-Host "  2. Run the analysis:" -ForegroundColor White
Write-Host "     python scripts\run_analysis.py" -ForegroundColor Yellow
Write-Host ""
Write-Host "  3. View reports in the reports\ directory" -ForegroundColor White
Write-Host ""
Read-Host "Press Enter to exit"
