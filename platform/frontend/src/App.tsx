import { useEffect, useRef, useState, useCallback } from 'react';
import { api } from './api';

// ─── Types ───────────────────────────────────────────────────────────────────
type AppEntry = {
  id: string;
  name: string;
  tagline: string;
  description: string;
  icon: string;
  color: string;
  tags: string[];
  status: string;
  frontend_url: string;
  backend_url: string;
};

type AppHealth = {
  id: string;
  reachable: boolean;
  llm_mode?: string;
  status?: string;
  error?: string;
};

type PlatformHealth = {
  status: string;
  llm_mode: string;
  llm_url: string;
  llm_model: string;
  llm_error: string | null;
};

type LlmConfig = {
  openai_api_key: string;
  openai_base_url: string;
  openai_model: string;
  has_key: boolean;
  source: string;
};

type PushResult = {
  id: string;
  pushed: boolean;
  llm_mode?: string;
  error?: string;
};

type ProcessInfo = {
  id: string;
  port: number;
  status: string;
  pid: number | null;
  restarts: number;
  uptime_s: number | null;
  frontend_status?: string;
  frontend_port?: number;
};

// ─── Main App ─────────────────────────────────────────────────────────────────
export default function App() {
  const [apps, setApps] = useState<AppEntry[]>([]);
  const [health, setHealth] = useState<Record<string, AppHealth>>({});
  const [processes, setProcesses] = useState<Record<string, ProcessInfo>>({});
  const [platformHealth, setPlatformHealth] = useState<PlatformHealth | null>(null);
  const [llmCfg, setLlmCfg] = useState<LlmConfig>({
    openai_api_key: '',
    openai_base_url: 'https://api.openai.com/v1',
    openai_model: 'gpt-4.1-mini',
    has_key: false,
    source: 'none',
  });
  const [showSettings, setShowSettings] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState('');
  const [healthLoading, setHealthLoading] = useState(false);

  // Auto-retry health polling: keeps retrying every POLL_INTERVAL ms
  // until all registered apps are reachable, then switches to a slower
  // keep-alive interval. This ensures apps that are still booting up
  // will appear Online as soon as their backend becomes responsive.
  const POLL_FAST = 3000;   // 3 s while any app is still offline
  const POLL_SLOW = 30000;  // 30 s once everything is up
  const pollTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const appsRef = useRef<AppEntry[]>([]);
  const healthRef = useRef<Record<string, AppHealth>>({});

  // Keep refs in sync so the polling closure always sees fresh values
  useEffect(() => { appsRef.current = apps; }, [apps]);
  useEffect(() => { healthRef.current = health; }, [health]);

  // Load apps + config on mount, then start polling
  useEffect(() => {
    api('/api/platform/apps')
      .then((r) => setApps(r.apps ?? []))
      .catch((e) => setMsg('Cannot reach platform backend — ' + e.message));
    api('/api/platform/config')
      .then((cfg) => setLlmCfg(cfg))
      .catch(() => {});
    loadHealth();
    return () => { if (pollTimer.current) clearTimeout(pollTimer.current); };
  }, []);

  const scheduleNextPoll = useCallback((currentHealth: Record<string, AppHealth>, totalApps: number) => {
    if (pollTimer.current) clearTimeout(pollTimer.current);
    const allUp = totalApps > 0 && Object.values(currentHealth).filter(h => h.reachable).length === totalApps;
    const delay = allUp ? POLL_SLOW : POLL_FAST;
    pollTimer.current = setTimeout(() => loadHealth(), delay);
  }, []);

  const loadHealth = useCallback(async () => {
    setHealthLoading(true);
    try {
      const [ph, ah, pr] = await Promise.all([
        api('/api/platform/health'),
        api('/api/platform/apps/health'),
        api('/api/platform/processes'),
      ]);
      setPlatformHealth(ph);
      const map: Record<string, AppHealth> = {};
      for (const h of ah.apps ?? []) map[h.id] = h;
      setHealth(map);
      const pmap: Record<string, ProcessInfo> = {};
      for (const p of pr.processes ?? []) pmap[p.id] = p;
      setProcesses(pmap);
      scheduleNextPoll(map, ah.apps?.length ?? 0);
    } catch (_) {
      // Platform backend not yet ready — retry fast
      pollTimer.current = setTimeout(() => loadHealth(), POLL_FAST);
    }
    setHealthLoading(false);
  }, [scheduleNextPoll]);

  async function saveConfig(
    key: string,
    url: string,
    model: string,
    pushToApps: boolean
  ) {
    setBusy(true);
    setMsg('Saving config…');
    try {
      const r = await api('/api/platform/config', {
        method: 'PUT',
        body: JSON.stringify({
          openai_api_key: key,
          openai_base_url: url,
          openai_model: model,
          push_to_apps: pushToApps,
        }),
      });
      const mode = r.llm_mode;
      const pushSummary = buildPushSummary(r.push_results ?? []);
      setMsg(
        (mode === 'configured'
          ? 'LLM connected ✓'
          : mode === 'unreachable'
          ? 'Warning: LLM unreachable'
          : 'Config saved (demo mode)') +
          (pushSummary ? ' · ' + pushSummary : '')
      );
      api('/api/platform/config').then((cfg) => setLlmCfg(cfg)).catch(() => {});
      setShowSettings(false);
      loadHealth();
    } catch (e: any) {
      setMsg('Error: ' + (e.message || 'Unknown'));
    } finally {
      setBusy(false);
    }
  }

  async function pushNow() {
    setBusy(true);
    setMsg('Pushing config to all apps…');
    try {
      const r = await api('/api/platform/config/push', { method: 'POST' });
      setMsg('Pushed · ' + buildPushSummary(r.push_results ?? []));
      loadHealth();
    } catch (e: any) {
      setMsg('Push error: ' + e.message);
    } finally {
      setBusy(false);
    }
  }

  function buildPushSummary(results: PushResult[]): string {
    if (!results.length) return '';
    const ok = results.filter((r) => r.pushed).length;
    const fail = results.filter((r) => !r.pushed);
    let s = `${ok}/${results.length} apps updated`;
    if (fail.length) s += ' · Failed: ' + fail.map((f) => f.id).join(', ');
    return s;
  }

  const llmOk = platformHealth?.llm_mode === 'configured';

  return (
    <div className="platform">
      {/* ── Header ── */}
      <header>
        <div className="header-brand">
          <img
            src="/CapgeminiEngineering_Logo_2COL_RGB.svg"
            alt="Capgemini Engineering"
            className="brand-logo"
            onError={(e) => {
              (e.target as HTMLImageElement).style.display = 'none';
            }}
          />
          <div className="brand-text">
            <span className="brand-title">Velocity AI</span>
            <span className="brand-sub">Platform</span>
          </div>
        </div>
        <div className="header-right">
          <span className={`llm-badge ${llmCfg.has_key ? 'llm-on' : 'llm-off'}`}>
            {llmCfg.has_key ? '● LLM Connected' : '○ Demo Mode'}
          </span>
          <button
            className="icon-btn"
            onClick={loadHealth}
            disabled={healthLoading}
            title="Refresh health"
          >
            {healthLoading ? '⟳' : '↺'}
          </button>
          <button
            className="icon-btn"
            onClick={() => setShowSettings((v) => !v)}
            title="Platform settings"
          >
            ⚙
          </button>
        </div>
      </header>

      {/* ── Settings overlay ── */}
      {showSettings && (
        <SettingsPanel
          cfg={llmCfg}
          busy={busy}
          onSave={saveConfig}
          onPush={pushNow}
          onClose={() => setShowSettings(false)}
        />
      )}

      <main>
        {/* ── Hero ── */}
        <section className="hero">
          <h1>Velocity AI Platform</h1>
          <p className="hero-sub">
            A suite of AI-powered engineering tools. Select an application below to launch it.
          </p>
          {msg && (
            <div className={`platform-msg ${msg.startsWith('Error') || msg.startsWith('Warning') ? 'msg-warn' : 'msg-ok'}`}>
              {msg}
            </div>
          )}
        </section>

        {/* ── Platform status bar ── */}
        <section className="status-bar">
          <div className="status-item">
            <span className="status-dot" style={{ background: platformHealth ? '#4cef9a' : '#aaa' }} />
            <span>Platform backend</span>
            <span className="status-val">{platformHealth ? 'Online' : 'Checking…'}</span>
          </div>
          <div className="status-divider" />
          <div className="status-item">
            <span
              className="status-dot"
              style={{
                background: llmOk ? '#4cef9a' : platformHealth?.llm_mode === 'demo' ? '#aaa' : '#d97706',
              }}
            />
            <span>LLM</span>
            <span className="status-val">
              {platformHealth
                ? platformHealth.llm_mode === 'configured'
                  ? `${platformHealth.llm_model}`
                  : platformHealth.llm_mode === 'demo'
                  ? 'Demo mode'
                  : `${platformHealth.llm_mode}${
                      platformHealth.llm_error ? ' — ' + platformHealth.llm_error : ''
                    }`
                : 'Checking…'}
            </span>
          </div>
          <div className="status-divider" />
          <div className="status-item">
            <span>Apps online</span>
            <span className="status-val">
              {Object.values(health).length > 0
                ? `${Object.values(health).filter((h) => h.reachable).length} / ${Object.values(health).length}`
                : 'Checking…'}
            </span>
          </div>
          <button
            className="push-btn"
            onClick={pushNow}
            disabled={busy || !llmCfg.has_key}
            title={!llmCfg.has_key ? 'Configure an API key first' : 'Push platform LLM config to all apps'}
          >
            ↑ Push config to all apps
          </button>
        </section>

        {/* ── App cards ── */}
        <section className="apps-grid">
          {apps.length === 0 && (
            <p className="no-apps">No applications registered. Check that the platform backend is running.</p>
          )}
          {apps.map((app) => (
            <AppCard
              key={app.id}
              app={app}
              health={health[app.id]}
              process={processes[app.id]}
              onRestart={async (id) => {
                try {
                  await api(`/api/platform/processes/${id}/restart`, { method: 'POST' });
                  setTimeout(() => loadHealth(), 1500);
                } catch (e: any) {
                  setMsg('Restart error: ' + e.message);
                }
              }}
            />
          ))}
        </section>

        {/* ── Footer ── */}
        <footer className="platform-footer">
          <span>Velocity AI Platform · Capgemini Engineering</span>
          <span>Applications run independently — launch them via their individual URLs.</span>
        </footer>
      </main>
    </div>
  );
}

