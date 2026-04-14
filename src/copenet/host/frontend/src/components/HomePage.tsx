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

const QUICK_ACTIONS = [
  'Create agent',
  'Run workflow',
  'Start experiment',
  'Connect data',
];

const PINNED_AGENTS = [
  { title: 'Research Scout', subtitle: 'Find patterns across notes, feeds, and docs', accent: 'bg-[#edf2ff] text-[#4c68d7]' },
  { title: 'Signal Operator', subtitle: 'Watch live runs and summarize what changed', accent: 'bg-[#fff0e6] text-[#d17b43]' },
  { title: 'Workflow Editor', subtitle: 'Turn repeated chats into reusable sequences', accent: 'bg-[#efe9ff] text-[#8a59db]' },
  { title: 'Knowledge Curator', subtitle: 'Keep your workspace context fresh and grounded', accent: 'bg-[#fff4ea] text-[#cc8350]' },
];

const QUICK_STARTS = [
  'Build a new agent',
  'Run a playbook',
  'Connect a knowledge base',
  'Compare two runtimes',
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

  const totalMessages = useMemo(
    () => Object.values(messages).reduce((count, sessionMessages) => count + sessionMessages.length, 0),
    [messages],
  );
  const activeSessions = sessions.filter((session) => !session.archived).length;
  const archivedSessions = sessions.filter((session) => session.archived).length;
  const connectedProviders = providers.filter((provider) => provider.available).length;
  const latestSessions = sessions.slice(0, 5);

  const stats = [
    {
      label: 'Active Sessions',
      value: String(activeSessions || 0),
      note: archivedSessions ? `${archivedSessions} archived for later` : 'Ready for new work',
      icon: Bot,
    },
    {
      label: 'Messages Logged',
      value: String(totalMessages || 0),
      note: 'Append-only conversation history',
      icon: Activity,
    },
    {
      label: 'Providers Online',
      value: `${connectedProviders}/${providers.length || 1}`,
      note: wsStatus === 'connected' ? 'Gateway connected' : 'Gateway reconnecting',
      icon: Database,
    },
    {
      label: 'Tools Available',
      value: String(tools.length || 0),
      note: 'Inspectable, traceable execution',
      icon: WandSparkles,
    },
  ];

  return (
    <div className="space-y-4">
      <section className="grid gap-4 xl:grid-cols-[1.68fr_0.82fr]">
        <div className="space-y-4">
          <div className="rounded-[30px] border border-shell-border bg-shell-panel px-8 py-7 shadow-shell">
          <div className="max-w-3xl">
            <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-shell-border bg-shell-panel-strong px-4 py-1.5 text-[11px] font-semibold uppercase tracking-[0.22em] text-shell-muted">
              <Sparkles className="h-3.5 w-3.5 text-shell-accent" />
              Built to inspire what comes next
            </div>
            <h1 className="font-display text-[3.6rem] leading-[0.94] tracking-tight text-shell-text">
              Welcome home to CopeNet.
            </h1>
            <p className="mt-3 max-w-2xl text-[16px] leading-7 text-shell-muted">
              Shape agentic workspaces, keep every tool call inspectable, and turn useful sessions
              into repeatable workflows. The point is not just to chat. It is to build momentum.
            </p>
          </div>

          <div className="mt-7 flex flex-wrap justify-center gap-3">
            <button
              type="button"
              onClick={() => setCurrentSection('agents')}
              className="inline-flex items-center gap-2 rounded-full bg-shell-ink px-5 py-3 text-sm font-semibold text-white transition hover:opacity-92"
            >
              <Bot className="h-4 w-4" />
              Create agent session
            </button>
            <button
              type="button"
              onClick={() => setCurrentSection('workflows')}
              className="inline-flex items-center gap-2 rounded-full border border-shell-border bg-shell-panel-strong px-5 py-3 text-sm font-medium text-shell-text transition hover:border-shell-border-strong hover:bg-shell-panel"
            >
              <Play className="h-4 w-4" />
              Run playbook
            </button>
            <button
              type="button"
              onClick={() => setCurrentSection('experiments')}
              className="inline-flex items-center gap-2 rounded-full border border-shell-border bg-shell-panel-strong px-5 py-3 text-sm font-medium text-shell-text transition hover:border-shell-border-strong hover:bg-shell-panel"
            >
              <LineChart className="h-4 w-4" />
              New experiment
            </button>
            <button
              type="button"
              onClick={() => setCurrentSection('data-tools')}
              className="inline-flex items-center gap-2 rounded-full border border-shell-border bg-shell-panel-strong px-5 py-3 text-sm font-medium text-shell-text transition hover:border-shell-border-strong hover:bg-shell-panel"
            >
              <Database className="h-4 w-4" />
              Upload data
            </button>
          </div>
        </div>
          <section>
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-lg font-semibold tracking-tight text-shell-text">At a glance</h2>
              <button
                type="button"
                onClick={() => setCurrentSection('observability')}
                className="inline-flex items-center gap-2 text-sm font-medium text-shell-muted transition hover:text-shell-text"
              >
                View all
                <ArrowRight className="h-4 w-4" />
              </button>
            </div>
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              {stats.map((stat) => {
                const Icon = stat.icon;
                return (
                  <div key={stat.label} className="rounded-[24px] border border-shell-border bg-shell-panel px-5 py-4 shadow-shell">
                    <div className="mb-3 flex items-center justify-between">
                      <span className="text-sm text-shell-muted">{stat.label}</span>
                      <div className="flex h-7 w-7 items-center justify-center rounded-full bg-shell-accent-soft text-shell-accent">
                        <Icon className="h-3.5 w-3.5" />
                      </div>
                    </div>
                    <div className="text-[2.15rem] font-semibold tracking-tight text-shell-text">{stat.value}</div>
                    <div className="mt-1.5 text-[13px] text-shell-muted">{stat.note}</div>
                  </div>
                );
              })}
            </div>
          </section>

          <section className="grid gap-4 xl:grid-cols-[1.18fr_0.82fr]">
            <div className="rounded-[30px] border border-shell-border bg-shell-panel px-5 py-5 shadow-shell">
          <div className="mb-3 flex items-center justify-between">
            <div>
              <h3 className="text-lg font-semibold text-shell-text">Recent Activity</h3>
              <p className="text-sm text-shell-muted">The work CopeNet is helping you move forward</p>
            </div>
            <button
              type="button"
              onClick={() => setCurrentSection('agents')}
              className="text-sm font-medium text-shell-muted transition hover:text-shell-text"
            >
              Open Agents
            </button>
          </div>
          <div className="space-y-2.5">
            {latestSessions.length > 0 ? (
              latestSessions.map((session) => (
                <button
                  key={session.key}
                  type="button"
                  onClick={() => setCurrentSection('agents')}
                  className="flex w-full items-center gap-3 rounded-[22px] border border-shell-border bg-shell-panel-strong px-4 py-3 text-left transition hover:border-shell-border-strong hover:bg-shell-panel"
                >
                  <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-shell-accent-soft text-shell-accent">
                    <Flame className="h-4 w-4" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm font-semibold text-shell-text">
                      {session.title || 'Untitled session'}
                    </div>
                    <div className="truncate text-xs text-shell-muted">
                      {session.provider} · {session.model || 'default runtime'}
                    </div>
                  </div>
                  <div className="rounded-full bg-shell-success-soft px-3 py-1 text-[11px] font-semibold text-shell-success">
                    {session.archived ? 'Archived' : 'Active'}
                  </div>
                </button>
              ))
            ) : (
              <div className="rounded-3xl border border-dashed border-shell-border bg-shell-bg px-5 py-6 text-sm text-shell-muted">
                No saved sessions yet. Your first draft in Agents will start shaping this workspace.
              </div>
            )}
          </div>
        </div>

            <div className="rounded-[30px] border border-shell-border bg-shell-panel px-5 py-5 shadow-shell">
          <div className="mb-3 flex items-center justify-between">
            <div>
              <h3 className="text-lg font-semibold text-shell-text">My Workspaces</h3>
              <p className="text-sm text-shell-muted">Ground context around real work</p>
            </div>
            <button
              type="button"
              onClick={() => setCurrentSection('data-tools')}
              className="text-sm font-medium text-shell-muted transition hover:text-shell-text"
            >
              Manage
            </button>
          </div>
          <div className="space-y-2.5">
            {WORKSPACES.map((workspace) => (
              <button
                key={workspace.title}
                type="button"
                onClick={() => setCurrentSection('data-tools')}
                className="flex w-full items-start gap-3 rounded-[22px] border border-shell-border bg-shell-panel-strong px-4 py-3 text-left transition hover:border-shell-border-strong hover:bg-shell-panel"
              >
                <div className="mt-0.5 flex h-10 w-10 items-center justify-center rounded-2xl bg-shell-panel-strong text-shell-accent">
                  <BriefcaseBusiness className="h-4 w-4" />
                </div>
                <div className="min-w-0">
                  <div className="truncate text-sm font-semibold text-shell-text">{workspace.title}</div>
                  <div className="mt-1 text-xs leading-5 text-shell-muted">{workspace.subtitle}</div>
                  <div className="mt-2 text-[11px] font-medium uppercase tracking-[0.18em] text-shell-muted">
                    {workspace.meta}
                  </div>
                </div>
              </button>
            ))}
          </div>
        </div>
          </section>

          <section className="grid gap-4 xl:grid-cols-[1.05fr_1.05fr_0.9fr]">
            <div className="rounded-[30px] border border-shell-border bg-[linear-gradient(145deg,var(--color-shell-ink),#2d3340)] px-5 py-5 text-white shadow-shell">
              <div className="text-xs font-semibold uppercase tracking-[0.22em] text-white/60">Agent Library</div>
              <div className="mt-3 text-2xl font-semibold tracking-tight">Build your own operating crew</div>
              <p className="mt-2.5 max-w-xs text-sm leading-6 text-white/70">
                Pin your best sessions, shape specialist runtimes, and turn repeated tasks into intentional agents.
              </p>
            </div>

            <div className="rounded-[30px] border border-shell-border bg-shell-panel px-5 py-5 shadow-shell">
              <div className="text-xs font-semibold uppercase tracking-[0.22em] text-shell-muted">Playbook Library</div>
              <div className="mt-3 text-2xl font-semibold tracking-tight text-shell-text">Replay what works</div>
              <p className="mt-2.5 text-sm leading-6 text-shell-muted">
                The next layer is turning useful prompts, tool traces, and session patterns into reusable workflows.
              </p>
              <div className="mt-5 flex items-center gap-3 text-sm font-medium text-shell-text">
                <Play className="h-4 w-4 text-shell-accent" />
                Runbooks, experiments, and recurring analysis
              </div>
            </div>

            <div className="rounded-[30px] border border-shell-border bg-shell-panel px-5 py-5 shadow-shell">
              <div className="text-xs font-semibold uppercase tracking-[0.22em] text-shell-muted">What&apos;s New</div>
              <div className="mt-3 space-y-3">
                {NEWS_ITEMS.map((item) => (
                  <div key={item} className="rounded-[22px] border border-shell-border bg-shell-panel-strong px-4 py-3 text-sm leading-6 text-shell-text">
                    {item}
                  </div>
                ))}
              </div>
            </div>
          </section>
        </div>

        <div className="space-y-4">
          <div className="rounded-[30px] border border-shell-border bg-shell-panel px-5 py-5 shadow-shell">
            <div className="mb-3 flex items-center justify-between">
              <div>
                <div className="text-sm font-semibold text-shell-text">Pinned Agents</div>
                <div className="text-xs text-shell-muted">The agents worth returning to</div>
              </div>
              <button type="button" className="text-sm text-shell-muted transition hover:text-shell-text">+</button>
            </div>
            <div className="space-y-2.5">
              {PINNED_AGENTS.map((agent) => (
                <button
                  key={agent.title}
                  type="button"
                  onClick={() => setCurrentSection('agents')}
                  className="flex w-full items-center gap-3 rounded-[22px] border border-shell-border bg-shell-panel-strong px-3 py-3 text-left transition hover:border-shell-border-strong hover:bg-shell-panel"
                >
                  <div className={`flex h-10 w-10 items-center justify-center rounded-2xl ${agent.accent}`}>
                    <Bot className="h-4 w-4" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-sm font-semibold text-shell-text">{agent.title}</div>
                    <div className="truncate text-xs text-shell-muted">{agent.subtitle}</div>
                  </div>
                  <ArrowRight className="h-4 w-4 text-shell-muted" />
                </button>
              ))}
            </div>
          </div>

          <div className="rounded-[30px] border border-shell-border bg-shell-panel px-5 py-5 shadow-shell">
            <h3 className="text-lg font-semibold text-shell-text">Quick Starts</h3>
            <div className="mt-3 space-y-2">
              {QUICK_STARTS.map((item) => (
                <button
                  key={item}
                  type="button"
                  onClick={() => setCurrentSection('agents')}
                  className="flex w-full items-center justify-between rounded-[22px] border border-shell-border bg-shell-panel-strong px-4 py-3 text-left text-sm text-shell-text transition hover:border-shell-border-strong hover:bg-shell-panel"
                >
                  <span>{item}</span>
                  <ArrowRight className="h-4 w-4 text-shell-muted" />
                </button>
              ))}
            </div>
          </div>

          <div className="rounded-[30px] border border-shell-border bg-shell-panel px-5 py-5 shadow-shell">
            <h3 className="text-lg font-semibold text-shell-text">System Health</h3>
            <div className="mt-3 rounded-[22px] border border-shell-border bg-shell-panel-strong p-4">
              <div className="flex items-center gap-2 text-sm font-medium text-shell-text">
                <span
                  className={`h-2.5 w-2.5 rounded-full ${
                    wsStatus === 'connected'
                      ? 'bg-shell-success'
                      : wsStatus === 'connecting'
                        ? 'bg-shell-accent'
                        : 'bg-shell-error'
                  }`}
                />
                {wsStatus === 'connected' ? 'Gateway online' : wsStatus === 'connecting' ? 'Reconnecting' : 'Disconnected'}
              </div>
              <div className="mt-3 space-y-2 text-sm text-shell-muted">
                <div className="flex items-center justify-between">
                  <span>Connected providers</span>
                  <span>{connectedProviders}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span>Known tools</span>
                  <span>{tools.length}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span>Quick actions</span>
                  <span>{QUICK_ACTIONS.length}</span>
                </div>
              </div>
            </div>
          </div>
          
          <div className="rounded-[30px] border border-shell-border bg-[radial-gradient(circle_at_top_left,rgba(255,255,255,0.08),transparent_40%),var(--color-shell-ink)] px-5 py-5 text-white shadow-shell">
            <div className="flex items-center justify-between">
              <div className="text-xs font-semibold uppercase tracking-[0.22em] text-white/60">Performance</div>
              <Clock3 className="h-4 w-4 text-white/70" />
            </div>
            <div className="mt-5 space-y-3">
              <div className="h-24 rounded-[24px] border border-white/10 bg-white/5 p-4">
                <div className="mt-8 h-0.5 w-full bg-gradient-to-r from-white/20 via-shell-accent to-white/60" />
              </div>
              <div className="text-sm leading-6 text-white/70">
                Enough signal to keep pushing. Enough shape to inspire what the next version should become.
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
