# Velocity AI — Platform

The platform landing page for all Velocity AI applications.

## What it does

- Shows all registered applications as cards with live health indicators
- Provides a single place to configure the shared LLM API key and push it to all app backends at once
- Each app card shows whether its backend is reachable and whether LLM is configured
- Clicking a card (or the Launch button) opens the app in a new tab

## Structure

```
platform/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── config.py      # Platform settings, runtime LLM config, .env persistence
│   │   ├── registry.py    # App registry — add new apps here
│   │   └── main.py        # FastAPI: health, app list, config push
│   ├── requirements.txt
│   └── Dockerfile
└── frontend/
    ├── src/
    │   ├── App.tsx        # Platform landing page UI
    │   ├── api.ts         # Fetch wrapper
    │   ├── styles.css
    │   ├── main.tsx
    │   └── vite-env.d.ts
    ├── index.html
    ├── package.json
    ├── tsconfig.json
    └── vite.config.ts
```

## Running the platform

### Backend

```powershell
cd platform/backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 7000
```

### Frontend

```powershell
cd platform/frontend
npm install
npm run dev
# Opens at http://localhost:5170
```

## API endpoints

| Method | Path                               | Description                      |
| ------ | ---------------------------------- | -------------------------------- |
| GET    | `/api/platform/health`           | Platform + LLM health check      |
| GET    | `/api/platform/apps`             | List all registered apps         |
| GET    | `/api/platform/apps/health`      | Health of all app backends       |
| GET    | `/api/platform/apps/{id}/health` | Health of one app backend        |
| GET    | `/api/platform/config`           | Current LLM config (key masked)  |
| PUT    | `/api/platform/config`           | Set LLM config + push to apps    |
| POST   | `/api/platform/config/push`      | Push existing config to all apps |

## Adding a new application

1. Create your app in its own directory (e.g. `MyApp/backend`, `MyApp/frontend`)
2. Open `platform/backend/app/registry.py` and add an entry to `APPS`:

```python
{
    "id": "my-app",
    "name": "My App",
    "tagline": "One-line description",
    "description": "Full description shown on the card.",
    "icon": "🔧",
    "color": "#6366f1",
    "frontend_url_key": "my_app_frontend_url",
    "backend_url_key": "my_app_backend_url",
    "tags": ["Tag1", "Tag2"],
    "status": "live",
},
```

3. Add the corresponding URL settings to `platform/backend/app/config.py`:

```python
my_app_backend_url: str = "http://localhost:8002"
my_app_frontend_url: str = "http://localhost:5175"
```

4. Restart the platform backend — no frontend changes needed.

## Environment / config

### Platform-level `.env` (`platform/backend/.env`)

```
OPENAI_API_KEY=sk-your-key
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4.1-mini
REQ_GEN_BACKEND_URL=http://localhost:8000
REQ_GEN_FRONTEND_URL=http://localhost:5173
RISK_ASSESSOR_BACKEND_URL=http://localhost:8001
RISK_ASSESSOR_FRONTEND_URL=http://localhost:5174
```

### App-level `.env` (e.g. `RequirementsGenerator/backend/.env`)

Each app has its own `.env` which is used when the app is run standalone.
When running under the platform, use **Push config to all apps** to sync the key.

## ENV resolution priority

```
Runtime override (PUT /api/platform/config)  ← highest priority
    ↓
platform/backend/.env
    ↓
Default values in config.py                 ← lowest priority
```

For individual apps:

```
Runtime override (PUT /api/config in the app)  ← highest
    ↓  or pushed via platform PUT /api/platform/config
app/backend/.env
    ↓
Default values                                 ← lowest
```
