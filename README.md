# Velocity Requirements Generator Web

React + FastAPI conversion of the desktop Requirements Generator. It preserves the core web-appropriate workflows: requirements analysis, clarification, document/template upload, requirements generation, editable tables, versions, diagrams, query/review/update, session persistence, theme selection, metrics, and XLSX export.

## Quick start

### Backend
```bash
cd backend
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```
Open http://localhost:5173. API docs: http://localhost:8000/docs.

### Docker
```bash
docker compose up --build
```

## Configuration
Set `OPENAI_API_KEY`, `OPENAI_BASE_URL`, and `OPENAI_MODEL` in `backend/.env`. If no key is configured, the project runs in deterministic demo mode, so the full UI remains testable without external services.

## Notes on migration
- Qt signals/controllers are REST endpoints and React state/hooks.
- Qt output tabs are React tabs for analysis, table, diagram, and versions.
- Desktop attachment handling is multipart upload with server-side safe storage.
- In-memory desktop version state is persisted per session as JSON under `backend/data/sessions`.
- Mermaid is rendered in the browser.
- XLSX generation remains server-side using openpyxl.
- Credentials are environment variables only; no secrets are embedded.
