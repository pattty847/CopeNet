import { useCallback, useEffect, useRef, useState } from 'react';
import { wsClient } from '../../../lib/wsClient';
import { DEFAULT_CONFIG } from './model';
import type { ScreenerConfig, ScreenerState } from './types';
const api = wsClient.marketScreeners;

export function useScreeners() {
  const [state, setState] = useState<ScreenerState | null>(null);
  const [config, setConfig] = useState<ScreenerConfig>(DEFAULT_CONFIG);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const initialized = useRef(false);
  const alive = useRef(true);
  const inFlight = useRef(false);
  const reload = useCallback(async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    try {
      const next = await api.state();
      if (!alive.current) return;
      setState(next);
      if (!initialized.current) {
        setConfig(next.config);
        initialized.current = true;
      }
    } catch (reason) {
      if (alive.current) setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      inFlight.current = false;
    }
  }, []);
  useEffect(() => {
    alive.current = true;
    void reload();
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible') void reload();
    }, 3000);
    return () => {
      alive.current = false;
      window.clearInterval(timer);
    };
  }, [reload]);
  const act = async (action: () => Promise<void>) => {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      await action();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  };
  return { state, setState, config, setConfig, busy, error, setError, notice, setNotice, reload, act };
}
