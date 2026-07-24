import { useEffect, useState } from 'react';
import { api, BASE } from './api';
import SettingsPanel, { LlmConfig } from '../../../common/frontend/SettingsPanel';
import { useLlmConfig } from '../../../common/frontend/useLlmConfig';
import EmptyState from '../../../common/frontend/EmptyState';

const HREF_BASE = BASE || `${window.location.protocol}//${window.location.hostname}:8001`;

type Stage = 'idle' | 'analysis_complete' | 'complete';
type Tab = 'chat' | 'report' | 'checklist';
type LlmConfig = { openai_api_key: string; openai_base_url: string; openai_model: string; has_key: boolean; source: string };
type Finding = { id?: string; severity?: string; category?: string; text?: string; recommendation?: string };
type ChatMsg = { role: 'user' | 'assistant'; content: string };

export default function App() {
  const [sid, setSid] = useState('');
  const [stage, setStage] = useState<Stage>('idle');
  const [tab, setTab] = useState<Tab>('chat');
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState('Ready');
  const [showSettings, setShowSettings] = useState(false);
  const [llmCfg, setLlmCfg] = useState<LlmConfig>({ openai_api_key: '', openai_base_url: 'https://api.openai.com/v1', openai_model: 'gpt-4o', has_key: false, source: 'none' });

  // Sidebar state
  const [drawingFiles, setDrawingFiles] = useState<{ name: string; path: string }[]>([]);
  const [templateFile, setTemplateFile] = useState<{ name: string; path: string } | null>(null);

  // Analysis results
  const [extractedData, setExtractedData] = useState<any>(null);
  const [checkResults, setCheckResults] = useState<any>(null);
  const [reportHtml, setReportHtml] = useState('');
  const [checklistHtml, setChecklistHtml] = useState('');
  const [reportDocxPath, setReportDocxPath] = useState('');
  const [reportPdfPath, setReportPdfPath] = useState('');
  const [filledChecklistPath, setFilledChecklistPath] = useState('');
  const [reportChecklist, setReportChecklist] = useState<Finding[]>([]);

  // Chat state
  const [chatMessages, setChatMessages] = useState<ChatMsg[]>([]);
  const [chatInput, setChatInput] = useState('');

  useEffect(() => {
    api('/api/sessions', { method: 'POST' })
      .then(s => setSid(s.id))
      .catch(e => setMsg('Cannot reach backend — ' + e.message));
    api('/api/config').then(cfg => setLlmCfg(cfg)).catch(() => {});
  }, []);

  async function uploadDrawing(file: File) {
    if (!sid) return;
    const fd = new FormData();
    fd.append('file', file);
    setBusy(true); setMsg('Uploading drawing…');
    try {
      const r = await api(`/api/sessions/${sid}/upload/drawing`, { method: 'POST', body: fd });
      setDrawingFiles(prev => [...prev, { name: r.file, path: r.file_path }]);
      setMsg(`Drawing uploaded: ${r.file}`);
    } catch (e: any) { setMsg('Upload error: ' + e.message); }
    finally { setBusy(false); }
  }

  async function uploadTemplate(file: File) {
    if (!sid) return;
    const fd = new FormData();
    fd.append('file', file);
    setBusy(true); setMsg('Uploading template…');
    try {
      const r = await api(`/api/sessions/${sid}/upload/template`, { method: 'POST', body: fd });
      setTemplateFile({ name: r.file, path: r.template_path });
      setMsg(`Template uploaded: ${r.file}`);
    } catch (e: any) { setMsg('Upload error: ' + e.message); }
    finally { setBusy(false); }
  }

  async function runAnalysis() {
    if (!sid || drawingFiles.length === 0) return;
    setBusy(true); setMsg('Analyzing drawing… this may take a minute');
    try {
      const r = await api(`/api/sessions/${sid}/analyze`, {
        method: 'POST',
        body: JSON.stringify({ drawing_paths: drawingFiles.map(f => f.path), best_practices: '' })
      });
      setExtractedData(r.extracted_data);
      setCheckResults(r.check_results);
      setStage('analysis_complete');
      const fc = r.findings_count ?? 0;
      setMsg(`Analysis complete — ${fc} finding${fc !== 1 ? 's' : ''} identified. Click Generate Report to create the report.`);
      setChatMessages(prev => [...prev, {
        role: 'assistant',
        content: `Drawing analysis complete. ${fc} finding${fc !== 1 ? 's' : ''} identified.\nYou can ask questions about the drawing, or click Generate Report to create the full report and filled checklist.`
      }]);
      setTab('chat');
    } catch (e: any) { setMsg('Analysis error: ' + e.message); }
    finally { setBusy(false); }
  }

  async function runReport() {
    if (!sid) return;
    setBusy(true); setMsg('Generating report… this may take a minute');
    try {
      const r = await api(`/api/sessions/${sid}/report`, {
        method: 'POST',
        body: JSON.stringify({
          drawing_paths: drawingFiles.map(f => f.path),
          template_path: templateFile?.path ?? null,
          best_practices: ''
        })
      });
      setReportHtml(r.report_preview_html || '');
      setChecklistHtml(r.filled_checklist_preview_html || '');
      setReportDocxPath(r.report_docx_path || '');
      setReportPdfPath(r.report_pdf_path || '');
      setFilledChecklistPath(r.filled_checklist_path || '');
      setReportChecklist(r.report_checklist || []);
      setStage('complete');
      setMsg('Report and checklist generated successfully.');
      setTab('report');
    } catch (e: any) { setMsg('Report error: ' + e.message); }
    finally { setBusy(false); }
  }

  async function sendChat() {
    if (!chatInput.trim() || !sid) return;
    const text = chatInput.trim();
    setChatInput('');
    setChatMessages(prev => [...prev, { role: 'user', content: text }]);
    setBusy(true);
    try {
      const history = chatMessages.map(m => `${m.role}: ${m.content}`).join('\n');
      const r = await api(`/api/sessions/${sid}/chat`, {
        method: 'POST',
        body: JSON.stringify({ message: text, chat_history: history })
      });
      setChatMessages(prev => [...prev, { role: 'assistant', content: r.response }]);
    } catch (e: any) {
      setChatMessages(prev => [...prev, { role: 'assistant', content: 'Error: ' + e.message }]);
    }
    finally { setBusy(false); }
  }

  async function saveConfig(key: string, url: string, model: string) {
    setBusy(true); setMsg('Saving config…');
    try {
      const r = await api('/api/config', { method: 'PUT', body: JSON.stringify({ openai_api_key: key, openai_base_url: url, openai_model: model }) });
      setMsg(r.llm_mode === 'configured' ? 'LLM connected ✓' : r.llm_mode === 'unreachable' ? 'Warning: LLM unreachable — ' + r.llm_error : 'Config saved (demo mode)');
      api('/api/config').then(cfg => setLlmCfg(cfg)).catch(() => {});
      setShowSettings(false);
    } catch (e: any) { setMsg('Error: ' + (e.message || 'Unknown')); }
    finally { setBusy(false); }
  }

  return (
    <div className="app">
      <header>
        <div className="header-brand">
          <img src="/CapgeminiEngineering_Logo_2COL_RGB.svg" alt="Capgemini Engineering" className="brand-logo" />
          <b>Velocity AI</b>
          <span>Drawing Reviewer</span>
        </div>
        <div className="header-right">
          <span className={`llm-badge ${llmCfg.has_key ? 'llm-on' : 'llm-off'}`}>{llmCfg.has_key ? '● LLM' : '○ Demo'}</span>
          <button className="settings-btn" onClick={() => setShowSettings(v => !v)} title="LLM Settings">⚙</button>
          <div className="status">{busy ? '● ' : ''}{msg}</div>
        </div>
      </header>

      {showSettings && <SettingsPanel cfg={llmCfg} onSave={saveConfig} onClose={() => setShowSettings(false)} busy={busy} />}

      <main>
        <aside>
          <h2 style={{ marginBottom: 4 }}>Drawing Reviewer</h2>
          <p className="hint">Upload a PDF drawing, optionally an Excel checklist template, then analyze and generate the review report.</p>

          <hr className="divider" />

          <div className="step-label">Step 1 — Upload Drawing(s)</div>
          <label className="upload-btn">
            📄 Attach PDF Drawing
            <input type="file" accept=".pdf" onChange={e => e.target.files?.[0] && uploadDrawing(e.target.files[0])} disabled={busy} />
          </label>

          {drawingFiles.length > 0 && (
            <div className="attached-files">
              <h4>Attached Drawings</h4>
              {drawingFiles.map((f, i) => (
                <div className="file-item" key={i}>
                  <span className="fname">📄 {f.name}</span>
                  <button className="fremove" onClick={() => setDrawingFiles(prev => prev.filter((_, j) => j !== i))} title="Remove">✕</button>
                </div>
              ))}
            </div>
          )}

          <hr className="divider" />

          <div className="step-label">Step 2 — Upload Checklist Template (optional)</div>
          <label className="upload-btn">
            📊 Attach Excel Checklist
            <input type="file" accept=".xlsx,.xlsm" onChange={e => e.target.files?.[0] && uploadTemplate(e.target.files[0])} disabled={busy} />
          </label>
          {templateFile && (
            <div className="attached-files">
              <h4>Checklist Template</h4>
              <div className="file-item">
                <span className="fname">📊 {templateFile.name}</span>
                <button className="fremove" onClick={() => setTemplateFile(null)} title="Remove">✕</button>
              </div>
            </div>
          )}

          <hr className="divider" />

          <div className="step-label">Step 3 — Analyze</div>
          <button
            className="full-btn primary"
            disabled={!sid || drawingFiles.length === 0 || busy}
            onClick={runAnalysis}
          >
            🔍 Analyze Drawing
          </button>

          {stage === 'analysis_complete' && (
            <p className="hint" style={{ color: '#0070ad' }}>✓ Analysis ready — click Generate Report below.</p>
          )}

          <hr className="divider" />

          <div className="step-label">Step 4 — Generate Report</div>
          <button
            className="full-btn primary"
            disabled={!sid || drawingFiles.length === 0 || busy}
            onClick={runReport}
          >
            📋 Generate Report &amp; Checklist
          </button>

          {stage === 'complete' && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 6 }}>
              {reportDocxPath && (
                <a className="button full-btn" href={`${HREF_BASE}/api/download?path=${encodeURIComponent(reportDocxPath)}`} target="_blank" rel="noreferrer">⬇ Download Word Report</a>
              )}
              {reportPdfPath && (
                <a className="button full-btn" href={`${HREF_BASE}/api/download?path=${encodeURIComponent(reportPdfPath)}`} target="_blank" rel="noreferrer">⬇ Download PDF Report</a>
              )}
              {filledChecklistPath && (
                <a className="button full-btn" href={`${HREF_BASE}/api/download?path=${encodeURIComponent(filledChecklistPath)}`} target="_blank" rel="noreferrer">⬇ Download Filled Checklist</a>
              )}
            </div>
          )}
        </aside>

        <div className="workspace">
          <nav>
            {(['chat', 'report', 'checklist'] as Tab[]).map(t => (
              <button key={t} className={tab === t ? 'active' : ''} onClick={() => setTab(t)}>
                {t === 'chat' ? '💬 Chat' : t === 'report' ? '📄 Report' : '✅ Checklist'}
              </button>
            ))}
          </nav>

          {tab === 'chat' && (
            <ChatPanel
              messages={chatMessages}
              input={chatInput}
              onInputChange={setChatInput}
              onSend={sendChat}
              busy={busy}
              analysisReady={stage !== 'idle'}
            />
          )}

          {tab === 'report' && (
            <article>
              {reportHtml ? (
                <div className="report-preview" dangerouslySetInnerHTML={{ __html: reportHtml }} />
              ) : (
                <EmptyState
                  icon="📄"
                  title="No Report Yet"
                  description={stage === 'idle' ? 'Upload a drawing and click Analyze Drawing, then Generate Report.' : 'Analysis complete. Click Generate Report & Checklist to create the full report.'}
                />
              )}
            </article>
          )}

          {tab === 'checklist' && (
            <article>
              {checklistHtml ? (
                <div className="report-preview" dangerouslySetInnerHTML={{ __html: checklistHtml }} />
              ) : reportChecklist.length > 0 ? (
                <FindingsTable findings={reportChecklist} />
              ) : (
                <EmptyState
                  icon="✅"
                  title="No Checklist Yet"
                  description={stage === 'idle' ? 'Upload a drawing and run the full review to see the checklist.' : 'Click Generate Report & Checklist to produce the filled checklist.'}
                />
              )}
            </article>
          )}
        </div>
      </main>
    </div>
  );
}

