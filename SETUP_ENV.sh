#!/bin/bash
# YBG Environment Setup Script
# Run: source SETUP_ENV.sh

echo "Setting up YBG environment variables..."

# Generate secure secrets
export JWT_SECRET=$(python -c 'import secrets; print(secrets.token_urlsafe(32))')
export YGB_VIDEO_JWT_SECRET=$(python -c 'import secrets; print(secrets.token_urlsafe(32))')
export YGB_LEDGER_KEY=$(python -c 'import secrets; print(secrets.token_urlsafe(32))')

# Set operational mode
export YGB_USE_MOE="true"
export YGB_ENV="development"
export YGB_REQUIRE_ENCRYPTION="false"

echo "✅ Environment configured:"
echo "   JWT_SECRET: ${JWT_SECRET:0:16}... (${#JWT_SECRET} chars)"
echo "   YGB_VIDEO_JWT_SECRET: ${YGB_VIDEO_JWT_SECRET:0:16}... (${#YGB_VIDEO_JWT_SECRET} chars)"
echo "   YGB_LEDGER_KEY: ${YGB_LEDGER_KEY:0:16}... (${#YGB_LEDGER_KEY} chars)"
echo "   YGB_USE_MOE: $YGB_USE_MOE"
echo "   YGB_ENV: $YGB_ENV"
echo ""
echo "Run: python CHECK_SYSTEM.py to verify"
