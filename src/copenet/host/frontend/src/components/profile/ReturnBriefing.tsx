// ReturnBriefing — "I'm back" re-entry surface for the Home page.
//
// Four sections mirror the Jarvis vision:
//   1. What needs your attention now (time-sensitive, ranked)
//   2. What CopeNet did while you were away (with receipts)
//   3. What it's watching (developing, not urgent yet)
//   4. One thing it noticed (personality slot — most Jarvis-like)
//
// Honest about what isn't wired: renders an explicit "not yet wired" note
// when called with dev-mode skeleton data vs real backend payload.
//
// Backend contract: populated by briefing:ready RPC push when the backend ships.
//
// Dev trigger: <ReturnBriefing devMode /> seeds skeleton data so the surface
// can be tested before the backend lands. Clearly labeled. Easily stripped.

import { AlertCircle, ArrowRight, Bell, Eye, Lightbulb, X, Zap } from 'lucide-react';
import { useAppStore } from '../../store/useAppStore';
import { useReturnBriefing } from '../../runtime/adapter';
import type { ReturnBriefingPayload } from '../../runtime/types';

// ---------------------------------------------------------------------------
// Dev-mode skeleton data — clearly labeled, not in operator flow.
// Exported only for the dev trigger in HomePage. Remove export + usage when backend ships.
// ---------------------------------------------------------------------------
export const DEV_SKELETON_FOR_TEST: ReturnBriefingPayload = {
  briefingId: 'dev_skeleton',
  generatedAt: new Date().toISOString(),
  attentionItems: [
    {
      id: 'attn_1',
      title: 'CopeNet Core session has a paused run awaiting approval',
      urgency: 'high',
      source: 'Agents · CopeNet Core',
      detail: 'Tool: send_message · Telegram · @copenet_ops',
    },
    {
      id: 'attn_2',
      title: 'Sentinel Market Flows: 3 new probes ready for review',
      urgency: 'medium',
      source: 'Workflows · Sentinel',
      detail: null,
    },
  ],
  activityItems: [
    {
      id: 'act_1',
      summary: 'Ran research probe on BTC liquidity structure — 14 tools, 2 artifacts produced',
      sessionKey: null,
      toolsUsed: 14,
      at: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(),
    },
    {
      id: 'act_2',
      summary: 'Archived 2 resolved sessions and updated workspace index',
      sessionKey: null,
      toolsUsed: 4,
      at: new Date(Date.now() - 5 * 60 * 60 * 1000).toISOString(),
    },
  ],
  watchItems: [
    {
      id: 'watch_1',
      label: 'BTC options open interest divergence',
      signal: 'Cumulative delta flipping negative while price holds — not actionable yet',
      source: 'Sentinel Market Flows',
    },
    {
      id: 'watch_2',
      label: 'CopeNet build latency spike',
      signal: 'tsc times have increased ~40% over 3 days — monitoring',
      source: 'Observability',
    },
  ],
  noticeText: 'You tend to approve faster when the proposed action includes a rationale. CopeNet is adjusting how it surfaces reasoning in approval requests.',
  noticeSource: 'session_observation',
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function relativeTime(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(ms / 60_000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

const urgencyStyle: Record<string, { bg: string; text: string }> = {
  high:   { bg: 'bg-shell-error/10',   text: 'text-shell-error' },
  medium: { bg: 'bg-shell-accent/10',  text: 'text-shell-accent' },
  low:    { bg: 'bg-shell-panel-strong', text: 'text-shell-muted' },
};

// ---------------------------------------------------------------------------
// Section components
// ---------------------------------------------------------------------------
function SectionHeader({ icon: Icon, label, count }: { icon: typeof Bell; label: string; count?: number }) {
  return (
    <div className="flex items-center gap-2 pb-2">
      <Icon className="h-3.5 w-3.5 text-shell-accent" />
      <div className="text-[10px] font-semibold uppercase tracking-[0.2em] text-shell-accent">{label}</div>
      {count !== undefined && count > 0 && (
        <span className="rounded-full bg-shell-accent-soft px-1.5 py-0.5 text-[9px] font-semibold text-shell-accent">
          {count}
        </span>
      )}
    </div>
  );
}

function AttentionSection({ items }: { items: ReturnBriefingPayload['attentionItems'] }) {
  if (items.length === 0) {
    return (
      <div className="rounded-[12px] border border-dashed border-shell-border bg-shell-bg px-3 py-2.5 text-[12px] text-shell-muted">
        Nothing needs your attention right now.
      </div>
    );
  }
  return (
    <div className="space-y-1.5">
      {items.map((item) => {
        const style = urgencyStyle[item.urgency] ?? urgencyStyle.low;
        return (
          <div
            key={item.id}
            className="flex items-start gap-2.5 rounded-[14px] border border-shell-border bg-shell-panel-strong px-3 py-2.5"
          >
            <AlertCircle className={`mt-0.5 h-3.5 w-3.5 shrink-0 ${style.text}`} />
            <div className="min-w-0 flex-1">
              <div className="text-[13px] font-medium text-shell-text">{item.title}</div>
              {item.detail && (
                <div className="mt-0.5 text-[11px] text-shell-muted">{item.detail}</div>
              )}
              <div className="mt-1 text-[10px] text-shell-muted/70">{item.source}</div>
            </div>
            <span className={`shrink-0 rounded-full px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-[0.12em] ${style.bg} ${style.text}`}>
              {item.urgency}
            </span>
          </div>
        );
      })}
    </div>
  );
}

function ActivitySection({ items }: { items: ReturnBriefingPayload['activityItems'] }) {
  if (items.length === 0) {
    return (
      <div className="rounded-[12px] border border-dashed border-shell-border bg-shell-bg px-3 py-2.5 text-[12px] text-shell-muted">
        No recorded activity while you were away.
      </div>
    );
  }
  return (
    <div className="space-y-1.5">
      {items.map((item) => (
        <div
          key={item.id}
          className="flex items-start gap-2.5 rounded-[14px] border border-shell-border bg-shell-panel-strong px-3 py-2.5"
        >
          <Zap className="mt-0.5 h-3 w-3 shrink-0 text-shell-accent/60" />
          <div className="min-w-0 flex-1">
            <div className="text-[12px] text-shell-text">{item.summary}</div>
            <div className="mt-0.5 flex items-center gap-2 text-[10px] text-shell-muted/70">
              <span>{relativeTime(item.at)}</span>
              {item.toolsUsed !== undefined && (
                <>
                  <span>·</span>
                  <span>{item.toolsUsed} tools</span>
                </>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function WatchSection({ items }: { items: ReturnBriefingPayload['watchItems'] }) {
  if (items.length === 0) {
    return (
      <div className="rounded-[12px] border border-dashed border-shell-border bg-shell-bg px-3 py-2.5 text-[12px] text-shell-muted">
        Nothing developing right now.
      </div>
    );
  }
  return (
    <div className="space-y-1.5">
      {items.map((item) => (
        <div
          key={item.id}
          className="flex items-start gap-2.5 rounded-[14px] border border-shell-border bg-shell-panel-strong px-3 py-2.5"
        >
          <Eye className="mt-0.5 h-3 w-3 shrink-0 text-shell-muted/60" />
          <div className="min-w-0 flex-1">
            <div className="text-[12px] font-medium text-shell-text">{item.label}</div>
            <div className="mt-0.5 text-[11px] leading-snug text-shell-muted">{item.signal}</div>
            {item.source && (
              <div className="mt-0.5 text-[10px] text-shell-muted/60">{item.source}</div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

function NoticeSection({ text, source }: { text: string | null; source?: string | null }) {
  if (!text) {
    return (
      <div className="rounded-[12px] border border-dashed border-shell-border bg-shell-bg px-3 py-2.5 text-[12px] text-shell-muted">
        Nothing particular to surface right now.
      </div>
    );
  }
  return (
    <div className="rounded-[16px] border border-shell-accent/20 bg-shell-accent-soft px-4 py-3">
      <div className="text-[13px] leading-6 text-shell-text">"{text}"</div>
      {source && (
        <div className="mt-1.5 text-[10px] text-shell-muted/70">
          Source: {source === 'session_observation' ? 'Session observation' : source}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------
interface ReturnBriefingProps {
  /** DEV MODE ONLY — seeds a skeleton briefing so the surface is testable. Strip when backend lands. */
  devMode?: boolean;
}

export function ReturnBriefing({ devMode = false }: ReturnBriefingProps) {
  const storeData = useReturnBriefing();
  const dismissReturnBriefing = useAppStore((s) => s.dismissReturnBriefing);
  const setReturnBriefing = useAppStore((s) => s.setReturnBriefing);

  // Resolve which data to show
  const data = storeData;

  // Dev mode: if no real data and devMode prop is set, seed skeleton
  const isDevSkeleton = devMode && !storeData;

  if (!data && !isDevSkeleton) return null;

  const briefing: ReturnBriefingPayload = data ?? DEV_SKELETON_FOR_TEST;

  const handleDismiss = () => {
    if (isDevSkeleton) {
      // Seed the store so the dismiss works consistently
      setReturnBriefing(DEV_SKELETON_FOR_TEST);
    }
    dismissReturnBriefing();
  };

  return (
    <div className="animate-fade-in-up rounded-[24px] border border-shell-accent/25 bg-shell-panel px-4 py-5 shadow-shell sm:px-6">
      {/* Header */}
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          {isDevSkeleton && (
            <div className="mb-1.5 inline-flex items-center gap-1.5 rounded-full border border-shell-accent/20 bg-shell-accent-soft px-2.5 py-0.5 text-[9px] font-semibold uppercase tracking-[0.18em] text-shell-accent">
              Dev Mode · Skeleton Data
            </div>
          )}
          <h2 className="font-display text-xl tracking-tight text-shell-text">
            You're back.
          </h2>
          <p className="mt-0.5 text-[12px] text-shell-muted">
            Here's what CopeNet has for you.
          </p>
        </div>
        <button
          type="button"
          onClick={handleDismiss}
          className="flex h-7 w-7 items-center justify-center rounded-lg border border-shell-border text-shell-muted transition-colors duration-150 hover:border-shell-accent/30 hover:text-shell-text"
          title="Dismiss briefing"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>

      {/* Four sections in a responsive grid */}
      <div className="grid gap-4 sm:grid-cols-2">
        {/* Section 1: Attention */}
        <div className="space-y-2">
          <SectionHeader
            icon={Bell}
            label="Needs Your Attention"
            count={briefing.attentionItems.length}
          />
          <AttentionSection items={briefing.attentionItems} />
        </div>

        {/* Section 2: Activity */}
        <div className="space-y-2">
          <SectionHeader
            icon={Zap}
            label="While You Were Away"
            count={briefing.activityItems.length}
          />
          <ActivitySection items={briefing.activityItems} />
        </div>

        {/* Section 3: Watching */}
        <div className="space-y-2">
          <SectionHeader
            icon={Eye}
            label="Watching"
            count={briefing.watchItems.length}
          />
          <WatchSection items={briefing.watchItems} />
        </div>

        {/* Section 4: One thing noticed */}
        <div className="space-y-2">
          <SectionHeader icon={Lightbulb} label="One Thing It Noticed" />
          <NoticeSection text={briefing.noticeText} source={briefing.noticeSource} />
        </div>
      </div>

      {/* Footer */}
      <div className="mt-4 flex items-center justify-between border-t border-shell-border pt-3">
        <div className="text-[10px] text-shell-muted/60">
          {isDevSkeleton
            ? 'Dev skeleton · not wired to backend'
            : `Generated ${relativeTime(briefing.generatedAt)}`}
        </div>
        <button
          type="button"
          onClick={handleDismiss}
          className="flex items-center gap-1.5 text-[11px] font-medium text-shell-muted transition-colors duration-150 hover:text-shell-text"
        >
          Dismiss
          <ArrowRight className="h-3 w-3" />
        </button>
      </div>
    </div>
  );
}
