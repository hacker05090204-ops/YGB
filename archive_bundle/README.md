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

**One command (recommended, wired + fast defaults):**
```bash
powershell -ExecutionPolicy Bypass -File .\start_full_stack.ps1
```

**Private client mode (join the hosted Tailscale server and open it):**
```bash
powershell -ExecutionPolicy Bypass -File .\start_private_client.ps1
```

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
| `/api/g38/status` | GET | Training status |

---

## 📋 Requirements

- **Python** 3.10+
- **Node.js** 18+
- **npm** or **pnpm**

---

## 🖥️ Deploying YGB Backend on ygb-nas (Production)

The YGB backend runs on the **ygb-nas** machine and is accessed via Tailscale.

### 1. Clone & Configure

```bash
git clone https://github.com/hacker05090204-ops/YGB.git
cd YGB

# Copy the environment template (has all real keys pre-filled)
cp .env.example .env
```

### 2. Install & Start

```bash
pip install -r requirements.txt
cd frontend && npm install && cd ..
powershell -ExecutionPolicy Bypass -File .\start_full_stack.ps1
```

### 3. Access Points

| Service | URL |
|---------|-----|
| **Frontend** | `https://ygb-nas.tail7521c4.ts.net` |
| **Backend API** | `https://ygb-nas.tail7521c4.ts.net:8443` |
| **Local Frontend** | `http://localhost:3000` |
| **Local Backend** | `http://localhost:8000` |

---

## ⚙️ `.env` Configuration

Copy `.env.example` → `.env`. All keys are pre-filled with real values.

### OAuth (GitHub & Google)

```env
GITHUB_CLIENT_ID=Ov23liHtMNFZ096bZUE6
GITHUB_CLIENT_SECRET=<ask-owner-for-secret>
GITHUB_REDIRECT_URI=https://ygb-nas.tail7521c4.ts.net:8443/auth/github/callback

GOOGLE_CLIENT_ID=516476936580-41897h9ghok3c15e9h7svrgq3tblo9dl.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=<ask-owner-for-secret>
GOOGLE_REDIRECT_URI=https://ygb-nas.tail7521c4.ts.net:8443/auth/google/callback
```

### Sync Engine (Peer Mesh)

```env
YGB_DEVICE_ID=laptop_a
YGB_SYNC_ROOT=D:\
YGB_SYNC_INTERVAL_SEC=300
YGB_CHUNK_SIZE_MB=64

# Add peers by Tailscale IP
# YGB_PEER_NODES=laptop_b:100.64.0.2:8000,laptop_c:100.64.0.3:8000
```

**To add a new peer:**
1. Install Tailscale on the peer machine
2. Join the same Tailscale network
3. Add the peer's Tailscale IP to `YGB_PEER_NODES` on both machines
4. Set a unique `YGB_DEVICE_ID` on each peer

---

## 🧠 G38 Training (Mode A)

The system runs 24/7 GPU-accelerated training on the RTX 2050:

| Parameter | Value |
|-----------|-------|
| **Model** | BugClassifier (296K params) |
| **Architecture** | 256 → (512, 256, 128) → 2 |
| **Mode** | MODE-A: Representation Only |
| **Dataset** | 113K+ real samples from ingestion pipeline |
| **Checkpoints** | `D:\ygb_hdd\training\g38_model_checkpoint.safetensors` |

**Training Modes:**
- **MODE-A** (ACTIVE): Learns system structure — HTTP shapes, DOM patterns, API schemas. No bug labels.
- **MODE-B** (LOCKED): Proof-based learning. Unlocks only when G33/G36 produce verified bugs.

Check training status: `GET /api/g38/status`

---

## 🆘 Troubleshooting

| Issue | Solution |
|-------|----------|
| API won't start | Run `pip install -r requirements.txt` in `/api` |
| Frontend errors | Run `npm install` in `/frontend` |
| Port 8000 in use | Kill the process or change port in `server.py` |
| Port 3000 in use | Kill the process or use `npm run dev -- -p 3001` |
| OAuth callback fails | Ensure `GITHUB_REDIRECT_URI` matches your Tailscale hostname |
| Training not starting | Check `ENABLE_G38_AUTO_TRAINING=true` in `.env` |
| Sync not connecting | Verify `YGB_PEER_NODES` IPs and Tailscale connectivity |

---

<p align="center">
  <b>Built with ❤️ for security researchers</b>
</p>
