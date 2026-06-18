import { useEffect, useMemo, useState } from 'react';
import { useIsMobile } from '../lib/responsive';
import { useAppStore } from '../store/useAppStore';
import { ReturnBriefing, DEV_SKELETON_FOR_TEST } from './profile/ReturnBriefing';
import { useReturnBriefing } from '../runtime/adapter';
import { renderHomeCard, type HomeCardContext } from './home/HomeCards';
import { ApodCard } from './home/ApodCard';
import { MissionControlPanel } from './home/MissionControlPanel';
import { buildMissionControlItems, type MissionControlItem } from '../lib/missionControl';
import { wsClient } from '../lib/wsClient';
import type { SessionRunRecord } from '../types/backend';

const MISSION_SESSION_LIMIT = 24;

export function HomePage() {
  const themeMode = useAppStore((state) => state.themeMode);
  const sessions = useAppStore((state) => state.sessions);
  const messages = useAppStore((state) => state.messages);
  const providers = useAppStore((state) => state.providers);
  const tools = useAppStore((state) => state.tools);
  const wsStatus = useAppStore((state) => state.wsStatus);
  const pulses = useAppStore((state) => state.pulses);
  const sessionStates = useAppStore((state) => state.sessionStates);
  const upsertSessionState = useAppStore((state) => state.upsertSessionState);
  const pendingApproval = useAppStore((state) => state.pendingApproval);
  const approvalHistory = useAppStore((state) => state.approvalHistory);
  const setCurrentSection = useAppStore((state) => state.setCurrentSection);
  const setActiveSessionKey = useAppStore((state) => state.setActiveSessionKey);
  const setDraftOpen = useAppStore((state) => state.setDraftOpen);
  const setWorkflowsRoute = useAppStore((state) => state.setWorkflowsRoute);
  const setReturnBriefing = useAppStore((state) => state.setReturnBriefing);
  const isMobile = useIsMobile();
  const returnBriefing = useReturnBriefing();
  const [showChangelog, setShowChangelog] = useState(false);
  const [missionRunsBySession, setMissionRunsBySession] = useState<Record<string, SessionRunRecord[]>>({});
  const [missionLoading, setMissionLoading] = useState(false);
  const resolvedThemeMode = typeof window === 'undefined' ? useAppStore.getState().themeMode : themeMode;
  const isDark = resolvedThemeMode === 'dark';

  const totalMessages = useMemo(
    () => Object.values(messages).reduce((count, sessionMessages) => count + sessionMessages.length, 0),
    [messages],
  );
  const activeSessionRecords = useMemo(() => sessions.filter((session) => !session.archived), [sessions]);
  const missionSessionRecords = useMemo(() => activeSessionRecords.slice(0, MISSION_SESSION_LIMIT), [activeSessionRecords]);
  const activeSessions = activeSessionRecords.length;
  const connectedProviders = providers.filter((provider) => provider.available).length;
  const latestSessions = sessions.slice(0, 4);
  const missionSessionSignature = missionSessionRecords.map((session) => `${session.key}:${session.updatedAt || ''}`).join('|');

  useEffect(() => {
    let cancelled = false;
    if (missionSessionRecords.length === 0) {
      setMissionRunsBySession({});
      setMissionLoading(false);
      return;
    }

    setMissionLoading(true);
    void Promise.all(
      missionSessionRecords.map(async (session) => {
        const [runs, state] = await Promise.all([
          wsClient.listSessionRuns(session.key, 8).catch(() => [] as SessionRunRecord[]),
          wsClient.resolveSessionState(session.key).catch(() => null),
        ]);
        return { sessionKey: session.key, runs, state };
      }),
    )
      .then((records) => {
        if (cancelled) return;
        const nextRuns: Record<string, SessionRunRecord[]> = {};
        for (const record of records) {
          nextRuns[record.sessionKey] = record.runs;
          if (record.state) upsertSessionState(record.state);
        }
        setMissionRunsBySession(nextRuns);
      })
      .finally(() => {
        if (!cancelled) setMissionLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [missionSessionRecords, missionSessionSignature, upsertSessionState]);

  const missionApprovals = useMemo(() => {
    const byId = new Map(approvalHistory.map((approval) => [approval.approvalId, approval]));
    if (pendingApproval) byId.set(pendingApproval.approvalId, pendingApproval);
    return [...byId.values()];
  }, [approvalHistory, pendingApproval]);

  const missionItems = useMemo(
    () =>
      buildMissionControlItems({
        sessions,
        sessionStates,
        runsBySession: missionRunsBySession,
        approvals: missionApprovals,
      }),
    [missionApprovals, missionRunsBySession, sessionStates, sessions],
  );

  const openMissionSession = (item: MissionControlItem) => {
    setActiveSessionKey(item.sessionKey);
    setDraftOpen(false);
    setCurrentSection('agents');
  };

  const openMissionRun = (item: MissionControlItem) => {
    setActiveSessionKey(item.sessionKey);
    setDraftOpen(false);
    setCurrentSection('observability');
  };

  const openMissionWorkflow = (item: MissionControlItem) => {
    setActiveSessionKey(item.sessionKey);
    setDraftOpen(false);
    setWorkflowsRoute('hub');
    setCurrentSection('workflows');
  };

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
    showChangelog,
    setShowChangelog,
    setCurrentSection,
    setWorkflowsRoute,
    pulseCount: pulses.length,
  };

  return (
    <div className="animate-fade-in-up space-y-4 px-0.5 sm:px-0">
      {returnBriefing ? (
        <ReturnBriefing />
      ) : (
        !isMobile && (
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
        )
      )}

      {/* 1. Hero — cinematic, greeting + CTAs + workspace signal */}
      <div>{renderHomeCard('hero', cardContext)}</div>

      {/* 2. Operational overview — recent sessions + system health, flush row */}
      <div className="grid grid-cols-1 items-stretch gap-3 lg:grid-cols-12">
        <div className="lg:col-span-8">{renderHomeCard('recent_activity', cardContext)}</div>
        <div className="lg:col-span-4">{renderHomeCard('system_health', cardContext)}</div>
      </div>

      {/* 2b. Ambient orientation — NASA Picture of the Day */}
      <ApodCard isMobile={isMobile} />

      {/* 3. Mission Control — scan what wants attention */}
      <MissionControlPanel
        items={missionItems}
        loading={missionLoading}
        onOpenSession={openMissionSession}
        onOpenObservability={openMissionRun}
        onPromoteWorkflow={openMissionWorkflow}
      />

      {/* 4. Identity & Memory — deepest surface, full width */}
      {!isMobile && <div>{renderHomeCard('memory_profile', cardContext)}</div>}
    </div>
  );
}