// ── Chat Panel ─────────────────────────────────────────────────────────────

function ChatPanel({ messages, input, onInputChange, onSend, busy, analysisReady }: {
  messages: ChatMsg[];
  input: string;
  onInputChange: (v: string) => void;
  onSend: () => void;
  busy: boolean;
  analysisReady: boolean;
}) {
  return (
    <article style={{ display: 'flex', flexDirection: 'column', height: '100%', padding: '0' }}>
      <div style={{ flex: 1, overflowY: 'auto', padding: '20px', display: 'flex', flexDirection: 'column', gap: 12 }}>
        {messages.length === 0 && (
          <EmptyState
            icon="💬"
            title="Drawing Review Chat"
            description={analysisReady ? 'Analysis complete. Ask any question about the drawing.' : 'Upload a drawing PDF and click Analyze Drawing to get started. After analysis, ask questions here.'}
          />
        )}
        {messages.map((m, i) => (
          <div key={i} style={{
            alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start',
            maxWidth: '80%',
            background: m.role === 'user' ? '#0070ad' : 'white',
            color: m.role === 'user' ? 'white' : '#18212b',
            border: '1px solid var(--line)',
            borderRadius: m.role === 'user' ? '14px 14px 4px 14px' : '14px 14px 14px 4px',
            padding: '10px 14px',
            fontSize: 13,
            lineHeight: 1.5,
            whiteSpace: 'pre-wrap',
            boxShadow: '0 1px 4px rgba(0,0,0,.06)'
          }}>
            {m.content}
          </div>
        ))}
        {busy && (
          <div style={{ alignSelf: 'flex-start', color: '#60717e', fontSize: 13, padding: '10px 14px', background: 'white', border: '1px solid var(--line)', borderRadius: '14px 14px 14px 4px' }}>
            ⏳ Thinking…
          </div>
        )}
      </div>
      <div style={{ borderTop: '1px solid var(--line)', padding: '14px 20px', background: 'white', display: 'flex', gap: 10 }}>
        <textarea
          style={{ flex: 1, minHeight: 60, resize: 'none', borderRadius: 8, border: '1px solid var(--line)', padding: '10px 12px', fontSize: 13, fontFamily: 'inherit' }}
          placeholder={analysisReady ? 'Ask about the drawing…' : 'Analyze a drawing first, then ask questions here…'}
          value={input}
          onChange={e => onInputChange(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); onSend(); } }}
          disabled={busy}
        />
        <button className="primary" style={{ alignSelf: 'flex-end', padding: '10px 18px' }} onClick={onSend} disabled={busy || !input.trim()}>
          Send
        </button>
      </div>
    </article>
  );
}

