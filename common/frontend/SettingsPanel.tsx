/**
 * common/frontend/SettingsPanel.tsx
 * ────────────────────────────────────
 * Shared LLM configuration settings panel used by all Velocity AI apps.
 *
 * Usage in any app's App.tsx:
 *
 *   import SettingsPanel, { LlmConfig } from '../../../common/frontend/SettingsPanel';
 *
 *   const [llmCfg, setLlmCfg] = useState<LlmConfig>({ ... });
 *   const [showSettings, setShowSettings] = useState(false);
 *
 *   async function saveConfig(key: string, url: string, model: string) {
 *     const r = await api('/api/config', {
 *       method: 'PUT',
 *       body: JSON.stringify({ openai_api_key: key, openai_base_url: url, openai_model: model }),
 *     });
 *     // handle r.llm_mode ...
 *     api('/api/config').then(cfg => setLlmCfg(cfg));
 *     setShowSettings(false);
 *   }
 *
 *   {showSettings && (
 *     <SettingsPanel
 *       cfg={llmCfg}
 *       onSave={saveConfig}
 *       onClose={() => setShowSettings(false)}
 *       busy={busy}
 *     />
 *   )}
 */

import { useState } from 'react';

/** Shape of the /api/config GET response */
export interface LlmConfig {
  openai_api_key: string;
  openai_base_url: string;
  openai_model: string;
  has_key: boolean;
  source: 'env' | 'runtime' | 'none';
}

interface SettingsPanelProps {
  cfg: LlmConfig;
  onSave: (key: string, baseUrl: string, model: string) => void;
  onClose: () => void;
  busy: boolean;
  /** Optional placeholder model name shown in the model input */
  defaultModelPlaceholder?: string;
}

/**
 * Modal overlay panel that lets users configure the OpenAI-compatible LLM
 * endpoint (API key, base URL, model name) at runtime.
 *
 * - Clicking the overlay backdrop calls onClose.
 * - "Save & Test" calls onSave with (key | '__keep__', url, model).
 *   The '__keep__' sentinel tells the backend not to replace the existing key
 *   when the user leaves the key field blank.
 */
export default function SettingsPanel({
  cfg,
  onSave,
  onClose,
  busy,
  defaultModelPlaceholder = 'gpt-4.1-mini',
}: SettingsPanelProps) {
  const [key, setKey] = useState('');
  const [url, setUrl] = useState(cfg.openai_base_url);
  const [model, setModel] = useState(cfg.openai_model);
  const [showKey, setShowKey] = useState(false);

  function handleBackdropClick(e: React.MouseEvent<HTMLDivElement>) {
    if ((e.target as HTMLElement).classList.contains('settings-overlay')) {
      onClose();
    }
  }

  return (
    <div className="settings-overlay" onClick={handleBackdropClick}>
      <div className="settings-panel">
        {/* Header */}
        <div className="settings-header">
          <h2>⚙ LLM Configuration</h2>
          <button onClick={onClose} aria-label="Close settings">✕</button>
        </div>

        {/* Current source indicator */}
        <p className="settings-status">
          Current source: <b>{cfg.source}</b>
          {cfg.has_key && <span className="llm-on" style={{ marginLeft: 8 }}>● Connected</span>}
        </p>

        {/* API Key */}
        <label>
          API Key
          <div className="key-row">
            <input
              type={showKey ? 'text' : 'password'}
              value={key}
              onChange={e => setKey(e.target.value)}
              placeholder={
                cfg.has_key
                  ? 'Enter new key to replace current'
                  : 'Paste your API key here…'
              }
              autoComplete="off"
            />
            <button type="button" onClick={() => setShowKey(v => !v)}>
              {showKey ? 'Hide' : 'Show'}
            </button>
          </div>
        </label>

        {/* Base URL */}
        <label>
          Base URL
          <input
            type="text"
            value={url}
            onChange={e => setUrl(e.target.value)}
            placeholder="https://api.openai.com/v1"
          />
        </label>

        {/* Model */}
        <label>
          Model
          <input
            type="text"
            value={model}
            onChange={e => setModel(e.target.value)}
            placeholder={defaultModelPlaceholder}
          />
        </label>

        {/* Footer actions */}
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
          Key is saved to the server's <code>.env</code> file and persists
          across restarts.
        </p>
      </div>
    </div>
  );
}
