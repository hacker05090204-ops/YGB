# 🎯 YGB - Bug Research System

A comprehensive bug bounty research platform with AI-powered target discovery, execution governance, and voice controls.

---

## 🚀 Quick Start

### 1. Install Dependencies

```bash
# Backend (Python)
cd api
pip install -r requirements.txt

# Frontend (Node.js)
cd frontend
npm install
```

### 2. Start the System

**Terminal 1 - Backend API:**
```bash
cd api
python server.py
```
> API runs at: http://localhost:8000

**Terminal 2 - Frontend:**
```bash
cd frontend
npm run dev
```
> Frontend runs at: http://localhost:3000

### 3. Open in Browser

| Page | URL | Description |
|------|-----|-------------|
| **Control Dashboard** | http://localhost:3000/control | Main Phase-49 dashboard |
| **Runner** | http://localhost:3000/runner | Module execution |
| **Dashboard** | http://localhost:3000/dashboard | Analytics |

---

## 📁 Project Structure

```
YGB/
├── api/                    # Python backend
│   ├── server.py          # FastAPI server
│   └── requirements.txt   # Dependencies
│
├── frontend/              # Next.js frontend
│   ├── app/               # Pages
│   │   ├── control/       # ⭐ Main control dashboard
│   │   ├── dashboard/     # Analytics
│   │   └── runner/        # Module runner
│   │
│   └── components/        # UI components
│       ├── execution-state.tsx
│       ├── mode-selector.tsx
│       ├── approval-panel.tsx
│       ├── browser-assistant.tsx
│       ├── voice-controls.tsx
│       └── target-discovery-panel.tsx
│
├── python/                # Governance phases (01-19)
└── impl_v1/               # Implementation phases (20-49)
```

---

## 🎮 Features

### Control Dashboard (`/control`)

| Feature | Description |
|---------|-------------|
| 🎯 **Target Discovery** | Find public bug bounty programs |
| 🔄 **Mode Selector** | MOCK / READ_ONLY / AUTONOMOUS_FIND / REAL |
| ✅ **Approval Panel** | Approve / Reject / Stop execution |
| 📊 **Execution State** | 6-state machine visualization |
| 🤖 **Browser Assistant** | Method explanations & proposals |
| 🎤 **Voice Controls** | English & Hindi voice commands |

---

## 🔐 Safety

All actions are governed by Phase-49 security model:

> ⚠️ **Frontend has NO execution authority** - all actions route through backend

- ✅ Approval buttons send intent only
- ✅ Voice commands block forbidden patterns
- ✅ AUTONOMOUS_FIND mode capped at 12 hours
- ✅ REAL mode requires explicit human confirmation

---

## 🛠️ API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | System health check |
| `/api/dashboard/create` | POST | Initialize dashboard |
| `/api/execution/transition` | POST | State transitions |
| `/api/approval/decision` | POST | Submit approval |
| `/api/targets/discover` | POST | Find targets |
| `/api/voice/parse` | POST | Parse voice input |
| `/api/autonomy/session` | POST | Set operation mode |

---

## 📋 Requirements

- **Python** 3.10+
- **Node.js** 18+
- **npm** or **pnpm**

---

## 🆘 Troubleshooting

| Issue | Solution |
|-------|----------|
| API won't start | Run `pip install -r requirements.txt` in `/api` |
| Frontend errors | Run `npm install` in `/frontend` |
| Port 8000 in use | Kill the process or change port in `server.py` |
| Port 3000 in use | Kill the process or use `npm run dev -- -p 3001` |

---

<p align="center">
  <b>Built with ❤️ for security researchers</b>
</p>