// ─── App Card ─────────────────────────────────────────────────────────────────
function AppCard({
  app,
  health,
  process,
  onRestart,
}: {
  app: AppEntry;
  health?: AppHealth;
  process?: ProcessInfo;
  onRestart: (id: string) => void;
}) {
  const reachable = health?.reachable;
  const checking = health === undefined;
  const procStatus = process?.status ?? 'unknown';
  const isRunning = procStatus === 'running';
  const [restarting, setRestarting] = useState(false);

  function launch() {
    window.open(app.frontend_url, '_blank', 'noopener,noreferrer');
  }

  async function handleRestart(e: React.MouseEvent) {
    e.stopPropagation();
    setRestarting(true);
    await onRestart(app.id);
    setTimeout(() => setRestarting(false), 3000);
  }

  function formatUptime(s: number | null | undefined): string {
    if (s == null) return '';
    if (s < 60) return `${Math.round(s)}s`;
    if (s < 3600) return `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`;
    return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`;
  }

  return (
    <div
      className="app-card"
      style={{ '--card-accent': app.color } as React.CSSProperties}
      onClick={launch}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => e.key === 'Enter' && launch()}
    >
      <div className="card-accent-bar" />
      <div className="card-body">
        <div className="card-header">
          <span className="card-icon">{app.icon}</span>
          <div className="card-title-group">
            <h2 className="card-name">{app.name}</h2>
            <p className="card-tagline">{app.tagline}</p>
          </div>
          <div
            className={`card-health-dot ${
              checking ? 'health-checking' : reachable ? 'health-up' : 'health-down'
            }`}
            title={
              checking
                ? 'Checking…'
                : reachable
                ? `Online · ${health?.llm_mode ?? ''}`
                : `Offline · ${health?.error ?? 'Unreachable'}`
            }
          />
        </div>

        <p className="card-description">{app.description}</p>

        <div className="card-tags">
          {app.tags.map((t) => (
            <span key={t} className="tag">{t}</span>
          ))}
        </div>

        {/* Process info row */}
        {process && (
          <div className="proc-info">
            <span className={`proc-badge ${
              isRunning ? 'proc-running' :
              procStatus.startsWith('exited') ? 'proc-exited' :
              procStatus === 'stopped' ? 'proc-stopped' : 'proc-unknown'
            }`}>
              {isRunning ? '▶' : '■'} backend
            </span>
            {process.pid && <span className="proc-meta">:{process.port}</span>}
            {isRunning && process.uptime_s != null && (
              <span className="proc-meta">up {formatUptime(process.uptime_s)}</span>
            )}
            {process.restarts > 0 && (
              <span className="proc-meta proc-warn">↺ {process.restarts}</span>
            )}
            <span className="proc-divider">|</span>
            <span className={`proc-badge ${
              process.frontend_status === 'running' ? 'proc-running' : 'proc-stopped'
            }`}>
              {process.frontend_status === 'running' ? '▶' : '■'} frontend
            </span>
            {process.frontend_port && (
              <span className="proc-meta">:{process.frontend_port}</span>
            )}
          </div>
        )}

        <div className="card-footer">
          <div className="card-status">
            {checking ? (
              <span className="status-checking">Checking status…</span>
            ) : reachable ? (
              <span className="status-up">
                ● Online
                {health?.llm_mode === 'configured' && <span className="llm-dot"> · LLM ✓</span>}
                {health?.llm_mode === 'demo' && <span className="demo-dot"> · Demo</span>}
              </span>
            ) : (
              <span className="status-down">
                {isRunning ? '◌ Starting…' : '○ Backend offline'}
              </span>
            )}
          </div>
          <div className="card-actions">
            {process && (
              <button
                className="restart-btn"
                onClick={handleRestart}
                disabled={restarting}
                title="Restart backend process"
              >
                {restarting ? '…' : '↺'}
              </button>
            )}
            <button
              className="launch-btn"
              onClick={(e) => { e.stopPropagation(); launch(); }}
            >
              Launch ↗
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Settings Panel ───────────────────────────────────────────────────────────
function SettingsPanel({
  cfg,
  busy,
  onSave,
  onPush,
  onClose,
}: {
  cfg: LlmConfig;
  busy: boolean;
  onSave: (key: string, url: string, model: string, push: boolean) => void;
  onPush: () => void;
  onClose: () => void;
}) {
  const [key, setKey] = useState('');
  const [url, setUrl] = useState(cfg.openai_base_url);
  const [model, setModel] = useState(cfg.openai_model);
  const [show, setShow] = useState(false);
  const [pushToApps, setPushToApps] = useState(true);

  return (
    <div
      className="overlay"
      onClick={(e) => {
        if ((e.target as HTMLElement).classList.contains('overlay')) onClose();
      }}
    >
      <div className="settings-panel">
        <div className="settings-header">
          <h2>⚙ Platform LLM Configuration</h2>
          <button className="close-btn" onClick={onClose}>
            ✕
          </button>
        </div>

        <p className="settings-desc">
          Configure the shared LLM key once here and push it to all application
          backends instantly. Each app can also be configured independently via
          its own settings panel.
        </p>

        <div className="settings-status">
          Source: <b>{cfg.source}</b>
          {cfg.has_key && <span className="badge-on"> ● Connected</span>}
          {!cfg.has_key && <span className="badge-off"> ○ No key</span>}
        </div>

        <label className="field-label">
          API Key
          <div className="key-row">
            <input
              type={show ? 'text' : 'password'}
              value={key}
              onChange={(e) => setKey(e.target.value)}
              placeholder={
                cfg.has_key
                  ? 'Enter new key to replace current'
                  : 'Paste your OpenAI / compatible API key…'
              }
            />
            <button type="button" className="show-btn" onClick={() => setShow((v) => !v)}>
              {show ? 'Hide' : 'Show'}
            </button>
          </div>
        </label>

        <label className="field-label">
          Base URL
          <input
            type="text"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://api.openai.com/v1"
          />
        </label>

        <label className="field-label">
          Model
          <input
            type="text"
            value={model}
            onChange={(e) => setModel(e.target.value)}
            placeholder="gpt-4.1-mini"
          />
        </label>

        <label className="toggle-label">
          <input
            type="checkbox"
            checked={pushToApps}
            onChange={(e) => setPushToApps(e.target.checked)}
          />
          <span>Push this config to all running app backends</span>
        </label>

        <div className="settings-footer">
          <button className="btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button
            className="btn-ghost"
            onClick={onPush}
            disabled={busy || !cfg.has_key}
            title="Push current saved config to apps without changing the key"
          >
            Push existing config ↑
          </button>
          <button
            className="btn-primary"
            disabled={busy || (!key.trim() && !cfg.has_key)}
            onClick={() => onSave(key || '__keep__', url, model, pushToApps)}
          >
            Save &amp; Test
          </button>
        </div>

        <p className="hint">
          The key is saved to <code>platform/backend/.env</code> and survives
          restarts. Individual apps read their own <code>.env</code> unless you
          push from here.
        </p>
      </div>
    </div>
  );
}