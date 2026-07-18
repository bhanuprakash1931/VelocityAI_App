import { useEffect, useRef, useState, useMemo } from 'react';
import { api, BASE } from './api';

const HREF_BASE = BASE || `${window.location.protocol}//${window.location.hostname}:8000`;

type Col = { name: string; data_type: string; editable: boolean };
type RiskTable = { title: string; columns: Col[]; rows: any[][] };
type Stage = 'idle' | 'analysis_complete' | 'clarification' | 'complete';
type LlmConfig = {
  openai_api_key: string;
  openai_base_url: string;
  openai_model: string;
  has_key: boolean;
  source: string;
};
type HeatmapCell = {
  likelihood_level: number;
  likelihood_label: string;
  impact_level: number;
  impact_label: string;
  risk_ids: string[];
  count: number;
};
type RiskRow = {
  id: string;
  category: string;
  statement: string;
  likelihood: string;
  impact: string;
  overall: string;
  overall_level: number;
  owner: string;
  status: string;
};
type DiagramData = {
  risks: RiskRow[];
  heatmap: HeatmapCell[];
  category_counts: Record<string, number>;
  mermaid: string;
  total: number;
  high_critical: number;
};

// ─── Rating colour helpers ──────────────────────────────────────────────────
function ratingColor(val: string): string {
  const v = val.toLowerCase();
  if (v.includes('critical')) return '#c00';
  if (v.includes('high')) return '#d97706';
  if (v.includes('medium') || v.includes('moderate')) return '#0070ad';
  if (v.includes('low')) return '#2e7d32';
  return '#60717e';
}
function ratingBg(val: string): string {
  const v = val.toLowerCase();
  if (v.includes('critical')) return '#fde8e8';
  if (v.includes('high')) return '#fff3cd';
  if (v.includes('medium') || v.includes('moderate')) return '#dff3fc';
  if (v.includes('low')) return '#e8f5e9';
  return '#f3f2f1';
}
function heatBg(l: number, i: number): string {
  const score = l * i;
  if (score >= 12) return '#fde8e8';
  if (score >= 6) return '#fff3cd';
  if (score >= 3) return '#dff3fc';
  return '#e8f5e9';
}

