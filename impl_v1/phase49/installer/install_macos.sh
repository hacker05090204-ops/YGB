#!/bin/bash
# Phase-49 Installer - macOS
# 
# This script installs dependencies for the Phase-49 browser engine.
# It ALWAYS asks for user permission before installing anything.

set -e

echo "========================================"
echo "Phase-49 Installer - macOS"
echo "========================================"
echo ""

# Get macOS version
MACOS_VERSION=$(sw_vers -productVersion)
echo "Detected: macOS $MACOS_VERSION"
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

# Check for Homebrew
echo "Checking Homebrew..."
if command -v brew &> /dev/null; then
    BREW_VERSION=$(brew --version | head -n1)
    echo "✓ Found: $BREW_VERSION"
else
    echo "✗ Homebrew not found"
    if ask_permission "Homebrew (recommended package manager)"; then
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    fi
fi

# Check for Python
echo ""
echo "Checking Python..."
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version)
    echo "✓ Found: $PYTHON_VERSION"
else
    echo "✗ Python 3 not found"
    if ask_permission "Python 3"; then
        if command -v brew &> /dev/null; then
            brew install python3
        else
            echo "Please install Python from https://www.python.org/downloads/"
            open "https://www.python.org/downloads/"
        fi
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

# Check for Xcode Command Line Tools (includes clang++)
echo ""
echo "Checking C++ compiler (clang++)..."
if command -v clang++ &> /dev/null; then
    CLANG_VERSION=$(clang++ --version | head -n1)
    echo "✓ Found: $CLANG_VERSION"
else
    echo "✗ clang++ not found"
    if ask_permission "Xcode Command Line Tools"; then
        xcode-select --install
        echo "Please complete the installation in the popup window."
        read -p "Press Enter after installation completes..."
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
        if command -v brew &> /dev/null; then
            brew install cmake
        else
            echo "Please download CMake from https://cmake.org/download/"
            open "https://cmake.org/download/"
        fi
    fi
fi

# Check for Chromium
echo ""
echo "Checking Chromium browser..."
CHROMIUM_PATH=""
for path in "/Applications/Chromium.app" "/Applications/Google Chrome.app"; do
    if [ -d "$path" ]; then
        CHROMIUM_PATH=$path
        break
    fi
done

if [ -n "$CHROMIUM_PATH" ]; then
    echo "✓ Found: $CHROMIUM_PATH"
else
    echo "✗ Chromium not found"
    if ask_permission "Chromium browser"; then
        if command -v brew &> /dev/null; then
            brew install --cask chromium
        else
            echo "Please download Chromium from https://chromium.woolyss.com/"
            open "https://chromium.woolyss.com/"
        fi
    fi
fi

echo ""
echo "========================================"
echo "Installation Summary"
echo "========================================"
echo "Homebrew: $(command -v brew &> /dev/null && echo '✓' || echo '✗')"
echo "Python: $(command -v python3 &> /dev/null && echo '✓' || echo '✗')"
echo "pip: $(command -v pip3 &> /dev/null && echo '✓' || echo '✗')"
echo "pytest: $(python3 -c 'import pytest' 2>/dev/null && echo '✓' || echo '✗')"
echo "clang++: $(command -v clang++ &> /dev/null && echo '✓' || echo '✗')"
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
echo "  python3 -m pytest impl_v1/phase49/tests/ -v"
echo ""
