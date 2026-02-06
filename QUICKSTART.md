# YGB Security Scanner - Quick Start

## Run the System

### Terminal 1: Start Backend
```powershell
cd C:\Users\jadav\OneDrive\Desktop\YGB\api
python server.py
```
Wait for: `✅ Server ready at http://localhost:8000`

### Terminal 2: Start Frontend
```powershell
cd C:\Users\jadav\OneDrive\Desktop\YGB\frontend
npm run dev
```
Wait for: `Ready in Xs`

### Open in Browser
Go to: **http://localhost:3000**

---

## Usage

1. Enter target URL (e.g., `https://example.com`)
2. Click **"Start Security Analysis"**
3. Watch 51 phases execute with real browser
4. View findings in real-time
5. Click **"Download Report"** when complete

---

## Reports

All reports saved to:
```
C:\Users\jadav\OneDrive\Desktop\YGB\report\
```

---

## Requirements

```powershell
pip install httpx fastapi uvicorn pydantic
```

---

## Features

- 51 Security Phases
- CVE Detection (Log4j, Heartbleed, etc.)
- SQL Injection Testing
- XSS, CSRF, IDOR Detection
- Common Path Discovery (/login, /admin, /api)
- HTTP-Only Analysis Mode (governance enforced)
- Auto TXT Reports
