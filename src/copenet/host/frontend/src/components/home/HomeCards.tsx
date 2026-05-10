import {
  Activity,
  ArrowRight,
  Bot,
  BriefcaseBusiness,
  Clock3,
  Database,
  Flame,
  LineChart,
  Play,
  Sparkles,
  WandSparkles,
} from 'lucide-react';
import type { ReactElement } from 'react';
import { MemorySurface } from '../profile/MemorySurface';
import { ProfileChangelog } from '../profile/ProfileChangelog';
import { ProfileStatusCard } from '../profile/ProfileStatusCard';
import type { Session, WsStatus } from '../../types/backend';
import type { HomeCardId } from './homeLayout';

const HOME_HERO_DARK_URL = new URL('../../../../../../docs/imgs/wallpaper.png', import.meta.url).href;

const PINNED_AGENTS = [
  { title: 'Research Scout', subtitle: 'Find patterns across notes, feeds, and docs', accent: 'bg-[#edf2ff] text-[#4c68d7]', darkAccent: 'dark:bg-[#1c2340] dark:text-[#7b93e8]' },
  { title: 'Signal Operator', subtitle: 'Watch live runs and summarize what changed', accent: 'bg-[#fff0e6] text-[#d17b43]', darkAccent: 'dark:bg-[#2a1f14] dark:text-[#e0a070]' },
  { title: 'Workflow Editor', subtitle: 'Turn repeated chats into reusable sequences', accent: 'bg-[#efe9ff] text-[#8a59db]', darkAccent: 'dark:bg-[#201a30] dark:text-[#b08ae8]' },
  { title: 'Knowledge Curator', subtitle: 'Keep your workspace context fresh and grounded', accent: 'bg-[#fff4ea] text-[#cc8350]', darkAccent: 'dark:bg-[#2a1f14] dark:text-[#d4a070]' },
];

type QuickStartTarget =
  | { kind: 'section'; section: 'agents' | 'data-tools' | 'experiments' }
  | { kind: 'meme-lab' };

const QUICK_STARTS: { label: string; target: QuickStartTarget }[] = [
  { label: 'Build a new agent', target: { kind: 'section', section: 'agents' } },
  { label: 'Open Meme Lab', target: { kind: 'meme-lab' } },
  { label: 'Connect a knowledge base', target: { kind: 'section', section: 'data-tools' } },
  { label: 'Compare two runtimes', target: { kind: 'section', section: 'experiments' } },
];

const WORKSPACES = [
  { title: 'Sentinel Market Flows', subtitle: 'Liquidity notes, structure reports, and recurring probes', meta: '3 agents · 2 feeds · 6 workflows' },
  { title: 'CopeNet Core', subtitle: 'Repo sessions, probe results, and provider debugging', meta: '4 agents · 1 repo · 9 traces' },
  { title: 'Research Vault', subtitle: 'Long-form notes, source files, and inspiration prompts', meta: '2 agents · 18 docs · 4 experiments' },
];

const NEWS_ITEMS = [
  'Experiment cards are ready for real provider comparisons next.',
  'Tool traces now render inline and stay visible per session.',
  'The new Home page is meant to inspire what to build, not just what to click.',
];

export interface HomeStatsItem {
  label: string;
  value: string;
  note: string;
  icon: typeof Activity;
}

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
  stats: HomeStatsItem[];
  showChangelog: boolean;
  setShowChangelog: (value: boolean | ((prev: boolean) => boolean)) => void;
  setCurrentSection: (section: 'agents' | 'data-tools' | 'observability' | 'experiments') => void;
  setWorkflowsRoute: (route: 'hub' | 'meme-lab') => void;
  pulseCount: number;
}

function truncateCopy(value: string | undefined, limit: number): string {
  if (!value) return '';
  return value.length > limit ? `${value.slice(0, Math.max(0, limit - 1)).trimEnd()}…` : value;
}

function runQuickStart(target: QuickStartTarget, ctx: HomeCardContext) {
  if (target.kind === 'meme-lab') {
    ctx.setWorkflowsRoute('meme-lab');
    ctx.setCurrentSection('agents');
    return;
  }
  ctx.setCurrentSection(target.section);
}