// ── Findings Table ─────────────────────────────────────────────────────────

function FindingsTable({ findings }: { findings: Finding[] }) {
  if (!findings.length) return <EmptyState icon="✅" title="No Findings" description="No checklist findings were generated." />;
  return (
    <div>
      <h1>Checklist Findings</h1>
      <div className="tablewrap">
        <table className="checklist-table">
          <thead>
            <tr>
              <th>ID</th><th>Severity</th><th>Category</th><th>Finding</th><th>Recommendation</th>
            </tr>
          </thead>
          <tbody>
            {findings.map((f, i) => (
              <tr key={i}>
                <td>{f.id ?? `F${i + 1}`}</td>
                <td><SeverityBadge sev={f.severity ?? 'info'} /></td>
                <td>{f.category ?? '—'}</td>
                <td>{f.text ?? '—'}</td>
                <td>{f.recommendation ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function SeverityBadge({ sev }: { sev: string }) {
  const cls = { critical: 'badge-critical', error: 'badge-error', warning: 'badge-warning', info: 'badge-info' }[sev.toLowerCase()] ?? 'badge-info';
  return <span className={`badge ${cls}`}>{sev}</span>;
}

// ── Empty State ────────────────────────────────────────────────────────────

function EmptyState({ icon, title, description }: { icon: string; title: string; description: string }) {
  return (
    <div className="empty-state">
      <div className="icon">{icon}</div>
      <h2>{title}</h2>
      <p>{description}</p>
    </div>
  );
}

// ── Settings Panel ─────────────────────────────────────────────────────────

function SettingsPanel({ cfg, onSave, onClose, busy }: { cfg: LlmConfig; onSave: (k: string, u: string, m: string) => void; onClose: () => void; busy: boolean }) {
  const [key, setKey] = useState('');
  const [url, setUrl] = useState(cfg.openai_base_url);
  const [model, setModel] = useState(cfg.openai_model);
  const [show, setShow] = useState(false);
  return (
    <div className="settings-overlay" onClick={e => { if ((e.target as HTMLElement).classList.contains('settings-overlay')) onClose(); }}>
      <div className="settings-panel">
        <div className="settings-header"><h2>⚙ LLM Configuration</h2><button onClick={onClose}>✕</button></div>
        <p className="settings-status">Current source: <b>{cfg.source}</b> {cfg.has_key && <span className="llm-on">● Connected</span>}</p>
        <label>API Key
          <div className="key-row">
            <input type={show ? 'text' : 'password'} value={key} onChange={e => setKey(e.target.value)} placeholder={cfg.has_key ? 'Enter new key to replace current' : 'Paste your API key here…'} />
            <button type="button" onClick={() => setShow(v => !v)}>{show ? 'Hide' : 'Show'}</button>
          </div>
        </label>
        <label>Base URL<input type="text" value={url} onChange={e => setUrl(e.target.value)} placeholder="https://api.openai.com/v1" /></label>
        <label>Model<input type="text" value={model} onChange={e => setModel(e.target.value)} placeholder="gpt-4o" /></label>
        <div className="settings-footer">
          <button onClick={onClose}>Cancel</button>
          <button className="primary" disabled={busy || (!key.trim() && !cfg.has_key)} onClick={() => onSave(key || '__keep__', url, model)}>Save &amp; Test</button>
        </div>
        <p className="hint">Key is saved to the server's <code>.env</code> file and persists across restarts.</p>
      </div>
    </div>
  );
}