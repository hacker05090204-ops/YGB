# Phase-49 Installer - Windows
# 
# This script installs dependencies for the Phase-49 browser engine.
# It ALWAYS asks for user permission before installing anything.

param(
    [switch]$Force
)

Write-Host "========================================"
Write-Host "Phase-49 Installer - Windows"
Write-Host "========================================"
Write-Host ""

# Function to ask user permission
function Ask-Permission {
    param([string]$Component)
    
    if ($Force) {
        return $true
    }
    
    $response = Read-Host "Install $Component? [y/N]"
    return ($response -eq 'y' -or $response -eq 'Y')
}

# Check for Python
Write-Host "Checking Python..."
$python = Get-Command python -ErrorAction SilentlyContinue
if ($python) {
    $version = & python --version 2>&1
    Write-Host "✓ Found: $version" -ForegroundColor Green
} else {
    Write-Host "✗ Python not found" -ForegroundColor Red
    if (Ask-Permission "Python 3") {
        Write-Host "Please download Python from https://www.python.org/downloads/"
        Write-Host "Make sure to check 'Add Python to PATH' during installation."
        Start-Process "https://www.python.org/downloads/"
        Read-Host "Press Enter after installing Python"
    }
}

# Check for pip
Write-Host ""
Write-Host "Checking pip..."
$pip = Get-Command pip -ErrorAction SilentlyContinue
if ($pip) {
    Write-Host "✓ Found pip" -ForegroundColor Green
} else {
    Write-Host "✗ pip not found" -ForegroundColor Red
    if (Ask-Permission "pip") {
        & python -m ensurepip --upgrade
    }
}

# Check for pytest
Write-Host ""
Write-Host "Checking pytest..."
try {
    & python -c "import pytest" 2>$null
    Write-Host "✓ Found pytest" -ForegroundColor Green
} catch {
    Write-Host "✗ pytest not found" -ForegroundColor Red
    if (Ask-Permission "pytest") {
        & pip install pytest pytest-cov
    }
}

# Check for Visual Studio Build Tools
Write-Host ""
Write-Host "Checking C++ compiler (MSVC)..."
$vsWhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
if (Test-Path $vsWhere) {
    $vsPath = & $vsWhere -latest -property installationPath
    if ($vsPath) {
        Write-Host "✓ Found Visual Studio at $vsPath" -ForegroundColor Green
    } else {
        Write-Host "✗ Visual Studio not found" -ForegroundColor Red
    }
} else {
    Write-Host "✗ Visual Studio not found" -ForegroundColor Red
    if (Ask-Permission "Visual Studio Build Tools") {
        Write-Host "Download from: https://visualstudio.microsoft.com/downloads/"
        Write-Host "Select 'Desktop development with C++' workload"
        Start-Process "https://visualstudio.microsoft.com/downloads/"
    }
}

# Check for CMake
Write-Host ""
Write-Host "Checking CMake..."
$cmake = Get-Command cmake -ErrorAction SilentlyContinue
if ($cmake) {
    $version = & cmake --version | Select-Object -First 1
    Write-Host "✓ Found: $version" -ForegroundColor Green
} else {
    Write-Host "✗ CMake not found" -ForegroundColor Red
    if (Ask-Permission "CMake") {
        Write-Host "Download from: https://cmake.org/download/"
        Start-Process "https://cmake.org/download/"
    }
}

# Check for Chromium/Chrome
Write-Host ""
Write-Host "Checking Chromium browser..."
$chromiumPaths = @(
    "C:\Program Files\Chromium\Application\chrome.exe",
    "C:\Program Files (x86)\Chromium\Application\chrome.exe",
    "C:\Program Files\Google\Chrome\Application\chrome.exe",
    "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
)

$chromiumFound = $false
foreach ($path in $chromiumPaths) {
    if (Test-Path $path) {
        Write-Host "✓ Found: $path" -ForegroundColor Green
        $chromiumFound = $true
        break
    }
}

if (-not $chromiumFound) {
    Write-Host "✗ Chromium/Chrome not found" -ForegroundColor Red
    if (Ask-Permission "Chromium") {
        Write-Host "Download from: https://chromium.woolyss.com/"
        Start-Process "https://chromium.woolyss.com/"
    }
}

Write-Host ""
Write-Host "========================================"
Write-Host "Installation Summary"
Write-Host "========================================"
Write-Host "Python: $(if($python){'✓'}else{'✗'})"
Write-Host "pip: $(if($pip){'✓'}else{'✗'})"
Write-Host "MSVC: $(if($vsPath){'✓'}else{'✗'})"
Write-Host "CMake: $(if($cmake){'✓'}else{'✗'})"
Write-Host "Chromium: $(if($chromiumFound){'✓'}else{'✗'})"
Write-Host "========================================"
Write-Host ""
Write-Host "To build the C++ browser engine:"
Write-Host "  cd impl_v1\phase49\native"
Write-Host "  cmake ."
Write-Host "  cmake --build . --config Release"
Write-Host ""
Write-Host "To run tests:"
Write-Host "  python -m pytest impl_v1\phase49\tests\ -v"
Write-Host ""
