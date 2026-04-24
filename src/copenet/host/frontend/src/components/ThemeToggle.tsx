import { Moon, SunMedium } from 'lucide-react';
import { useAppStore } from '../store/useAppStore';

export function ThemeToggle() {
  const themeMode = useAppStore((state) => state.themeMode);
  const toggleThemeMode = useAppStore((state) => state.toggleThemeMode);

  return (
    <button
      type="button"
      onClick={toggleThemeMode}
      className="shell-icon-btn inline-flex h-9 w-9 items-center justify-center rounded-xl border border-shell-border bg-shell-panel text-shell-muted transition-all duration-150 hover:border-shell-border-strong hover:text-shell-text hover:shadow-shell"
      title={themeMode === 'light' ? 'Switch to dark mode' : 'Switch to light mode'}
      aria-label={themeMode === 'light' ? 'Switch to dark mode' : 'Switch to light mode'}
    >
      {themeMode === 'light' ? <Moon className="h-3.5 w-3.5" /> : <SunMedium className="h-3.5 w-3.5" />}
    </button>
  );
}
