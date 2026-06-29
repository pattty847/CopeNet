import {
  Activity,
  ArrowRight,
  Bot,
  Database,
  Flame,
  LineChart,
  Play,
  Sparkles,
  WandSparkles,
} from 'lucide-react';
import type { ReactElement } from 'react';
import { MemorySurface } from '../profile/MemorySurface';
import { UserNotesSurface } from '../profile/UserNotesSurface';
import type { Session, WsStatus } from '../../types/backend';
import type { HomeCardId } from './homeLayout';

const HOME_HERO_DARK_URL = '/imgs/wallpaper.png';

export interface HomeCardContext {
  isMobile: boolean;
  isDark: boolean;
  activeSessions: number;
  connectedProviders: number;
  providerCount: number;
  totalMessages: number;
  toolCount: number;
  wsStatus: WsStatus;
  latestSessions: Session[];
  setCurrentSection: (section: 'agents' | 'data-tools' | 'observability' | 'experiments') => void;
  setWorkflowsRoute: (route: 'hub' | 'meme-lab') => void;
  onCreateSession: () => void;
  pulseCount: number;
}

function truncateCopy(value: string | undefined, limit: number): string {
  if (!value) return '';
  return value.length > limit ? `${value.slice(0, Math.max(0, limit - 1)).trimEnd()}…` : value;
}

export function isHomeCardVisible(id: HomeCardId, ctx: HomeCardContext): boolean {
  if (id === 'memory_profile' && ctx.isMobile) return false;
  return true;
}

