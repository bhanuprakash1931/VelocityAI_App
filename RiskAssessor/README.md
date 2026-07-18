# Risk Assessor — Velocity AI

AI-powered risk assessment generation for projects, products, and systems.

## Features

- **Risk Analysis** — structured analysis from free-text stakeholder context
- **Risk Register Generation** — 12–20 rows covering Strategic, Operational, Financial, Compliance, Safety, Security, Technology, Supplier, Schedule, Quality, Environmental, and Reputational categories
- **DFMEA / FMEA Support** — detects DFMEA-style Excel templates and fills failure mode, severity, occurrence, detection, and RPN columns
- **Risk Heatmap** — likelihood × impact matrix with category breakdown and high/critical risk cards
- **Traceability Diagram** — Mermaid flowchart from context → analysis → register → categories
- **Filter & Search** — filter by category, overall rating, or free-text search in the table view
- **Actions** — query, review, update, and revise the register via the action panel
- **Export** — download the risk register as a formatted XLSX file
- **Excel Template Upload** — auto-detects column headers from uploaded risk templates
- **Demo Mode** — deterministic fallback when no LLM API key is configured
- **LLM Configuration** — set API key, base URL, and model via the settings panel (saved to `.env`)

## Project structure

```
RiskAssessor/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── config.py       # Settings, runtime overrides
│   │   ├── models.py       # Pydantic models
│   │   ├── store.py        # JSON session persistence
│   │   ├── services.py     # LLM calls, demo fallbacks, diagram data
│   │   └── main.py         # FastAPI routes
│   ├── requirements.txt
│   └── Dockerfile
└── frontend/
    ├── src/
    │   ├── App.tsx         # Main UI: analysis, table, heatmap, diagram, actions
    │   ├── api.ts          # Fetch wrapper
    │   ├── styles.css      # All styles
    │   ├── main.tsx
    │   └── vite-env.d.ts
    ├── index.html
    ├── package.json
    ├── tsconfig.json
    ├── vite.config.ts
    └── Dockerfile
```

## Quick start

### Backend

```bash
cd RiskAssessor/backend
python -m venv venv
# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt

# Optional: set your OpenAI key
echo OPENAI_API_KEY=sk-... > .env

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

API available at http://localhost:8000
Swagger UI at http://localhost:8000/docs

### Frontend

```bash
cd RiskAssessor/frontend
npm install
npm run dev -- --host 0.0.0.0 
```

UI available at http://localhost:5173

## API endpoints

| Method | Path                                     | Description                         |
| ------ | ---------------------------------------- | ----------------------------------- |
| GET    | `/api/health`                          | Health check + LLM status           |
| GET    | `/api/config`                          | Get current LLM config (key masked) |
| PUT    | `/api/config`                          | Set LLM API key, URL, model         |
| GET    | `/api/sessions`                        | List all sessions                   |
| POST   | `/api/sessions`                        | Create new session                  |
| GET    | `/api/sessions/{sid}`                  | Get session                         |
| DELETE | `/api/sessions/{sid}`                  | Delete session                      |
| POST   | `/api/sessions/{sid}/upload`           | Upload document / Excel template    |
| POST   | `/api/sessions/{sid}/analyze`          | Run risk analysis                   |
| POST   | `/api/sessions/{sid}/generate`         | Generate risk register              |
| PUT    | `/api/sessions/{sid}/table`            | Save edited table as new version    |
| POST   | `/api/sessions/{sid}/actions/{action}` | query / review / update / revise    |
| GET    | `/api/sessions/{sid}/diagram`          | Get heatmap + mermaid diagram data  |
| GET    | `/api/sessions/{sid}/export.xlsx`      | Export risk register as XLSX        |

## Configuration

Create `RiskAssessor/backend/.env`:

```
OPENAI_API_KEY=sk-your-key-here
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4.1-mini
CORS_ORIGINS=*
MAX_UPLOAD_MB=25
```

Without a key the app runs in **demo mode** — all responses are deterministic fallbacks and no LLM calls are made.

## CORS

The backend sets `allow_origins="*"` so any frontend origin can reach it during development. For production, set `CORS_ORIGINS` to your frontend domain.
