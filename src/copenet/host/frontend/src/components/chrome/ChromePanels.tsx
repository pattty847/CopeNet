import { useAppStore } from '../../store/useAppStore';
import { AlertsPanel } from './AlertsPanel';
import { NotebookPanel } from './NotebookPanel';
import { SettingsPanel } from './SettingsPanel';

/** Mounts whichever app-chrome slide-over is open. One at a time, from the top bar on a
 *  desk and from the More sheet on a phone. */
export function ChromePanels() {
  const chromePanel = useAppStore((state) => state.chromePanel);
  const setChromePanel = useAppStore((state) => state.setChromePanel);
  const close = () => setChromePanel(null);

  if (chromePanel === 'settings') return <SettingsPanel onClose={close} />;
  if (chromePanel === 'alerts') return <AlertsPanel onClose={close} />;
  if (chromePanel === 'notebook') return <NotebookPanel onClose={close} />;
  return null;
}