function HeroStats({ ctx }: { ctx: HomeCardContext }) {
  const stats = [
    { label: 'Active Sessions', value: String(ctx.activeSessions || 0), icon: Bot },
    { label: 'Providers Online', value: `${ctx.connectedProviders}/${ctx.providerCount || 1}`, icon: Database },
    { label: 'Tools Available', value: String(ctx.toolCount || 0), icon: WandSparkles },
    { label: 'Messages Logged', value: String(ctx.totalMessages || 0), icon: Activity },
  ];
  return (
    <div className="shell-home-highlight rounded-[20px] border border-shell-border px-4 py-4 text-shell-text shadow-shell">
      <div className="text-[10px] font-semibold uppercase tracking-[0.22em] text-shell-accent">
        Workspace Signal
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2">
        {stats.map((item) => {
          const Icon = item.icon;
          return (
            <div key={item.label} className="shell-home-metric rounded-[16px] border border-shell-border px-3 py-3">
              <div className="flex items-center justify-between">
                <div className="text-[10px] uppercase tracking-[0.16em] text-shell-muted">{item.label}</div>
                <Icon className="h-3 w-3 text-shell-accent" />
              </div>
              <div className="mt-1 text-[1.35rem] font-semibold tracking-tight text-shell-text">{item.value}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function renderHomeCard(id: HomeCardId, ctx: HomeCardContext): ReactElement {
  switch (id) {
    case 'hero':
      return (
        <div
          data-home-hero={ctx.isDark ? 'cinematic-dark' : undefined}
          className="shell-home-hero relative h-full overflow-hidden rounded-[24px] border border-shell-border bg-shell-panel px-4 py-4 shadow-shell sm:px-7 sm:py-5"
        >
          {ctx.isDark && (
            <>
              <div
                className="shell-home-hero-visual absolute inset-0 bg-cover bg-[center_right] bg-no-repeat"
                style={{ backgroundImage: `url(${HOME_HERO_DARK_URL})` }}
                aria-hidden="true"
              />
              <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(180deg,rgba(5,6,7,0.06),rgba(5,6,7,0.28)_72%,rgba(5,6,7,0.45))]" />
            </>
          )}
          <div className="shell-home-hero-grid h-full">
            <div className="max-w-3xl min-w-0">
              <div className="mb-3 inline-flex max-w-full items-center gap-2 rounded-full border border-shell-accent/15 bg-shell-accent-soft px-3 py-1 text-[9px] font-semibold uppercase tracking-[0.18em] text-shell-accent sm:text-[10px] sm:tracking-[0.2em]">
                <Sparkles className="h-3 w-3" />
                Operator console
              </div>
              <h1 className="max-w-full text-balance font-display text-[1.85rem] leading-[0.98] tracking-tight text-shell-text sm:text-[2.8rem] sm:leading-[0.96]">
                {ctx.isDark ? (
                  <>
                    Intelligence is compounding.
                    <br />
                    <span className="text-shell-accent">Execution is everything.</span>
                  </>
                ) : (
                  'Welcome home to CopeNet.'
                )}
              </h1>
              <p className="mt-2 max-w-xl text-[13px] leading-6 text-shell-muted sm:text-[14px]">
                Sessions, runtimes, and tools — one console. Scan Mission Control for what wants you, or fire up something new.
              </p>

              <div className="relative mt-5 flex max-w-full flex-col items-stretch gap-2 sm:flex-row sm:flex-wrap">
                <button
                  type="button"
                  onClick={() => ctx.onCreateSession()}
                  className="glow-accent grid w-full max-w-full min-w-0 grid-cols-[14px_minmax(0,1fr)] items-center gap-2 overflow-hidden rounded-xl border border-shell-accent/40 bg-shell-accent px-4 py-2.5 text-[13px] font-semibold text-[#1a1209] sm:inline-flex sm:w-auto sm:py-2"
                >
                  <Bot className="h-3.5 w-3.5 shrink-0" />
                  <span className="block min-w-0 truncate text-left">Create agent session</span>
                </button>
                {[
                  { label: 'Open Meme Lab', icon: Play, section: 'agents' as const, openMeme: true },
                  { label: 'New experiment', icon: LineChart, section: 'experiments' as const, openMeme: false },
                  { label: 'Upload data', icon: Database, section: 'data-tools' as const, openMeme: false },
                ].map((action) => (
                  <button
                    key={action.label}
                    type="button"
                    onClick={() => {
                      if (action.openMeme) ctx.setWorkflowsRoute('meme-lab');
                      ctx.setCurrentSection(action.section);
                    }}
                    className="grid w-full max-w-full min-w-0 grid-cols-[14px_minmax(0,1fr)] items-center gap-2 overflow-hidden rounded-xl border border-shell-border bg-shell-panel-strong px-4 py-2.5 text-[13px] font-medium text-shell-text transition-all duration-150 hover:border-shell-border-strong hover:bg-shell-panel sm:inline-flex sm:w-auto sm:py-2"
                  >
                    <action.icon className="h-3.5 w-3.5 shrink-0" />
                    <span className="block min-w-0 truncate text-left">{action.label}</span>
                  </button>
                ))}
              </div>
            </div>

            <div className="hidden min-w-0 self-end lg:block">
              <HeroStats ctx={ctx} />
            </div>
          </div>

          <div className="mt-5 lg:hidden">
            <HeroStats ctx={ctx} />
          </div>
        </div>
      );
    case 'recent_activity':
      return (
        <div className="shell-home-panel h-full rounded-[24px] border border-shell-border bg-shell-panel px-4 py-4 shadow-shell">
          <div className="mb-2.5 flex items-center justify-between">
            <div>
              <h3 className="font-display text-lg tracking-tight text-shell-text">Recent Activity</h3>
              <p className="text-[12px] text-shell-muted">The sessions CopeNet has touched lately</p>
            </div>
            <button
              type="button"
              onClick={() => ctx.setCurrentSection('agents')}
              className="text-[12px] font-medium text-shell-muted transition-colors duration-150 hover:text-shell-accent"
            >
              Open Agents
            </button>
          </div>
          <div className="space-y-1.5">
            {ctx.latestSessions.length > 0 ? (
              ctx.latestSessions.map((session) => (
                <button
                  key={session.key}
                  type="button"
                  onClick={() => ctx.setCurrentSection('agents')}
                  className="flex w-full items-center gap-2.5 overflow-hidden rounded-[14px] border border-shell-border bg-shell-panel-strong px-3 py-2.5 text-left transition-all duration-150 hover:border-shell-border-strong hover:bg-shell-panel hover:shadow-shell"
                >
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-shell-accent-soft text-shell-accent">
                    <Flame className="h-3.5 w-3.5" />
                  </div>
                  <div className="min-w-0 flex-1 overflow-hidden">
                    <div
                      className="truncate text-[13px] font-medium text-shell-text"
                      title={session.title || 'Untitled session'}
                    >
                      {truncateCopy(session.title || 'Untitled session', ctx.isMobile ? 34 : 64)}
                    </div>
                    <div
                      className="truncate text-[11px] text-shell-muted"
                      title={`${session.provider} · ${session.model || 'default runtime'}`}
                    >
                      {truncateCopy(`${session.provider} · ${session.model || 'default runtime'}`, ctx.isMobile ? 42 : 72)}
                    </div>
                  </div>
                  <div className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                    session.archived
                      ? 'bg-shell-panel-strong text-shell-muted'
                      : 'bg-shell-success-soft text-shell-success'
                  }`}>
                    {session.archived ? 'Archived' : 'Active'}
                  </div>
                </button>
              ))
            ) : (
              <div className="rounded-2xl border border-dashed border-shell-border bg-shell-bg px-4 py-5 text-[13px] text-shell-muted">
                No saved sessions yet. Your first draft in Agents will start shaping this workspace.
              </div>
            )}
          </div>
        </div>
      );
    case 'system_health':
      return (
        <div className="shell-home-rail-card h-full rounded-[24px] border border-shell-border bg-shell-panel px-4 py-4 shadow-shell">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="text-[10px] font-semibold uppercase tracking-[0.22em] text-shell-accent">System Health</div>
              <p className="mt-1 text-[12px] leading-5 text-shell-muted">Gateway connection and operator readiness.</p>
            </div>
            <span className={`mt-0.5 rounded-full px-2 py-0.5 text-[10px] font-semibold ${
              ctx.wsStatus === 'connected'
                ? 'bg-shell-success-soft text-shell-success'
                : ctx.wsStatus === 'connecting'
                  ? 'bg-shell-accent-soft text-shell-accent'
                  : 'bg-shell-panel-strong text-shell-error'
            }`}>
              {ctx.wsStatus === 'connected' ? 'Nominal' : ctx.wsStatus === 'connecting' ? 'Retrying' : 'Attention'}
            </span>
          </div>
          <div className="mt-3 rounded-[14px] border border-shell-border bg-shell-panel-strong p-3">
            <div className="flex items-center gap-2 text-[13px] font-medium text-shell-text">
              <span className="relative flex h-2 w-2">
                {ctx.wsStatus === 'connected' && (
                  <span className="pulse-live absolute inline-flex h-full w-full rounded-full bg-shell-success opacity-60" />
                )}
                <span
                  className={`relative inline-flex h-2 w-2 rounded-full ${
                    ctx.wsStatus === 'connected'
                      ? 'bg-shell-success'
                      : ctx.wsStatus === 'connecting'
                        ? 'bg-shell-accent'
                        : 'bg-shell-error'
                  }`}
                />
              </span>
              {ctx.wsStatus === 'connected' ? 'Gateway online' : ctx.wsStatus === 'connecting' ? 'Reconnecting' : 'Disconnected'}
            </div>
            <div className="mt-2.5 space-y-1.5 text-[12px] text-shell-muted">
              <div className="flex items-center justify-between">
                <span>Connected providers</span>
                <span className="font-medium text-shell-text">{ctx.connectedProviders}/{ctx.providerCount || 1}</span>
              </div>
              <div className="flex items-center justify-between">
                <span>Known tools</span>
                <span className="font-medium text-shell-text">{ctx.toolCount}</span>
              </div>
              <div className="flex items-center justify-between">
                <span>Unread pulses</span>
                <span className="font-medium text-shell-text">{ctx.pulseCount}</span>
              </div>
              <div className="flex items-center justify-between">
                <span>Active sessions</span>
                <span className="font-medium text-shell-text">{ctx.activeSessions}</span>
              </div>
            </div>
          </div>
          <button
            type="button"
            onClick={() => ctx.setCurrentSection('observability')}
            className="mt-3 inline-flex items-center gap-1.5 text-[12px] font-medium text-shell-muted transition-colors duration-150 hover:text-shell-accent"
          >
            Open observability
            <ArrowRight className="h-3 w-3" />
          </button>
        </div>
      );
    case 'memory_profile':
      return (
        <div className="grid grid-cols-1 items-start gap-3 lg:grid-cols-2">
          <MemorySurface />
          <UserNotesSurface />
        </div>
      );
  }
}
