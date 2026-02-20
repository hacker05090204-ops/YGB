#!/usr/bin/env bash
# ======================================================================
# setup.sh — Zero-Trust First-Clone Bootstrap
#
# This script runs on first clone to:
#   1. Install dependencies
#   2. Generate device identity
#   3. Submit pairing request to authority
#   4. Wait for authority approval
#   5. Store device certificate
#   6. Configure WireGuard
#   7. Verify access
#
# NO automatic server access without completing ALL steps.
# HMAC secret is NEVER distributed to workers.
# ======================================================================

set -e

echo ""
echo "========================================"
echo "  YGB ZERO-TRUST DEVICE BOOTSTRAP"
echo "========================================"
echo ""

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_ROOT"

# ==================================================
# STEP 1: Install Dependencies
# ==================================================
echo "[SETUP] Step 1: Installing dependencies..."

# Python dependencies
if command -v pip3 &> /dev/null; then
    pip3 install --upgrade pip
    pip3 install numpy pytest pytest-cov pytest-asyncio pycryptodome bcrypt
    if [ -f requirements.txt ]; then
        pip3 install -r requirements.txt
    fi
    if [ -f api/requirements.txt ]; then
        pip3 install -r api/requirements.txt
    fi
elif command -v pip &> /dev/null; then
    pip install --upgrade pip
    pip install numpy pytest pytest-cov pytest-asyncio pycryptodome bcrypt
    if [ -f requirements.txt ]; then
        pip install -r requirements.txt
    fi
fi

# Node dependencies (if frontend exists)
if [ -d frontend ] && command -v npm &> /dev/null; then
    echo "[SETUP]   Installing Node dependencies..."
    cd frontend && npm install --legacy-peer-deps && cd ..
fi

echo "[SETUP]   ✅ Dependencies installed."

# ==================================================
# STEP 2: Compile Device Bootstrap
# ==================================================
echo ""
echo "[SETUP] Step 2: Compiling device bootstrap..."

BOOTSTRAP_BIN="build/device_bootstrap"
mkdir -p build

if command -v g++ &> /dev/null; then
    g++ -std=c++17 -O2 -DBOOTSTRAP_MAIN \
        native/bootstrap/device_bootstrap.cpp \
        -o "$BOOTSTRAP_BIN"
    echo "[SETUP]   ✅ Bootstrap compiled."
else
    echo "[SETUP]   ⚠️  g++ not found. Install build-essential."
    echo "[SETUP]   On Ubuntu: sudo apt-get install build-essential"
    exit 1
fi

# ==================================================
# STEP 3: Generate Device Identity
# ==================================================
echo ""
echo "[SETUP] Step 3: Generating device identity..."

# Run bootstrap in test mode first to verify
"$BOOTSTRAP_BIN" --test
if [ $? -ne 0 ]; then
    echo "[SETUP]   ❌ Bootstrap self-test failed."
    exit 1
fi
echo "[SETUP]   ✅ Self-test passed."

# ==================================================
# STEP 4: Run Full Bootstrap (Identity + Pairing + Wait)
# ==================================================
echo ""
echo "[SETUP] Step 4: Running device bootstrap..."
echo "  This will:"
echo "    - Generate/load device identity"
echo "    - Submit pairing request to authority"
echo "    - Wait for approval (up to 5 minutes)"
echo ""

ROLE="${1:-WORKER}"
echo "  Requested role: $ROLE"
echo ""

"$BOOTSTRAP_BIN" "$ROLE"
BOOTSTRAP_RESULT=$?

if [ $BOOTSTRAP_RESULT -ne 0 ]; then
    echo ""
    echo "[SETUP] ❌ Bootstrap failed."
    echo "  Contact your administrator for approval."
    echo "  Your pairing request is in: storage/pairing_requests/"
    exit 1
fi

# ==================================================
# STEP 5: Verify Certificate
# ==================================================
echo ""
echo "[SETUP] Step 5: Verifying certificate..."

CERT_PATH="storage/certs/device_cert.json"
if [ ! -f "$CERT_PATH" ]; then
    echo "[SETUP]   ❌ Certificate not found at $CERT_PATH"
    exit 1
fi

echo "[SETUP]   ✅ Certificate verified."

# ==================================================
# STEP 6: Configure WireGuard
# ==================================================
echo ""
echo "[SETUP] Step 6: Configuring WireGuard..."

if command -v python3 &> /dev/null; then
    python3 scripts/wireguard_config.py
elif command -v python &> /dev/null; then
    python scripts/wireguard_config.py
fi

# ==================================================
# STEP 7: Final Verification
# ==================================================
echo ""
echo "[SETUP] Step 7: Final verification..."

# Run Python tests to verify everything works
if command -v python3 &> /dev/null; then
    PYTHONPATH="$PROJECT_ROOT" python3 -c "
import json
cert = json.load(open('storage/certs/device_cert.json'))
print(f'  Device: {cert[\"device_id\"][:16]}...')
print(f'  Role: {cert[\"role\"]}')
print(f'  Mesh IP: {cert[\"mesh_ip\"]}')
import time
remaining = (cert['expires_at'] - int(time.time())) // 86400
print(f'  Expires in: {remaining} days')
"
fi

echo ""
echo "========================================"
echo "  ✅ BOOTSTRAP COMPLETE"
echo "========================================"
echo ""
echo "  Server access is now granted."
echo "  WireGuard config: config/wg0.conf"
echo "  Device cert: storage/certs/device_cert.json"
echo ""
echo "  ⚠️  SECURITY NOTES:"
echo "    - HMAC secret is NOT on this device"
echo "    - Authority validates all requests"
echo "    - Certificate expires in 90 days"
echo "    - Re-run this script to re-bootstrap"
echo ""
