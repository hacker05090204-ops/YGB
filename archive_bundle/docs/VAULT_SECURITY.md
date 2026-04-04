# Vault Security — Backup & Recovery Guide

## Overview

YGB uses password-derived encryption for the vault, with separate JWT tokens for session management.

## Vault Password

The vault master key is derived from an admin password using **PBKDF2-HMAC-SHA256** (200,000 iterations).

**Backup**: Store the admin password in a secure password manager.

**If lost**:
- All encrypted vault data becomes inaccessible
- Re-encryption required with a new password
- Generate a new password and re-encrypt all secrets

## Salt File

**Location**: `secure_data/vault_salt.bin`

The salt is generated once per installation and used in key derivation. It must be preserved alongside encrypted data.

**Backup**: Include `vault_salt.bin` in encrypted backups of `secure_data/`.

**If lost**: Vault data cannot be decrypted even with the correct password.

## JWT Secret

**Environment variable**: `YGB_JWT_SECRET`

Used for signing short-lived authentication tokens. Auto-generated if not configured.

**If lost or regenerated**:
- All active sessions are invalidated
- Users must re-authenticate
- **No data corruption** — JWT is for auth only

**Generate new**:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

## Security Properties

| Component | Stored Where | If Lost |
|-----------|-------------|---------|
| Vault password | Admin's memory / password manager | Re-encrypt all data |
| Salt file | `secure_data/vault_salt.bin` | Cannot decrypt vault |
| JWT secret | `YGB_JWT_SECRET` env var | Sessions invalidated only |
| Derived key | Server memory only | Re-enter password |

## Frontend Security

- Frontend sends vault password over **HTTPS only**
- Backend derives the key server-side
- Derived key is **never** sent to frontend
- Key is held in memory only — cleared on server stop or explicit lock
