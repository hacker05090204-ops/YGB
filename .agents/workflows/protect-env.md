---
description: Rule — never delete or blank secrets in .env
---

# .env Secret Protection Rule

## HARD CONSTRAINT — Non-negotiable

The following keys in `.env` are **owner-set production secrets** and must **NEVER** be deleted, blanked, or overwritten:

- `JWT_SECRET`
- `YGB_HMAC_SECRET`
- `YGB_VIDEO_JWT_SECRET`
- `GITHUB_CLIENT_ID`
- `GITHUB_CLIENT_SECRET`

## What is forbidden

1. Setting any of these to an empty string
2. Replacing their values with placeholders like `change-me` or `your-secret-here`
3. Overwriting `.env` with a template that blanks them
4. Running any "sanitize" or "clean" operation that clears them

## What is allowed

- Reading their values via `os.getenv()` or `dotenv`
- Adding **new** variables to `.env`
- Rotating a key **only if** the owner explicitly requests it and the new value is immediately set

## Why

These keys were generated with `secrets.token_hex(32)` (256-bit) and set by the project owner. Clearing them breaks JWT auth, HMAC telemetry verification, video streaming tokens, and GitHub OAuth. The server preflight check will refuse to start without them.
