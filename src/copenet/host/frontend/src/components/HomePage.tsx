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
import { useMemo } from 'react';
import { useAppStore } from '../store/useAppStore';

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

export function HomePage() {
  const sessions = useAppStore((state) => state.sessions);
  const messages = useAppStore((state) => state.messages);
  const providers = useAppStore((state) => state.providers);
  const tools = useAppStore((state) => state.tools);
  const wsStatus = useAppStore((state) => state.wsStatus);
  const setCurrentSection = useAppStore((state) => state.setCurrentSection);
  const setWorkflowsRoute = useAppStore((state) => state.setWorkflowsRoute);

  const totalMessages = useMemo(
    () => Object.values(messages).reduce((count, sessionMessages) => count + sessionMessages.length, 0),
    [messages],
  );
  const activeSessions = sessions.filter((session) => !session.archived).length;
  const archivedSessions = sessions.filter((session) => session.archived).length;
  const connectedProviders = providers.filter((provider) => provider.available).length;
  const latestSessions = sessions.slice(0, 4);

  const stats = [
    {
      label: 'Active Sessions',
      value: String(activeSessions || 0),
      note: archivedSessions ? `${archivedSessions} archived` : 'Ready for new work',
      icon: Bot,
    },
    {
      label: 'Messages Logged',
      value: String(totalMessages || 0),
      note: 'Append-only history',
      icon: Activity,
    },
    {
      label: 'Providers Online',
      value: `${connectedProviders}/${providers.length || 1}`,
      note: wsStatus === 'connected' ? 'Gateway connected' : 'Reconnecting',
      icon: Database,
    },
    {
      label: 'Tools Available',
      value: String(tools.length || 0),
      note: 'Inspectable execution',
      icon: WandSparkles,
    },
  ];

  return (
    <div className="animate-fade-in-up space-y-3">
      {/* ── Hero + Pinned Agents ── */}
      <section className="grid gap-3 xl:grid-cols-[1.68fr_0.82fr]">
        <div className="space-y-3">
          {/* Hero */}
          <div className="rounded-[24px] border border-shell-border bg-shell-panel px-7 py-5 shadow-shell">
            <div className="max-w-3xl">
              <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-shell-accent/15 bg-shell-accent-soft px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.2em] text-shell-accent">
                <Sparkles className="h-3 w-3" />
                Built to inspire what comes next
              </div>
              <h1 className="font-display text-[2.8rem] leading-[0.96] tracking-tight text-shell-text">
                Welcome home to CopeNet.
              </h1>
              <p className="mt-2 max-w-xl text-[14px] leading-6 text-shell-muted">
                Shape agentic workspaces, keep every tool call inspectable, and turn useful sessions
                into repeatable workflows.
              </p>
            </div>

            <div className="mt-5 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => setCurrentSection('agents')}
                className="glow-accent inline-flex items-center gap-2 rounded-xl bg-shell-ink px-4 py-2 text-[13px] font-semibold text-white"
              >
                <Bot className="h-3.5 w-3.5" />
                Create agent session
              </button>
              {[
                { label: 'Open Meme Lab', icon: Play, section: 'workflows' as const, openMeme: true },
                { label: 'New experiment', icon: LineChart, section: 'experiments' as const, openMeme: false },
                { label: 'Upload data', icon: Database, section: 'data-tools' as const, openMeme: false },
              ].map((action) => (
                <button
                  key={action.label}
                  type="button"
                  onClick={() => {
                    if (action.openMeme) setWorkflowsRoute('meme-lab');
                    setCurrentSection(action.section);
                  }}
                  className="inline-flex items-center gap-2 rounded-xl border border-shell-border bg-shell-panel-strong px-4 py-2 text-[13px] font-medium text-shell-text transition-all duration-150 hover:border-shell-border-strong hover:bg-shell-panel"
                >
                  <action.icon className="h-3.5 w-3.5" />
                  {action.label}
                </button>
              ))}
            </div>
          </div>

          {/* At a glance */}
          <section>
            <div className="mb-2 flex items-center justify-between px-1">
              <h2 className="font-display text-xl tracking-tight text-shell-text">At a glance</h2>
              <button
                type="button"
                onClick={() => setCurrentSection('observability')}
                className="inline-flex items-center gap-1.5 text-[12px] font-medium text-shell-muted transition-colors duration-150 hover:text-shell-accent"
              >
                View all
                <ArrowRight className="h-3 w-3" />
              </button>
            </div>
            <div className="stagger-children grid gap-2 md:grid-cols-2 xl:grid-cols-4">
              {stats.map((stat) => {
                const Icon = stat.icon;
                return (
                  <div key={stat.label} className="lift-sm rounded-[18px] border border-shell-border bg-shell-panel px-4 py-3 shadow-shell">
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

          {/* Recent Activity + Workspaces */}
          <section className="grid gap-3 xl:grid-cols-[1.18fr_0.82fr]">
            {/* Recent Activity */}
            <div className="rounded-[24px] border border-shell-border bg-shell-panel px-4 py-4 shadow-shell">
              <div className="mb-2.5 flex items-center justify-between">
                <div>
                  <h3 className="font-display text-lg tracking-tight text-shell-text">Recent Activity</h3>
                  <p className="text-[12px] text-shell-muted">The work CopeNet is helping you move forward</p>
                </div>
                <button
                  type="button"
                  onClick={() => setCurrentSection('agents')}
                  className="text-[12px] font-medium text-shell-muted transition-colors duration-150 hover:text-shell-accent"
                >
                  Open Agents
                </button>
              </div>
              <div className="space-y-1.5">
                {latestSessions.length > 0 ? (
                  latestSessions.map((session) => (
                    <button
                      key={session.key}
                      type="button"
                      onClick={() => setCurrentSection('agents')}
                      className="flex w-full items-center gap-2.5 rounded-[14px] border border-shell-border bg-shell-panel-strong px-3 py-2.5 text-left transition-all duration-150 hover:border-shell-border-strong hover:bg-shell-panel hover:shadow-shell"
                    >
                      <div className="flex h-8 w-8 items-center justify-center rounded-xl bg-shell-accent-soft text-shell-accent">
                        <Flame className="h-3.5 w-3.5" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-[13px] font-medium text-shell-text">
                          {session.title || 'Untitled session'}
                        </div>
                        <div className="truncate text-[11px] text-shell-muted">
                          {session.provider} · {session.model || 'default runtime'}
                        </div>
                      </div>
                      <div className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${
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

            {/* Workspaces */}
            <div className="rounded-[24px] border border-shell-border bg-shell-panel px-4 py-4 shadow-shell">
              <div className="mb-2.5 flex items-center justify-between">
                <div>
                  <h3 className="font-display text-lg tracking-tight text-shell-text">My Workspaces</h3>
                  <p className="text-[12px] text-shell-muted">Ground context around real work</p>
                </div>
                <button
                  type="button"
                  onClick={() => setCurrentSection('data-tools')}
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
                    onClick={() => setCurrentSection('data-tools')}
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
          </section>

          {/* Bottom trio */}
          <section className="grid gap-3 xl:grid-cols-[1.05fr_1.05fr_0.9fr]">
            <div className="lift rounded-[24px] border border-shell-border bg-[linear-gradient(145deg,var(--color-shell-ink),#252a35)] px-4 py-4 text-white shadow-shell">
              <div className="text-[10px] font-semibold uppercase tracking-[0.2em] text-white/50">Agent Library</div>
              <div className="mt-2 font-display text-xl tracking-tight">Build your own operating crew</div>
              <p className="mt-2 max-w-xs text-[13px] leading-5 text-white/60">
                Pin your best sessions, shape specialist runtimes, and turn repeated tasks into intentional agents.
              </p>
            </div>

            <div className="lift rounded-[24px] border border-shell-border bg-shell-panel px-4 py-4 shadow-shell">
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

            <div className="rounded-[24px] border border-shell-border bg-shell-panel px-4 py-4 shadow-shell">
              <div className="text-[10px] font-semibold uppercase tracking-[0.2em] text-shell-muted">What&apos;s New</div>
              <div className="mt-2 space-y-1.5">
                {NEWS_ITEMS.map((item) => (
                  <div key={item} className="rounded-[12px] border border-shell-border bg-shell-panel-strong px-3 py-2 text-[12px] leading-5 text-shell-text">
                    {item}
                  </div>
                ))}
              </div>
            </div>
          </section>
        </div>

        {/* ── Right sidebar ── */}
        <div className="space-y-3">
          {/* Pinned Agents */}
          <div className="rounded-[24px] border border-shell-border bg-shell-panel px-4 py-4 shadow-shell">
            <div className="mb-2.5 flex items-center justify-between">
              <div>
                <div className="text-[13px] font-semibold text-shell-text">Pinned Agents</div>
                <div className="text-[11px] text-shell-muted">The agents worth returning to</div>
              </div>
              <button type="button" className="flex h-6 w-6 items-center justify-center rounded-lg border border-shell-border text-[13px] text-shell-muted transition-colors duration-150 hover:border-shell-accent/30 hover:text-shell-accent">+</button>
            </div>
            <div className="space-y-1.5">
              {PINNED_AGENTS.map((agent) => (
                <button
                  key={agent.title}
                  type="button"
                  onClick={() => setCurrentSection('agents')}
                  className="flex w-full items-center gap-2.5 rounded-[14px] border border-shell-border bg-shell-panel-strong px-3 py-2 text-left transition-all duration-150 hover:border-shell-border-strong hover:bg-shell-panel hover:shadow-shell"
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

          {/* Quick Starts */}
          <div className="rounded-[24px] border border-shell-border bg-shell-panel px-4 py-4 shadow-shell">
            <h3 className="font-display text-lg tracking-tight text-shell-text">Quick Starts</h3>
            <div className="mt-2 space-y-1">
              {QUICK_STARTS.map((item) => (
                <button
                  key={item.label}
                  type="button"
                  onClick={() => {
                    if (item.target.kind === 'meme-lab') {
                      setWorkflowsRoute('meme-lab');
                      setCurrentSection('workflows');
                    } else {
                      setCurrentSection(item.target.section);
                    }
                  }}
                  className="flex w-full items-center justify-between rounded-[12px] border border-shell-border bg-shell-panel-strong px-3 py-2 text-left text-[13px] text-shell-text transition-all duration-150 hover:border-shell-border-strong hover:bg-shell-panel hover:shadow-shell"
                >
                  <span>{item.label}</span>
                  <ArrowRight className="h-3 w-3 text-shell-muted" />
                </button>
              ))}
            </div>
          </div>

          {/* System Health */}
          <div className="rounded-[24px] border border-shell-border bg-shell-panel px-4 py-4 shadow-shell">
            <h3 className="font-display text-lg tracking-tight text-shell-text">System Health</h3>
            <div className="mt-2 rounded-[14px] border border-shell-border bg-shell-panel-strong p-3">
              <div className="flex items-center gap-2 text-[13px] font-medium text-shell-text">
                <span className="relative flex h-2 w-2">
                  {wsStatus === 'connected' && (
                    <span className="pulse-live absolute inline-flex h-full w-full rounded-full bg-shell-success opacity-60" />
                  )}
                  <span
                    className={`relative inline-flex h-2 w-2 rounded-full ${
                      wsStatus === 'connected'
                        ? 'bg-shell-success'
                        : wsStatus === 'connecting'
                          ? 'bg-shell-accent'
                          : 'bg-shell-error'
                    }`}
                  />
                </span>
                {wsStatus === 'connected' ? 'Gateway online' : wsStatus === 'connecting' ? 'Reconnecting' : 'Disconnected'}
              </div>
              <div className="mt-2.5 space-y-1.5 text-[12px] text-shell-muted">
                <div className="flex items-center justify-between">
                  <span>Connected providers</span>
                  <span className="font-medium text-shell-text">{connectedProviders}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span>Known tools</span>
                  <span className="font-medium text-shell-text">{tools.length}</span>
                </div>
              </div>
            </div>
          </div>

          {/* Performance */}
          <div className="rounded-[24px] border border-shell-border bg-[radial-gradient(circle_at_top_left,rgba(92,200,184,0.06),transparent_50%),var(--color-shell-ink)] px-4 py-4 text-white shadow-shell">
            <div className="flex items-center justify-between">
              <div className="text-[10px] font-semibold uppercase tracking-[0.2em] text-white/50">Performance</div>
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
        </div>
      </section>
    </div>
  );
}
