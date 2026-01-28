#!/bin/bash
# Phase-49 Installer - Linux
# 
# This script installs dependencies for the Phase-49 browser engine.
# It ALWAYS asks for user permission before installing anything.

set -e

echo "========================================"
echo "Phase-49 Installer - Linux"
echo "========================================"
echo ""

# Detect distribution
if [ -f /etc/os-release ]; then
    . /etc/os-release
    DISTRO=$ID
    VERSION=$VERSION_ID
else
    DISTRO="unknown"
    VERSION="unknown"
fi

echo "Detected: $DISTRO $VERSION"
echo ""

# Function to ask user permission
ask_permission() {
    local component=$1
    echo ""
    read -p "Install $component? [y/N]: " response
    case "$response" in
        [yY][eE][sS]|[yY]) 
            return 0
            ;;
        *)
            echo "Skipping $component"
            return 1
            ;;
    esac
}

# Check for Python
echo "Checking Python..."
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version)
    echo "✓ Found: $PYTHON_VERSION"
else
    echo "✗ Python 3 not found"
    if ask_permission "Python 3"; then
        case $DISTRO in
            ubuntu|debian)
                sudo apt update && sudo apt install -y python3 python3-pip
                ;;
            fedora|rhel|centos)
                sudo dnf install -y python3 python3-pip
                ;;
            arch)
                sudo pacman -S python python-pip
                ;;
            *)
                echo "Unknown distro. Please install Python 3 manually."
                exit 1
                ;;
        esac
    fi
fi

# Check for pip
echo ""
echo "Checking pip..."
if command -v pip3 &> /dev/null; then
    echo "✓ Found pip3"
else
    echo "✗ pip3 not found"
    if ask_permission "pip3"; then
        python3 -m ensurepip --upgrade
    fi
fi

# Check for pytest
echo ""
echo "Checking pytest..."
if python3 -c "import pytest" 2>/dev/null; then
    echo "✓ Found pytest"
else
    echo "✗ pytest not found"
    if ask_permission "pytest"; then
        pip3 install pytest pytest-cov
    fi
fi

# Check for C++ compiler
echo ""
echo "Checking C++ compiler..."
if command -v g++ &> /dev/null; then
    GCC_VERSION=$(g++ --version | head -n1)
    echo "✓ Found: $GCC_VERSION"
else
    echo "✗ g++ not found"
    if ask_permission "g++ compiler"; then
        case $DISTRO in
            ubuntu|debian)
                sudo apt install -y build-essential
                ;;
            fedora|rhel|centos)
                sudo dnf groupinstall -y "Development Tools"
                ;;
            arch)
                sudo pacman -S base-devel
                ;;
        esac
    fi
fi

# Check for CMake
echo ""
echo "Checking CMake..."
if command -v cmake &> /dev/null; then
    CMAKE_VERSION=$(cmake --version | head -n1)
    echo "✓ Found: $CMAKE_VERSION"
else
    echo "✗ CMake not found"
    if ask_permission "CMake"; then
        case $DISTRO in
            ubuntu|debian)
                sudo apt install -y cmake
                ;;
            fedora|rhel|centos)
                sudo dnf install -y cmake
                ;;
            arch)
                sudo pacman -S cmake
                ;;
        esac
    fi
fi

# Check for Chromium
echo ""
echo "Checking Chromium browser..."
CHROMIUM_PATH=""
for path in /usr/bin/chromium /usr/bin/chromium-browser /snap/bin/chromium; do
    if [ -x "$path" ]; then
        CHROMIUM_PATH=$path
        break
    fi
done

if [ -n "$CHROMIUM_PATH" ]; then
    echo "✓ Found: $CHROMIUM_PATH"
else
    echo "✗ Chromium not found"
    if ask_permission "Chromium browser"; then
        case $DISTRO in
            ubuntu|debian)
                sudo apt install -y chromium-browser || sudo snap install chromium
                ;;
            fedora|rhel|centos)
                sudo dnf install -y chromium
                ;;
            arch)
                sudo pacman -S chromium
                ;;
        esac
    fi
fi

echo ""
echo "========================================"
echo "Installation Summary"
echo "========================================"
echo "Python: $(command -v python3 &> /dev/null && echo '✓' || echo '✗')"
echo "pip: $(command -v pip3 &> /dev/null && echo '✓' || echo '✗')"
echo "pytest: $(python3 -c 'import pytest' 2>/dev/null && echo '✓' || echo '✗')"
echo "g++: $(command -v g++ &> /dev/null && echo '✓' || echo '✗')"
echo "CMake: $(command -v cmake &> /dev/null && echo '✓' || echo '✗')"
echo "Chromium: $([[ -n \"$CHROMIUM_PATH\" ]] && echo '✓' || echo '✗')"
echo "========================================"
echo ""
echo "To build the C++ browser engine:"
echo "  cd impl_v1/phase49/native"
echo "  cmake ."
echo "  make"
echo ""
echo "To run tests:"
echo "  python -m pytest impl_v1/phase49/tests/ -v"
echo ""