export function isHomeCardVisible(id: HomeCardId, ctx: HomeCardContext): boolean {
  if (id === 'memory_profile' && ctx.isMobile) return false;
  return true;
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
                Built to inspire what comes next
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
                Shape agentic workspaces, keep every tool call inspectable, and turn useful sessions
                into repeatable workflows.
              </p>
            </div>

            {ctx.isDark && (
              <div className="hidden min-w-0 self-end lg:block">
                <div className="shell-home-highlight rounded-[20px] border border-shell-border px-4 py-4 text-shell-text shadow-shell">
                  <div className="text-[10px] font-semibold uppercase tracking-[0.22em] text-shell-accent">
                    Workspace Signal
                  </div>
                  <div className="mt-3 grid grid-cols-2 gap-2">
                    {[
                      { label: 'Active Sessions', value: String(ctx.activeSessions || 0) },
                      { label: 'Providers Online', value: `${ctx.connectedProviders}/${ctx.providerCount || 1}` },
                      { label: 'Tools Available', value: String(ctx.toolCount || 0) },
                      { label: 'Messages Logged', value: String(ctx.totalMessages || 0) },
                    ].map((item) => (
                      <div key={item.label} className="shell-home-metric rounded-[16px] border border-shell-border px-3 py-3">
                        <div className="text-[10px] uppercase tracking-[0.16em] text-shell-muted">{item.label}</div>
                        <div className="mt-1 text-[1.35rem] font-semibold tracking-tight text-shell-text">{item.value}</div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>

          <div className="relative mt-5 flex max-w-full flex-col items-stretch gap-2 sm:flex-row sm:flex-wrap">
            <button
              type="button"
              onClick={() => ctx.setCurrentSection('agents')}
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
      );
    case 'glance':
      return (
        <section className="h-full">
          <div className="mb-2 flex items-center justify-between px-1">
            <h2 className="font-display text-xl tracking-tight text-shell-text">At a glance</h2>
            <button
              type="button"
              onClick={() => ctx.setCurrentSection('observability')}
              className="inline-flex items-center gap-1.5 text-[12px] font-medium text-shell-muted transition-colors duration-150 hover:text-shell-accent"
            >
              View all
              <ArrowRight className="h-3 w-3" />
            </button>
          </div>
          <div className="stagger-children grid h-[calc(100%-2rem)] items-start gap-2 md:grid-cols-2 xl:grid-cols-4">
            {ctx.stats.map((stat) => {
              const Icon = stat.icon;
              return (
                <div key={stat.label} className="shell-home-panel lift-sm rounded-[18px] border border-shell-border bg-shell-panel px-4 py-3 shadow-shell">
                  <div className="mb-2 flex items-center justify-between">
                    <span className="text-[12px] text-shell-muted">{stat.label}</span>
                    <div className="flex h-6 w-6 items-center justify-center rounded-lg bg-shell-accent-soft text-shell-accent">
                      <Icon className="h-3 w-3" />
                    </div>
                  </div>
                  <div className="text-[1.5rem] font-semibold tracking-tight text-shell-text">{stat.value}</div>
                  <div className="mt-0.5 text-[11px] text-shell-muted">{stat.note}</div>
                </div>
              );
            })}
          </div>
        </section>
      );
    case 'quick_starts':
      return (
        <div className="shell-home-rail-card h-full rounded-[20px] border border-shell-border bg-shell-panel px-4 py-4 shadow-shell">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="text-[10px] font-semibold uppercase tracking-[0.22em] text-shell-accent">
                Quick Starts
              </div>
              <p className="mt-1 text-[12px] leading-5 text-shell-muted">
                The shortest useful paths when you want to move without digging.
              </p>
            </div>
            <ArrowRight className="mt-0.5 h-3.5 w-3.5 text-shell-muted" />
          </div>
          <div className="mt-3 space-y-1.5">
            {QUICK_STARTS.map((item) => (
              <button
                key={item.label}
                type="button"
                onClick={() => runQuickStart(item.target, ctx)}
                className="flex w-full items-center justify-between rounded-[14px] border border-shell-border bg-shell-panel-strong px-3 py-2.5 text-left text-[13px] text-shell-text transition-all duration-150 hover:border-shell-border-strong hover:bg-shell-panel hover:shadow-shell"
              >
                <span>{item.label}</span>
                <ArrowRight className="h-3 w-3 text-shell-muted" />
              </button>
            ))}
          </div>
        </div>
      );
    case 'recent_activity':
      return (
        <div className="shell-home-panel h-full rounded-[24px] border border-shell-border bg-shell-panel px-4 py-4 shadow-shell">
          <div className="mb-2.5 flex items-center justify-between">
            <div>
              <h3 className="font-display text-lg tracking-tight text-shell-text">Recent Activity</h3>
              <p className="text-[12px] text-shell-muted">The work CopeNet is helping you move forward</p>
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
    case 'workspaces':
      return (
        <div className="shell-home-panel h-full rounded-[24px] border border-shell-border bg-shell-panel px-4 py-4 shadow-shell">
          <div className="mb-2.5 flex items-center justify-between">
            <div>
              <h3 className="font-display text-lg tracking-tight text-shell-text">My Workspaces</h3>
              <p className="text-[12px] text-shell-muted">Ground context around real work</p>
            </div>
            <button
              type="button"
              onClick={() => ctx.setCurrentSection('data-tools')}
              className="text-[12px] font-medium text-shell-muted transition-colors duration-150 hover:text-shell-accent"
            >
              Manage
            </button>
          </div>
          <div className="space-y-1.5">
            {WORKSPACES.map((workspace) => (
              <button
                key={workspace.title}
                type="button"
                onClick={() => ctx.setCurrentSection('data-tools')}
                className="flex w-full items-start gap-2.5 rounded-[14px] border border-shell-border bg-shell-panel-strong px-3 py-2.5 text-left transition-all duration-150 hover:border-shell-border-strong hover:bg-shell-panel hover:shadow-shell"
              >
                <div className="mt-0.5 flex h-8 w-8 items-center justify-center rounded-xl bg-shell-panel-strong text-shell-accent">
                  <BriefcaseBusiness className="h-3.5 w-3.5" />
                </div>
                <div className="min-w-0">
                  <div className="truncate text-[13px] font-medium text-shell-text">{workspace.title}</div>
                  <div className="mt-0.5 text-[11px] leading-4 text-shell-muted">{workspace.subtitle}</div>
                  <div className="mt-1.5 text-[10px] font-medium uppercase tracking-[0.16em] text-shell-muted">
                    {workspace.meta}
                  </div>
                </div>
              </button>
            ))}
          </div>
        </div>
      );
    case 'agent_library':
      return (
        <div className="shell-home-highlight lift h-full rounded-[24px] border border-shell-border bg-[linear-gradient(145deg,var(--color-shell-ink),#252a35)] px-4 py-4 text-white shadow-shell">
          <div className="text-[10px] font-semibold uppercase tracking-[0.2em] text-white/50">Agent Library</div>
          <div className="mt-2 font-display text-xl tracking-tight">Build your own operating crew</div>
          <p className="mt-2 max-w-xs text-[13px] leading-5 text-white/60">
            Pin your best sessions, shape specialist runtimes, and turn repeated tasks into intentional agents.
          </p>
        </div>
      );
    case 'playbook_library':
      return (
        <div className="shell-home-panel lift h-full rounded-[24px] border border-shell-border bg-shell-panel px-4 py-4 shadow-shell">
          <div className="text-[10px] font-semibold uppercase tracking-[0.2em] text-shell-muted">Playbook Library</div>
          <div className="mt-2 font-display text-xl tracking-tight text-shell-text">Replay what works</div>
          <p className="mt-2 text-[13px] leading-5 text-shell-muted">
            Turn useful prompts, tool traces, and session patterns into reusable workflows.
          </p>
          <div className="mt-3 flex items-center gap-2 text-[13px] font-medium text-shell-text">
            <Play className="h-3.5 w-3.5 text-shell-accent" />
            Runbooks, experiments, and recurring analysis
          </div>
        </div>
      );
    case 'whats_new':
      return (
        <div className="shell-home-panel h-full rounded-[24px] border border-shell-border bg-shell-panel px-4 py-4 shadow-shell">
          <div className="text-[10px] font-semibold uppercase tracking-[0.2em] text-shell-muted">What&apos;s New</div>
          <div className="mt-2 space-y-1.5">
            {NEWS_ITEMS.map((item) => (
              <div key={item} className="rounded-[12px] border border-shell-border bg-shell-panel-strong px-3 py-2 text-[12px] leading-5 text-shell-text">
                {item}
              </div>
            ))}
          </div>
        </div>
      );
    case 'memory_profile':
      return (
        <div className="space-y-3">
          <MemorySurface />
          <ProfileStatusCard onViewChangelog={() => ctx.setShowChangelog((v) => !v)} />
          {ctx.showChangelog && (
            <div className="shell-home-panel rounded-[24px] border border-shell-border bg-shell-panel px-4 py-4 shadow-shell">
              <div className="mb-3 flex items-center justify-between">
                <div className="text-[10px] font-semibold uppercase tracking-[0.22em] text-shell-accent">
                  Profile History
                </div>
                <button
                  type="button"
                  onClick={() => ctx.setShowChangelog(false)}
                  className="text-[11px] text-shell-muted transition-colors duration-150 hover:text-shell-text"
                >
                  Close
                </button>
              </div>
              <ProfileChangelog limit={8} />
            </div>
          )}
        </div>
      );
    case 'pinned_agents':
      return (
        <div className="shell-home-panel h-full rounded-[24px] border border-shell-border bg-shell-panel px-4 py-4 shadow-shell">
          <div className="mb-2.5 flex items-center justify-between">
            <div>
              <div className="text-[10px] font-semibold uppercase tracking-[0.22em] text-shell-accent">Pinned Agents</div>
              <div className="mt-1 text-[12px] text-shell-muted">The agents worth returning to when a job becomes a role.</div>
            </div>
            <button type="button" className="flex h-6 w-6 items-center justify-center rounded-lg border border-shell-border text-[13px] text-shell-muted transition-colors duration-150 hover:border-shell-accent/30 hover:text-shell-accent">+</button>
          </div>
          <div className="space-y-1.5">
            {PINNED_AGENTS.map((agent) => (
              <button
                key={agent.title}
                type="button"
                onClick={() => ctx.setCurrentSection('agents')}
                className="group flex w-full items-center gap-2.5 rounded-[14px] border border-shell-border bg-shell-panel-strong px-3 py-2 text-left transition-all duration-150 hover:border-shell-border-strong hover:bg-shell-panel hover:shadow-shell"
              >
                <div className={`flex h-8 w-8 items-center justify-center rounded-xl ${agent.accent} ${agent.darkAccent}`}>
                  <Bot className="h-3.5 w-3.5" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-[13px] font-medium text-shell-text">{agent.title}</div>
                  <div className="truncate text-[11px] text-shell-muted">{agent.subtitle}</div>
                </div>
                <ArrowRight className="h-3 w-3 text-shell-muted transition-transform duration-150 group-hover:translate-x-0.5" />
              </button>
            ))}
          </div>
        </div>
      );
    case 'system_health':
      return (
        <div className="shell-home-rail-card h-full rounded-[24px] border border-shell-border bg-shell-panel px-4 py-4 shadow-shell">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="text-[10px] font-semibold uppercase tracking-[0.22em] text-shell-accent">System Health</div>
              <p className="mt-1 text-[12px] leading-5 text-shell-muted">Connection state and operator readiness.</p>
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
          <div className="mt-2 rounded-[14px] border border-shell-border bg-shell-panel-strong p-3">
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
                <span className="font-medium text-shell-text">{ctx.connectedProviders}</span>
              </div>
              <div className="flex items-center justify-between">
                <span>Known tools</span>
                <span className="font-medium text-shell-text">{ctx.toolCount}</span>
              </div>
              <div className="flex items-center justify-between">
                <span>Unread pulses</span>
                <span className="font-medium text-shell-text">{ctx.pulseCount}</span>
              </div>
            </div>
          </div>
        </div>
      );
    case 'performance':
      return (
        <div className="shell-home-highlight h-full rounded-[24px] border border-shell-border bg-[radial-gradient(circle_at_top_left,rgba(242,163,58,0.08),transparent_52%),var(--color-shell-ink)] px-4 py-4 text-white shadow-shell">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-[10px] font-semibold uppercase tracking-[0.2em] text-white/50">Performance</div>
              <div className="mt-1 text-[12px] text-white/45">Low-noise system signal, kept secondary on purpose.</div>
            </div>
            <Clock3 className="h-3.5 w-3.5 text-white/40" />
          </div>
          <div className="mt-3 space-y-2">
            <div className="h-16 rounded-[14px] border border-white/8 bg-white/4 p-3">
              <div className="mt-6 h-0.5 w-full bg-gradient-to-r from-white/15 via-shell-accent to-white/40 opacity-70" />
            </div>
            <div className="text-[12px] leading-5 text-white/50">
              Enough signal to keep pushing. Enough shape to inspire what comes next.
            </div>
          </div>
        </div>
      );
  }
}
