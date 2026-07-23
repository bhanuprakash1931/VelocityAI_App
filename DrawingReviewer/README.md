# Drawing Reviewer — Velocity AI

AI-assisted engineering drawing review application.

## Structure

```
DrawingReviewer/
  backend/
    app/
      __init__.py
      config.py      # Settings + runtime LLM config overrides
      models.py      # Pydantic schemas
      store.py       # JSON session persistence
      services.py    # Thin wrapper around VelocityAI_Platform workflow
      main.py        # FastAPI app (port 8001)
    requirements.txt
  frontend/
    src/
      App.tsx        # Main UI component
      api.ts         # Fetch wrapper
      styles.css     # App styles
      main.tsx       # React entry
    index.html
    package.json
    vite.config.ts   # Proxy /api -> localhost:8001
    tsconfig.json
```

## Quick Start

### Backend

```bash
# From VelocityAI_App root (uses shared venv)
.\venv\Scripts\activate
cd DrawingReviewer\backend

# Create .env with your API key
copy NUL .env
# Add: OPENAI_API_KEY=sk-...
# Add: OPENAI_BASE_URL=https://api.openai.com/v1
# Add: OPENAI_MODEL=gpt-4o

uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

### Frontend

```bash
cd DrawingReviewer\frontend
npm install
npm run dev
# Opens on http://localhost:5174
```

## Usage

1. **Upload PDF Drawing** — attach one or more engineering drawing PDFs
2. **Upload Excel Checklist** (optional) — attach a `.xlsx` checklist template to be filled
3. **Analyze Drawing** — runs vision extraction + best-practice check
4. **Chat** — ask questions about the drawing grounded in extracted data
5. **Generate Report & Checklist** — produces Word report, PDF report, and filled Excel checklist
6. **Download** artifacts using the sidebar buttons

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check + LLM status |
| GET/PUT | `/api/config` | LLM configuration |
| GET/POST | `/api/sessions` | List / create sessions |
| GET/DELETE | `/api/sessions/{sid}` | Get / delete session |
| POST | `/api/sessions/{sid}/upload/drawing` | Upload PDF drawing |
| POST | `/api/sessions/{sid}/upload/template` | Upload Excel template |
| POST | `/api/sessions/{sid}/analyze` | Run extraction + check |
| POST | `/api/sessions/{sid}/report` | Generate full report |
| POST | `/api/sessions/{sid}/chat` | Q&A grounded in analysis |
| GET | `/api/download?path=...` | Download generated artifact |

## Notes

- CORS is allowed for all origins (`allow_origins="*"`)
- The backend wraps `VelocityAI_Platform/apps/drawing_reviewer/` — ensure it is on `sys.path`
- Vision calls require a multimodal model (e.g. `gpt-4o`)
- Without an API key the workflow runs in fallback/demo mode
- Port 8001 is used to avoid conflict with RequirementsGenerator (8000) and RiskAssessor (8002)
