import { Activity, Bot, Database, RefreshCcw, SlidersHorizontal, WandSparkles } from 'lucide-react';
import { useMemo, useState } from 'react';
import { useIsMobile } from '../lib/responsive';
import { useAppStore } from '../store/useAppStore';
import { ReturnBriefing, DEV_SKELETON_FOR_TEST } from './profile/ReturnBriefing';
import { useReturnBriefing } from '../runtime/adapter';
import { HomeLayoutCard } from './home/HomeLayoutCard';
import { isHomeCardVisible, renderHomeCard, type HomeCardContext } from './home/HomeCards';
import { cycleHomeCardSize, DEFAULT_HOME_LAYOUT, reorderHomeLayout, type HomeCardId } from './home/homeLayout';

export function HomePage() {
  const themeMode = useAppStore((state) => state.themeMode);
  const sessions = useAppStore((state) => state.sessions);
  const messages = useAppStore((state) => state.messages);
  const providers = useAppStore((state) => state.providers);
  const tools = useAppStore((state) => state.tools);
  const wsStatus = useAppStore((state) => state.wsStatus);
  const pulses = useAppStore((state) => state.pulses);
  const setCurrentSection = useAppStore((state) => state.setCurrentSection);
  const setWorkflowsRoute = useAppStore((state) => state.setWorkflowsRoute);
  const setReturnBriefing = useAppStore((state) => state.setReturnBriefing);
  const homeLayout = useAppStore((state) => state.homeLayout);
  const setHomeLayout = useAppStore((state) => state.setHomeLayout);
  const resetHomeLayout = useAppStore((state) => state.resetHomeLayout);
  const isMobile = useIsMobile();
  const returnBriefing = useReturnBriefing();
  const [showChangelog, setShowChangelog] = useState(false);
  const [customizing, setCustomizing] = useState(false);
  const [draggingId, setDraggingId] = useState<HomeCardId | null>(null);
  const [dropTargetId, setDropTargetId] = useState<HomeCardId | null>(null);
  const resolvedThemeMode = typeof window === 'undefined' ? useAppStore.getState().themeMode : themeMode;
  const isDark = resolvedThemeMode === 'dark';

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

  const cardContext: HomeCardContext = {
    isMobile,
    isDark,
    activeSessions,
    connectedProviders,
    providerCount: providers.length,
    totalMessages,
    toolCount: tools.length,
    wsStatus,
    latestSessions,
    stats,
    showChangelog,
    setShowChangelog,
    setCurrentSection,
    setWorkflowsRoute,
    pulseCount: pulses.length,
  };

  const visibleLayout = homeLayout.filter((item) => isHomeCardVisible(item.id, cardContext));

  const applyDrop = (targetId: HomeCardId) => {
    if (!draggingId || draggingId === targetId) {
      setDropTargetId(null);
      return;
    }
    setHomeLayout(reorderHomeLayout(homeLayout, draggingId, targetId));
    setDraggingId(null);
    setDropTargetId(null);
  };

  return (
    <div className="animate-fade-in-up space-y-3 px-0.5 sm:px-0">
      {returnBriefing ? (
        <ReturnBriefing />
      ) : null}

      {!returnBriefing && !isMobile && (
        <div className="flex items-center gap-2 rounded-[12px] border border-dashed border-shell-border bg-shell-bg px-3 py-2 text-[11px] text-shell-muted/60">
          <span className="rounded-full border border-shell-border bg-shell-panel px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-[0.14em] text-shell-muted">
            Dev
          </span>
          <span>Return Briefing not yet wired to backend.</span>
          <button
            type="button"
            onClick={() => setReturnBriefing(DEV_SKELETON_FOR_TEST)}
            className="ml-auto rounded-[8px] border border-shell-border bg-shell-panel px-2.5 py-1 text-[10px] font-medium text-shell-text transition-colors duration-150 hover:border-shell-accent/30 hover:text-shell-accent"
          >
            Preview briefing
          </button>
        </div>
      )}

      <div className="flex flex-wrap items-center justify-between gap-2 px-1">
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-[0.22em] text-shell-accent">Home Layout</div>
          <p className="mt-1 text-[12px] text-shell-muted">
            Arrange the cards how you want. We&apos;ll remember it on this browser.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => setCustomizing((value) => !value)}
            className={`inline-flex items-center gap-2 rounded-xl border px-3 py-2 text-[12px] font-medium transition-colors ${customizing ? 'border-shell-accent/35 bg-shell-accent-soft text-shell-accent' : 'border-shell-border bg-shell-panel text-shell-text hover:border-shell-border-strong'}`}
          >
            <SlidersHorizontal className="h-3.5 w-3.5" />
            {customizing ? 'Done customizing' : 'Customize layout'}
          </button>
          <button
            type="button"
            onClick={() => {
              resetHomeLayout();
              setCustomizing(false);
              setDraggingId(null);
              setDropTargetId(null);
            }}
            className="inline-flex items-center gap-2 rounded-xl border border-shell-border bg-shell-panel px-3 py-2 text-[12px] font-medium text-shell-text transition-colors hover:border-shell-border-strong"
          >
            <RefreshCcw className="h-3.5 w-3.5" />
            Reset layout
          </button>
        </div>
      </div>

      {customizing && !isMobile && (
        <div className="rounded-[16px] border border-shell-accent/22 bg-shell-accent-soft px-4 py-3 text-[12px] text-shell-muted">
          Drag cards to reorder them. Drag the corner control to resize width or height. Double back here and hit reset if you want the shipped layout again.
        </div>
      )}

      <section className="grid grid-cols-1 items-start gap-3 lg:grid-cols-12">
        {visibleLayout.map((item) => (
          <HomeLayoutCard
            key={item.id}
            item={item}
            customizing={customizing}
            isMobile={isMobile}
            draggingId={draggingId}
            dropTargetId={dropTargetId}
            onDragStart={(id) => {
              setDraggingId(id);
              setDropTargetId(id);
            }}
            onDragEnd={() => {
              setDraggingId(null);
              setDropTargetId(null);
            }}
            onDropOn={applyDrop}
            onResize={(id, axis, direction) => {
              setHomeLayout(cycleHomeCardSize(homeLayout, id, direction, axis));
            }}
          >
            {renderHomeCard(item.id, cardContext)}
          </HomeLayoutCard>
        ))}
      </section>

      {!isMobile && homeLayout.length !== DEFAULT_HOME_LAYOUT.length && (
        <div className="rounded-[16px] border border-shell-border bg-shell-panel px-4 py-3 text-[12px] text-shell-muted">
          The Home layout registry changed since your last visit. New cards were added safely to the end of your layout.
        </div>
      )}
    </div>
  );
}
