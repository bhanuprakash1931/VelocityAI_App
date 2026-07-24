/**
 * common/frontend/useLlmConfig.ts
 * ─────────────────────────────────
 * Shared React hook that manages LLM configuration state for all
 * Velocity AI frontend applications.
 *
 * Handles:
 *   - Fetching current config from GET /api/config on mount.
 *   - Saving new config via PUT /api/config.
 *   - Exposing llmCfg, showSettings toggle, saveConfig, and status message.
 *
 * Usage in any app's App.tsx:
 *
 *   import { useLlmConfig } from '../../../common/frontend/useLlmConfig';
 *
 *   export default function App() {
 *     const {
 *       llmCfg,
 *       showSettings, setShowSettings,
 *       saveConfig,
 *       busy, msg, setMsg, setBusy,
 *     } = useLlmConfig();
 *     ...
 *   }
 */

import { useEffect, useState } from 'react';
import { api } from './api';
import type { LlmConfig } from './SettingsPanel';

export interface UseLlmConfigReturn {
  /** Current LLM configuration as returned by GET /api/config */
  llmCfg: LlmConfig;
  /** Refresh llmCfg from the server */
  refreshConfig: () => void;
  /** Whether the settings panel is visible */
  showSettings: boolean;
  setShowSettings: (v: boolean | ((prev: boolean) => boolean)) => void;
  /**
   * Save new config via PUT /api/config.
   * Pass '__keep__' as key to keep the existing server-side key unchanged.
   */
  saveConfig: (key: string, url: string, model: string) => Promise<void>;
  /** Global busy flag (true while any async operation is in flight) */
  busy: boolean;
  setBusy: (v: boolean) => void;
  /** Global status message shown in the header */
  msg: string;
  setMsg: (v: string) => void;
}

/** Default LLM config values used before the server responds */
const DEFAULT_CONFIG: LlmConfig = {
  openai_api_key: '',
  openai_base_url: 'https://api.openai.com/v1',
  openai_model: 'gpt-4.1-mini',
  has_key: false,
  source: 'none',
};

/**
 * Hook that centralises LLM configuration management.
 *
 * @param initialMsg  Initial status message (default: 'Ready').
 */
export function useLlmConfig(
  initialMsg = 'Ready',
): UseLlmConfigReturn {
  const [llmCfg, setLlmCfg] = useState<LlmConfig>(DEFAULT_CONFIG);
  const [showSettings, setShowSettings] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(initialMsg);

  function refreshConfig() {
    api('/api/config')
      .then((cfg: LlmConfig) => setLlmCfg(cfg))
      .catch(() => {/* silently ignore — server may not be ready yet */});
  }

  // Fetch config once on mount
  useEffect(() => {
    refreshConfig();
  }, []);

  async function saveConfig(
    key: string,
    url: string,
    model: string,
  ): Promise<void> {
    setBusy(true);
    setMsg('Saving config…');
    try {
      const r = await api('/api/config', {
        method: 'PUT',
        body: JSON.stringify({
          openai_api_key: key,
          openai_base_url: url,
          openai_model: model,
        }),
      });

      if (r.llm_mode === 'configured') {
        setMsg('LLM connected ✓');
      } else if (r.llm_mode === 'unreachable') {
        setMsg('Warning: LLM unreachable — ' + (r.llm_error ?? ''));
      } else {
        setMsg('Config saved (demo mode)');
      }

      refreshConfig();
      setShowSettings(false);
    } catch (e: any) {
      setMsg('Error: ' + (e?.message ?? 'Unknown'));
    } finally {
      setBusy(false);
    }
  }

  return {
    llmCfg,
    refreshConfig,
    showSettings,
    setShowSettings,
    saveConfig,
    busy,
    setBusy,
    msg,
    setMsg,
  };
}
