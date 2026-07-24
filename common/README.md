# common/

Shared code used by all Velocity AI applications.

```
common/
├── backend/
│   ├── __init__.py           # Package marker
│   ├── config.py             # Settings factory + runtime override helpers
│   ├── llm_service.py        # LLM client: llm_json, llm_vision_json,
│   │                         #   llm_chat_completion, probe_llm
│   ├── store.py              # Generic JSON session store (SessionStore)
│   ├── models.py             # Shared Pydantic models: Column, LlmConfigRequest,
│   │                         #   ApiResult, BaseSession
│   ├── template_handler.py   # Excel header detection + file upload helper
│   ├── artifact_builder.py   # XLSX export, HTML table/findings preview builders
│   └── router.py             # FastAPI router factories: config, health, sessions,
│                             #   download routes
└── frontend/
    ├── api.ts                # Shared fetch wrapper (BASE + api())
    ├── SettingsPanel.tsx     # LLM config modal panel + LlmConfig type
    ├── useLlmConfig.ts       # React hook for LLM config state management
    ├── EmptyState.tsx        # Reusable empty-state placeholder component
    └── styles.css            # Base stylesheet (design tokens, layout, controls)
```

---

## Backend — how each app uses common/

### 1. `config.py`

Each app's `backend/app/config.py` becomes a thin wrapper:

```python
# RequirementsGenerator/backend/app/config.py
from pathlib import Path
from common.backend.config import make_runtime_helpers

_ENV = Path(__file__).resolve().parents[1] / ".env"

(
    settings,
    get_api_key, get_base_url, get_model,
    set_runtime, get_runtime_snapshot, persist_runtime_to_env,
) = make_runtime_helpers(env_file=_ENV, default_model="gpt-4.1-mini")
```

### 2. `store.py`

Each app's `backend/app/store.py` wraps the generic `SessionStore`:

```python
# RequirementsGenerator/backend/app/store.py
from common.backend.store import SessionStore
from .config import settings
from .models import Session

_store = SessionStore(
    sessions_dir=settings.data_dir / "sessions",
    model_class=Session,
    list_fields=["versions"],
)

def save(s): _store.save(s)
def load(sid): return _store.load(sid)
def delete(sid): _store.delete(sid)
def list_all(): return _store.list_all()
```

### 3. `llm_service.py`

In each app's `backend/app/services.py`:

```python
from common.backend.llm_service import llm_json, llm_chat_completion
from .config import get_api_key, get_base_url, get_model

result = await llm_json(
    system="...",
    user=json.dumps(payload),
    get_api_key=get_api_key,
    get_base_url=get_base_url,
    get_model=get_model,
)
```

### 4. `models.py`

Each app's `backend/app/models.py` imports shared base models:

```python
from common.backend.models import Column, LlmConfigRequest, ApiResult, BaseSession

class Session(BaseSession):
    stakeholder_needs: str = ""
    analysis: str = ""
    versions: list[Version] = Field(default_factory=list)
    active_version: int = -1
```

### 5. `template_handler.py`

```python
from common.backend.template_handler import save_upload, detect_template_columns

@app.post("/api/sessions/{sid}/upload")
async def upload(sid: str, file: UploadFile = File(...)):
    out, name = await save_upload(
        file=file, sid=sid,
        uploads_dir=settings.data_dir / "uploads",
        max_upload_mb=settings.max_upload_mb,
    )
    columns = detect_template_columns(out) if out.suffix.lower() in {".xlsx", ".xlsm"} else []
    return {"success": True, "file": name, "template_columns": columns}
```

### 6. `artifact_builder.py`

```python
from common.backend.artifact_builder import export_xlsx_response

@app.get("/api/sessions/{sid}/export.xlsx")
def export_xlsx(sid: str):
    t = get_table(sid)
    return export_xlsx_response(
        columns=[c.name for c in t.columns],
        rows=t.rows,
        sheet_title="Requirements",
        filename="requirements.xlsx",
    )
```

### 7. `router.py`

```python
from common.backend.router import config_router, health_router, sessions_router

app.include_router(config_router(
    get_api_key=get_api_key, get_base_url=get_base_url, get_model=get_model,
    set_runtime=set_runtime, settings=settings,
))
app.include_router(health_router(
    get_api_key=get_api_key, get_base_url=get_base_url, get_model=get_model,
    settings=settings,
))
app.include_router(sessions_router(
    store=store,
    session_factory=lambda: Session(title="New session"),
))
```

---

## Frontend — how each app uses common/

### `api.ts`

```typescript
// src/api.ts  (each app)
export { api, BASE } from '../../../common/frontend/api';
```

### `SettingsPanel.tsx`

```typescript
import SettingsPanel, { LlmConfig } from '../../../common/frontend/SettingsPanel';
```

### `useLlmConfig.ts`

```typescript
import { useLlmConfig } from '../../../common/frontend/useLlmConfig';

export default function App() {
  const { llmCfg, showSettings, setShowSettings, saveConfig, busy, msg, setMsg } = useLlmConfig();
  // ...
}
```

### `EmptyState.tsx`

```typescript
import EmptyState from '../../../common/frontend/EmptyState';

<EmptyState icon="📄" title="No Report Yet" description="Run analysis first." />
```

### `styles.css`

```css
/* src/styles.css  (each app) */
@import '../../../common/frontend/styles.css';

/* App-specific overrides below */
```

---

## Python path setup

To let Python find the `common` package, add the repo root to `sys.path`
in each app's `backend/app/__init__.py`:

```python
# RequirementsGenerator/backend/app/__init__.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
```

Or set `PYTHONPATH=<repo_root>` in the launch environment / Dockerfile.