// ─── Main App ───────────────────────────────────────────────────────────────
export default function App() {
  const [sid, setSid] = useState('');
  const [needs, setNeeds] = useState('');
  const [analysis, setAnalysis] = useState('');
  const [qs, setQs] = useState<string[]>([]);
  const [answers, setAnswers] = useState('');
  const [table, setTable] = useState<RiskTable | null>(null);
  const [tab, setTab] = useState('analysis');
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState('Ready');
  const [cols, setCols] = useState<string[] | undefined>();
  const [stage, setStage] = useState<Stage>('idle');
  const [showSettings, setShowSettings] = useState(false);
  const [llmCfg, setLlmCfg] = useState<LlmConfig>({
    openai_api_key: '',
    openai_base_url: 'https://api.openai.com/v1',
    openai_model: 'gpt-4.1-mini',
    has_key: false,
    source: 'none',
  });
  const [filterCat, setFilterCat] = useState<string>('All');
  const [filterRating, setFilterRating] = useState<string>('All');
  const [searchText, setSearchText] = useState('');

  useEffect(() => {
    api('/api/sessions', { method: 'POST' })
      .then((s) => setSid(s.id))
      .catch((e) => setMsg('Cannot reach backend — ' + e.message));
    api('/api/config')
      .then((cfg) => setLlmCfg(cfg))
      .catch(() => {});
  }, []);

  async function run(path: string, body: any) {
    setBusy(true);
    setMsg('Working…');
    try {
      const r = await api(`/api/sessions/${sid}/${path}`, {
        method: 'POST',
        body: JSON.stringify(body),
      });
      const d = r.data || {};
      if (d.analysis) setAnalysis(d.analysis);
      if (d.clarification_questions?.length) {
        setQs(d.clarification_questions);
        setStage('clarification');
      } else if (r.stage === 'analysis_complete') {
        setStage('analysis_complete');
        setQs([]);
      }
      if (d.table) {
        setTable(d.table);
        setTab('table');
        setStage('complete');
      }
      setMsg(
        r.stage === 'clarification'
          ? 'Clarification needed'
          : r.stage === 'analysis_complete'
          ? 'Analysis complete — click Generate Risk Register'
          : 'Complete'
      );
    } catch (e: any) {
      setMsg('Error: ' + (e.message || 'Unknown error'));
    } finally {
      setBusy(false);
    }
  }

  async function upload(f: File) {
    const fd = new FormData();
    fd.append('file', f);
    setBusy(true);
    try {
      const r = await api(`/api/sessions/${sid}/upload`, {
        method: 'POST',
        body: fd,
      });
      if (r.template_columns?.length) setCols(r.template_columns);
      setMsg(`Uploaded ${r.file}${r.template_columns?.length ? ` — ${r.template_columns.length} template columns detected` : ''}`);
    } catch (e: any) {
      setMsg(e.message);
    } finally {
      setBusy(false);
    }
  }

  function edit(r: number, c: number, v: string) {
    if (!table) return;
    const rows = table.rows.map((x, i) =>
      i === r ? x.map((y, j) => (j === c ? v : y)) : x
    );
    setTable({ ...table, rows });
  }

  async function save() {
    if (!table) return;
    await api(`/api/sessions/${sid}/table`, {
      method: 'PUT',
      body: JSON.stringify({ columns: table.columns, rows: table.rows, source: 'user_edit' }),
    });
    setMsg('Saved as new version');
  }

  async function saveConfig(key: string, url: string, model: string) {
    setBusy(true);
    setMsg('Saving config…');
    try {
      const r = await api('/api/config', {
        method: 'PUT',
        body: JSON.stringify({ openai_api_key: key, openai_base_url: url, openai_model: model }),
      });
      setMsg(
        r.llm_mode === 'configured'
          ? 'LLM connected ✓'
          : r.llm_mode === 'unreachable'
          ? 'Warning: LLM unreachable — ' + r.llm_error
          : 'Config saved (demo mode)'
      );
      api('/api/config').then((cfg) => setLlmCfg(cfg)).catch(() => {});
      setShowSettings(false);
    } catch (e: any) {
      setMsg('Error: ' + (e.message || 'Unknown'));
    } finally {
      setBusy(false);
    }
  }

  // Filtered rows for table view
  const filteredRows = useMemo(() => {
    if (!table) return [];
    const cols = table.columns.map((c) => c.name.toLowerCase());
    const catIdx = cols.findIndex((c) => c.includes('category') || c.includes('type'));
    const ratingIdx = cols.findIndex(
      (c) => c.includes('overall') || c.includes('risk rating') || c.includes('score')
    );
    return table.rows.filter((row) => {
      const cat = catIdx >= 0 ? String(row[catIdx] ?? '') : '';
      const rating = ratingIdx >= 0 ? String(row[ratingIdx] ?? '') : '';
      const rowText = row.join(' ').toLowerCase();
      if (filterCat !== 'All' && !cat.toLowerCase().includes(filterCat.toLowerCase())) return false;
      if (filterRating !== 'All' && !rating.toLowerCase().includes(filterRating.toLowerCase())) return false;
      if (searchText && !rowText.includes(searchText.toLowerCase())) return false;
      return true;
    });
  }, [table, filterCat, filterRating, searchText]);

  const uniqueCategories = useMemo(() => {
    if (!table) return [];
    const catIdx = table.columns.findIndex(
      (c) => c.name.toLowerCase().includes('category') || c.name.toLowerCase().includes('type')
    );
    if (catIdx < 0) return [];
    return ['All', ...Array.from(new Set(table.rows.map((r) => String(r[catIdx] ?? '')).filter(Boolean)))];
  }, [table]);

  const ratingLevels = ['All', 'Critical', 'High', 'Medium', 'Low'];

  return (
    <div className="app">
      <header>
        <div className="header-brand">
          <img
            src="/CapgeminiEngineering_Logo_2COL_RGB.svg"
            alt="Capgemini Engineering"
            className="brand-logo"
            onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
          />
          <b>Velocity AI</b>
          <span>Risk Assessor</span>
        </div>
        <div className="header-right">
          <span className={`llm-badge ${llmCfg.has_key ? 'llm-on' : 'llm-off'}`}>
            {llmCfg.has_key ? '● LLM' : '○ Demo'}
          </span>
          <button className="settings-btn" onClick={() => setShowSettings((v) => !v)} title="LLM Settings">⚙</button>
          <div className="status">{busy ? '● ' : ''}{msg}</div>
        </div>
      </header>

      {showSettings && (
        <SettingsPanel
          cfg={llmCfg}
          onSave={saveConfig}
          onClose={() => setShowSettings(false)}
          busy={busy}
        />
      )}

      <main>
        <aside>
          <h2>Risk Context</h2>
          <textarea
            value={needs}
            onChange={(e) => setNeeds(e.target.value)}
            placeholder="Describe the project, system, product, assets, stakeholders, constraints, environment, and known concerns. The more context you provide, the more accurate the risk register will be."
          />

          <label className="upload">
            Attach documents / Excel risk template
            <input type="file" onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
          </label>
          {cols && <small>✓ {cols.length} template columns detected</small>}

          <button
            disabled={!sid || !needs.trim() || busy}
            onClick={() =>
              run('analyze', {
                stakeholder_needs: needs,
                clarification_answers: answers,
                template_columns: cols,
                direct_generation: false,
              })
            }
          >
            Analyze
          </button>

          <button
            className="primary"
            disabled={!analysis || busy}
            onClick={() => run('generate', { template_columns: cols })}
          >
            Generate Risk Register
          </button>

          {stage === 'analysis_complete' && !table && (
            <p className="hint" style={{ color: 'var(--accent)' }}>
              ✓ Analysis ready — click Generate Risk Register.
            </p>
          )}

          {qs.length > 0 && (
            <section className="clarify">
              <h3>Clarification needed</h3>
              {qs.map((q) => (
                <p key={q}>• {q}</p>
              ))}
              <textarea
                value={answers}
                onChange={(e) => setAnswers(e.target.value)}
                placeholder="Provide your answers here…"
              />
              <button
                className="primary"
                disabled={!answers.trim() || busy}
                onClick={() =>
                  run('analyze', {
                    stakeholder_needs: needs,
                    clarification_answers: answers,
                    template_columns: cols,
                    direct_generation: false,
                  })
                }
              >
                Submit answers
              </button>
            </section>
          )}

          {table && (
            <section className="actions-panel">
              <h3>Actions</h3>
              <ActionPanel sid={sid} table={table} analysis={analysis} />
            </section>
          )}

          <p className="hint">
            Without an API key, deterministic demo mode is used.
          </p>
        </aside>

        <section className="workspace">
          <nav>
            {['analysis', 'table', 'heatmap', 'diagram'].map((x) => (
              <button
                key={x}
                className={tab === x ? 'active' : ''}
                onClick={() => setTab(x)}
              >
                {x === 'heatmap' ? 'Risk Heatmap' : x.charAt(0).toUpperCase() + x.slice(1)}
              </button>
            ))}
          </nav>

          {tab === 'analysis' && (
            <article>
              <h1>Risk Analysis</h1>
              <div className="prose">
                {analysis
                  ? analysis.split('\n').map((line, i) => (
                      <span key={i}>
                        {line}
                        <br />
                      </span>
                    ))
                  : 'Run analysis to see the risk assessment and clarification questions.'}
              </div>
            </article>
          )}

          {tab === 'table' && (
            <article>
              <div className="toolbar">
                <h1>{table?.title || 'Risk Register'}</h1>
                <button onClick={save} disabled={!table}>Save version</button>
                <a className="button" href={`${HREF_BASE}/api/sessions/${sid}/export.xlsx`}>
                  Export XLSX
                </a>
              </div>

              {table && (
                <div className="filter-bar">
                  <input
                    placeholder="Search…"
                    value={searchText}
                    onChange={(e) => setSearchText(e.target.value)}
                    className="filter-input"
                  />
                  {uniqueCategories.length > 1 && (
                    <select
                      value={filterCat}
                      onChange={(e) => setFilterCat(e.target.value)}
                      className="filter-select"
                    >
                      {uniqueCategories.map((c) => (
                        <option key={c}>{c}</option>
                      ))}
                    </select>
                  )}
                  <select
                    value={filterRating}
                    onChange={(e) => setFilterRating(e.target.value)}
                    className="filter-select"
                  >
                    {ratingLevels.map((r) => (
                      <option key={r}>{r}</option>
                    ))}
                  </select>
                  <span className="filter-count">
                    {filteredRows.length} / {table.rows.length} risks
                  </span>
                </div>
              )}

              {table ? (
                <div className="tablewrap">
                  <table>
                    <thead>
                      <tr>
                        {table.columns.map((c) => (
                          <th key={c.name}>{c.name}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {filteredRows.map((r, i) => {
                        const ratingIdx = table.columns.findIndex(
                          (c) =>
                            c.name.toLowerCase().includes('overall') ||
                            c.name.toLowerCase().includes('risk rating')
                        );
                        const ratingVal = ratingIdx >= 0 ? String(r[ratingIdx] ?? '') : '';
                        return (
                          <tr
                            key={i}
                            style={{
                              background: ratingVal ? ratingBg(ratingVal) : undefined,
                            }}
                          >
                            {r.map((v, j) => {
                              const isRating =
                                j === ratingIdx ||
                                table.columns[j]?.name.toLowerCase().includes('likelihood') ||
                                table.columns[j]?.name.toLowerCase().includes('impact rating') ||
                                table.columns[j]?.name.toLowerCase().includes('residual');
                              return (
                                <td key={j}>
                                  {isRating && v ? (
                                    <span
                                      className="rating-chip"
                                      style={{
                                        color: ratingColor(String(v)),
                                        background: ratingBg(String(v)),
                                      }}
                                    >
                                      {v}
                                    </span>
                                  ) : (
                                    <input
                                      value={v ?? ''}
                                      onChange={(e) => edit(table.rows.indexOf(r), j, e.target.value)}
                                    />
                                  )}
                                </td>
                              );
                            })}
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p>No risk register generated yet.</p>
              )}
            </article>
          )}

          {tab === 'heatmap' && (
            <HeatmapTab sid={sid} hasTable={!!table} />
          )}

          {tab === 'diagram' && (
            <DiagramTab sid={sid} hasTable={!!table} />
          )}
        </section>
      </main>
    </div>
  );
}

// ─── Action Panel ────────────────────────────────────────────────────────────
function ActionPanel({
  sid,
  analysis: _analysis,
}: {
  sid: string;
  table: RiskTable;
  analysis: string;
}) {
  const [action, setAction] = useState<'query' | 'review' | 'update' | 'revise'>('query');
  const [text, setText] = useState('');
  const [response, setResponse] = useState('');
  const [busy, setBusy] = useState(false);

  async function submit() {
    if (!text.trim()) return;
    setBusy(true);
    setResponse('');
    try {
      const r = await api(`/api/sessions/${sid}/actions/${action}`, {
        method: 'POST',
        body: JSON.stringify({ text }),
      });
      setResponse(r.data?.response || JSON.stringify(r.data, null, 2));
    } catch (e: any) {
      setResponse('Error: ' + e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <div className="action-tabs">
        {(['query', 'review', 'update', 'revise'] as const).map((a) => (
          <button
            key={a}
            className={action === a ? 'action-tab active' : 'action-tab'}
            onClick={() => setAction(a)}
          >
            {a.charAt(0).toUpperCase() + a.slice(1)}
          </button>
        ))}
      </div>
      <p className="hint">
        {action === 'query' && 'Ask a question about the risk register or analysis.'}
        {action === 'review' && 'Paste a risk statement to review its quality.'}
        {action === 'update' && 'Describe a change to apply to the risk register.'}
        {action === 'revise' && 'Add a revision note to all risks in the register.'}
      </p>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={`Enter ${action} text…`}
        style={{ minHeight: 70 }}
      />
      <button className="primary" disabled={!text.trim() || busy} onClick={submit}>
        {busy ? 'Working…' : action.charAt(0).toUpperCase() + action.slice(1)}
      </button>
      {response && (
        <div className="action-response">
          <strong>Response:</strong>
          <div className="prose" style={{ marginTop: 8, fontSize: 13 }}>
            {response.split('\n').map((line, i) => (
              <span key={i}>{line}<br /></span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Heatmap Tab ─────────────────────────────────────────────────────────────
function HeatmapTab({ sid, hasTable }: { sid: string; hasTable: boolean }) {
  const [data, setData] = useState<DiagramData | null>(null);
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);

  async function load() {
    if (!sid || !hasTable) return;
    setBusy(true);
    setErr('');
    try {
      const r = await api(`/api/sessions/${sid}/diagram`);
      setData(r.data);
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    if (hasTable) load();
  }, [sid, hasTable]);

  if (!hasTable)
    return (
      <article>
        <h1>Risk Heatmap</h1>
        <p>Generate a risk register first, then view the heatmap here.</p>
      </article>
    );

  return (
    <article>
      <div className="toolbar">
        <h1>Risk Heatmap</h1>
        <button onClick={load} disabled={busy}>
          {busy ? 'Loading…' : 'Refresh'}
        </button>
      </div>
      {err && <p style={{ color: 'var(--error, #c00)' }}>Error: {err}</p>}

      {data && (
        <>
          <div className="heatmap-stats">
            <div className="stat-card">
              <div className="stat-num">{data.total}</div>
              <div className="stat-label">Total Risks</div>
            </div>
            <div className="stat-card stat-warn">
              <div className="stat-num">{data.high_critical}</div>
              <div className="stat-label">High / Critical</div>
            </div>
            <div className="stat-card">
              <div className="stat-num">{Object.keys(data.category_counts).length}</div>
              <div className="stat-label">Categories</div>
            </div>
          </div>

          <h3>Risk Likelihood × Impact Matrix</h3>
          <div className="heatmap-grid">
            <div className="heatmap-corner" />
            {[1, 2, 3, 4].map((l) => (
              <div key={l} className="heatmap-col-label">
                {['', 'Low', 'Medium', 'High', 'Critical'][l]}
              </div>
            ))}
            <div className="heatmap-row-header">Impact →</div>
            {[4, 3, 2, 1].map((likelihood) => (
              <>
                <div key={`lbl-${likelihood}`} className="heatmap-row-label">
                  {['', 'Low', 'Medium', 'High', 'Critical'][likelihood]}
                </div>
                {[1, 2, 3, 4].map((impact) => {
                  const cell = data.heatmap.find(
                    (h) => h.likelihood_level === likelihood && h.impact_level === impact
                  );
                  return (
                    <div
                      key={`${likelihood}-${impact}`}
                      className="heatmap-cell"
                      style={{ background: heatBg(likelihood, impact) }}
                      title={cell?.risk_ids.join(', ') || 'No risks'}
                    >
                      {cell && cell.count > 0 ? (
                        <span className="heatmap-count">{cell.count}</span>
                      ) : null}
                      {cell?.risk_ids.slice(0, 3).map((id) => (
                        <div key={id} className="heatmap-risk-id">{id}</div>
                      ))}
                    </div>
                  );
                })}
              </>
            ))}
          </div>
          <p className="hint" style={{ marginTop: 8 }}>Likelihood (rows) × Impact (columns). Darker = higher exposure.</p>

          <h3>Risks by Category</h3>
          <div className="category-bars">
            {Object.entries(data.category_counts)
              .sort((a, b) => b[1] - a[1])
              .map(([cat, count]) => (
                <div key={cat} className="category-bar-row">
                  <span className="cat-label">{cat}</span>
                  <div className="bar-track">
                    <div
                      className="bar-fill"
                      style={{ width: `${(count / data.total) * 100}%` }}
                    />
                  </div>
                  <span className="cat-count">{count}</span>
                </div>
              ))}
          </div>

          <h3 style={{ marginTop: 24 }}>High / Critical Risks</h3>
          <div className="risk-cards">
            {data.risks
              .filter((r) => r.overall_level >= 3)
              .map((r) => (
                <div key={r.id} className="risk-card">
                  <div className="risk-card-header">
                    <span className="risk-id">{r.id}</span>
                    <span
                      className="rating-chip"
                      style={{ color: ratingColor(r.overall), background: ratingBg(r.overall) }}
                    >
                      {r.overall}
                    </span>
                    <span className="risk-category">{r.category}</span>
                  </div>
                  <p className="risk-statement">{r.statement}</p>
                  <div className="risk-meta">
                    <span>L: {r.likelihood}</span>
                    <span>I: {r.impact}</span>
                    <span>Owner: {r.owner}</span>
                    <span>Status: {r.status}</span>
                  </div>
                </div>
              ))}
          </div>
        </>
      )}
    </article>
  );
}

// ─── Diagram Tab ─────────────────────────────────────────────────────────────
function DiagramTab({ sid, hasTable }: { sid: string; hasTable: boolean }) {
  const [code, setCode] = useState('');
  const [err, setErr] = useState('');
  const fetched = useRef(false);

  function load() {
    if (!sid || !hasTable) return;
    fetched.current = true;
    setErr('');
    api(`/api/sessions/${sid}/diagram`)
      .then((r) => setCode(r.data?.mermaid || ''))
      .catch((e) => {
        setErr(e.message);
        fetched.current = false;
      });
  }

  useEffect(() => {
    if (hasTable && !fetched.current) load();
  }, [sid, hasTable]);

  return (
    <article>
      <h1>Traceability Diagram</h1>
      {!hasTable ? (
        <p>Generate a risk register first, then view the traceability diagram here.</p>
      ) : (
        <>
          <p>
            Mermaid flowchart source — paste into{' '}
            <a href="https://mermaid.live" target="_blank" rel="noreferrer">
              mermaid.live
            </a>{' '}
            to render.
          </p>
          {err && <p style={{ color: 'var(--error, #c00)' }}>Error: {err}</p>}
          <pre>{code || 'Loading…'}</pre>
          <button onClick={load}>Refresh</button>
        </>
      )}
    </article>
  );
}

// ─── Settings Panel ───────────────────────────────────────────────────────────
function SettingsPanel({
  cfg,
  onSave,
  onClose,
  busy,
}: {
  cfg: LlmConfig;
  onSave: (k: string, u: string, m: string) => void;
  onClose: () => void;
  busy: boolean;
}) {
  const [key, setKey] = useState('');
  const [url, setUrl] = useState(cfg.openai_base_url);
  const [model, setModel] = useState(cfg.openai_model);
  const [show, setShow] = useState(false);

  return (
    <div
      className="settings-overlay"
      onClick={(e) => {
        if ((e.target as HTMLElement).classList.contains('settings-overlay')) onClose();
      }}
    >
      <div className="settings-panel">
        <div className="settings-header">
          <h2>⚙ LLM Configuration</h2>
          <button onClick={onClose}>✕</button>
        </div>
        <p className="settings-status">
          Current source: <b>{cfg.source}</b>{' '}
          {cfg.has_key && <span className="llm-on">● Connected</span>}
        </p>
        <label>
          API Key
          <div className="key-row">
            <input
              type={show ? 'text' : 'password'}
              value={key}
              onChange={(e) => setKey(e.target.value)}
              placeholder={cfg.has_key ? 'Enter new key to replace current' : 'Paste your API key here…'}
            />
            <button type="button" onClick={() => setShow((v) => !v)}>
              {show ? 'Hide' : 'Show'}
            </button>
          </div>
        </label>
        <label>
          Base URL
          <input
            type="text"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://api.openai.com/v1"
          />
        </label>
        <label>
          Model
          <input
            type="text"
            value={model}
            onChange={(e) => setModel(e.target.value)}
            placeholder="gpt-4.1-mini"
          />
        </label>
        <div className="settings-footer">
          <button onClick={onClose}>Cancel</button>
          <button
            className="primary"
            disabled={busy || (!key.trim() && !cfg.has_key)}
            onClick={() => onSave(key || '__keep__', url, model)}
          >
            Save &amp; Test
          </button>
        </div>
        <p className="hint">
          Key is saved to the server's <code>.env</code> file and persists across restarts.
        </p>
      </div>
    </div>
  );
}