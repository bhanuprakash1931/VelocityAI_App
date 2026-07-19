# Velocity AI Platform

A suite of AI-powered engineering tools built with React + FastAPI, accessible from a unified platform landing page or individually as standalone applications.

## Applications

| App                              | Description                                           | Frontend | Backend |
| -------------------------------- | ----------------------------------------------------- | -------- | ------- |
| **Platform**               | Landing page — launch apps, manage shared LLM config | :5170    | :7000   |
| **Requirements Generator** | AI requirements engineering, DFMEA, Excel templates   | :5173    | :8000   |
| **Risk Assessor**          | AI risk register, heatmap, FMEA, XLSX export          | :5174    | :8001   |

---

## Quick start — Full platform (all apps)

```powershell
# Windows PowerShell — starts all 6 processes in separate windows
.\start-all.ps1
```

Then open **http://localhost:5170** for the platform landing page.

---

## Quick start — Platform only

```powershell
.\start-platform.ps1
```

---

## Quick start — Individual apps (standalone)

### Requirements Generator

```powershell
# Backend
cd RequirementsGenerator/backend
venv\Scripts\activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Frontend (separate terminal)
cd RequirementsGenerator/frontend
npm run dev
# Opens at http://localhost:5173
```

### Risk Assessor

```powershell
# Backend
cd RiskAssessor/backend
venv\Scripts\activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Frontend (separate terminal)
cd RiskAssessor/frontend
npm run dev
# Opens at http://localhost:5173
```

> When running standalone, each app uses its own backend on port 8000. When running under the platform, the RiskAssessor backend moves to port 8001 to avoid conflict.

---

## Environment / configuration

### Option A — Platform-level shared config (recommended)

Create `platform/backend/.env`:

```
OPENAI_API_KEY=sk-your-key
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4.1-mini
```

Then use **Push config to all apps** in the platform settings panel (⚙) to sync the key to all running app backends in one click.

### Option B — Per-app config

Create `.env` in each app's backend directory:

```
# RequirementsGenerator/backend/.env
OPENAI_API_KEY=sk-your-key
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4.1-mini
```

```
# RiskAssessor/backend/.env
OPENAI_API_KEY=sk-your-key
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4.1-mini
```

### Priority (highest → lowest)

```
Runtime override via settings panel  ←  highest
    ↓
App/Platform backend .env file
    ↓
Code defaults (demo mode)            ←  lowest
```

Without any API key the apps run in **demo mode** — all outputs are deterministic fallbacks, no LLM calls are made.

---

## First-time setup

### Platform backend

```powershell
cd platform/backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### Platform frontend

```powershell
cd platform/frontend
npm install
```

### Requirements Generator backend

```powershell
cd RequirementsGenerator/backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### Requirements Generator frontend

```powershell
cd RequirementsGenerator/frontend
npm install
```

### Risk Assessor backend

```powershell
cd RiskAssessor/backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### Risk Assessor frontend

```powershell
cd RiskAssessor/frontend
npm install
```

---

## Adding a new application

1. Build your app in a new top-level directory (e.g. `MyApp/backend`, `MyApp/frontend`).
2. Add it to `platform/backend/app/registry.py` — see `platform/README.md` for instructions.
3. Add its URL settings to `platform/backend/app/config.py`.
4. Restart the platform backend. No frontend changes needed.

---

## Port reference

| Service                          | Port | URL                   |
| -------------------------------- | ---- | --------------------- |
| Platform backend                 | 7000 | http://localhost:7000 |
| Platform frontend                | 5170 | http://localhost:5170 |
| RequirementsGenerator backend    | 8000 | http://localhost:8000 |
| RequirementsGenerator frontend   | 5173 | http://localhost:5173 |
| RiskAssessor backend (platform)  | 8001 | http://localhost:8001 |
| RiskAssessor frontend (platform) | 5174 | http://localhost:5174 |
