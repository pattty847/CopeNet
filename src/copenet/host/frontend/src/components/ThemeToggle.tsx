import { Moon, SunMedium } from 'lucide-react';
import { useAppStore } from '../store/useAppStore';

export function ThemeToggle() {
  const themeMode = useAppStore((state) => state.themeMode);
  const toggleThemeMode = useAppStore((state) => state.toggleThemeMode);

  return (
    <button
      type="button"
      onClick={toggleThemeMode}
      className="inline-flex h-11 w-11 items-center justify-center rounded-full border border-shell-border bg-shell-panel-strong text-shell-text transition hover:border-shell-border-strong hover:bg-shell-panel"
      title={themeMode === 'light' ? 'Switch to dark mode' : 'Switch to light mode'}
      aria-label={themeMode === 'light' ? 'Switch to dark mode' : 'Switch to light mode'}
    >
      {themeMode === 'light' ? <Moon className="h-4 w-4" /> : <SunMedium className="h-4 w-4" />}
    </button>
  );
}
