// Home: a single-screen cold-open onto the desk.
//
// The operator lands here dozens of times a day and almost always wants one of four things
// — the market's state, a name on their tape, the run that is blocked, or a new session.
// All four are on this screen without a scroll. Anything that needs a page of its own is a
// click away rather than reproduced here; this surface deliberately owns no analysis.
//
// It reads only stored resources (`useStoredMarketResource` under the sweep hooks) plus the
// watchlist. Landing on Home must never acquire market data — Scans owns acquisition.

import { useEffect, useMemo, useState } from 'react';
import { Activity, ArrowRight, Bot, History, LineChart, Radio, Wrench } from 'lucide-react';
import { useAppStore } from '../../store/useAppStore';
import { wsClient } from '../../lib/wsClient';
import { buildMissionControlItems } from '../../lib/missionControl';
import { formatBreadth, formatVix, regimeLabel } from '../../sections/market/marketBriefModel';
import { toneColor } from '../../sections/market/marketUi';
import { useMarketWatchlist } from '../../sections/market/useMarketMonitorData';
import { useMarketDashboard, useMorningBrief } from '../../sections/market/useMarketSweepData';
import { Sparkline } from '../../sections/market/workspaceViz';
import type { SessionRunRecord } from '../../types/backend';
import {
  buildAttentionRows,
  buildChangeRows,
  buildTapeRows,
  marketClock,
  type AttentionRow,
  type TapeRow,
} from './cockpitModel';
import '../../sections/market/tickerWorkspace.css';
import './homeCockpit.css';

const REGIME_COLORS: Record<string, string> = {
  'risk-off': 'var(--mkt-down)',
  chop: 'var(--mkt-muted)',
  'risk-on': 'var(--mkt-up)',
  'event-risk': 'var(--mkt-accent)',
};

const MISSION_SESSION_LIMIT = 24;

/** The bar clock has to tick or it is a lie the moment the page settles. */
function useMarketClock() {
  const [clock, setClock] = useState(() => marketClock());
  useEffect(() => {
    const timer = window.setInterval(() => setClock(marketClock()), 15_000);
    return () => window.clearInterval(timer);
  }, []);
  return clock;
}

/** Run records for the sessions Mission Control ranks. Home asks once per session list
 *  change, never per render — the same contract the old Home page had. */
function useMissionRuns(sessionKeys: string[], signature: string) {
  const upsertSessionState = useAppStore((state) => state.upsertSessionState);
  const [runsBySession, setRunsBySession] = useState<Record<string, SessionRunRecord[]>>({});

  useEffect(() => {
    let cancelled = false;
    if (sessionKeys.length === 0) {
      setRunsBySession({});
      return;
    }
    void Promise.all(
      sessionKeys.map(async (sessionKey) => {
        const [runs, state] = await Promise.all([
          wsClient.listSessionRuns(sessionKey, 8).catch(() => [] as SessionRunRecord[]),
          wsClient.resolveSessionState(sessionKey).catch(() => null),
        ]);
        return { sessionKey, runs, state };
      }),
    ).then((records) => {
      if (cancelled) return;
      const next: Record<string, SessionRunRecord[]> = {};
      for (const record of records) {
        next[record.sessionKey] = record.runs;
        if (record.state) upsertSessionState(record.state);
      }
      setRunsBySession(next);
    });
    return () => {
      cancelled = true;
    };
    // `signature` is what actually changes when the session list moves; the key array is
    // rebuilt every render and would loop forever as a dependency.
  }, [signature, upsertSessionState]);

  return runsBySession;
}

function TapeList({ rows, onOpen }: { rows: TapeRow[]; onOpen: (symbol: string) => void }) {
  if (rows.length === 0) {
    return <div className="hc-empty">No watchlist yet. Open Market to add names.</div>;
  }
  return (
    <>
      {rows.map((row) => (
        <button key={row.symbol} type="button" className="hc-row" onClick={() => onOpen(row.symbol)} title={row.name}>
          <span className="hc-row__sym" data-held={row.held}>
            {row.symbol}
          </span>
          <span className="hc-row__spark">
            {row.spark.length > 1 && <Sparkline points={row.spark} color={toneColor(row.tone)} height={18} />}
          </span>
          <span className="hc-row__last">{row.value}</span>
          <span className="hc-row__chg" style={{ color: toneColor(row.tone) }}>
            {row.change}
          </span>
        </button>
      ))}
    </>
  );
}

function AttentionList({ rows, onOpen }: { rows: AttentionRow[]; onOpen: (row: AttentionRow) => void }) {
  if (rows.length === 0) {
    return <div className="hc-empty">Nothing is waiting on you.</div>;
  }
  return (
    <>
      {rows.map((row) => (
        <button key={row.id} type="button" className="hc-task" onClick={() => onOpen(row)}>
          <span className="hc-task__dot" data-severity={row.severity} />
          <span className="hc-task__label">{row.label}</span>
          <span className="hc-task__meta">{row.meta}</span>
          <span className="hc-task__detail">{row.detail}</span>
        </button>
      ))}
    </>
  );
}

export function HomeCockpit() {
  const sessions = useAppStore((state) => state.sessions);
  const sessionStates = useAppStore((state) => state.sessionStates);
  const providers = useAppStore((state) => state.providers);
  const tools = useAppStore((state) => state.tools);
  const pulses = useAppStore((state) => state.pulses);
  const wsStatus = useAppStore((state) => state.wsStatus);
  const pendingApprovalsById = useAppStore((state) => state.pendingApprovalsById);
  const approvalHistory = useAppStore((state) => state.approvalHistory);
  const setCurrentSection = useAppStore((state) => state.setCurrentSection);
  const setActiveSessionKey = useAppStore((state) => state.setActiveSessionKey);
  const setDraftOpen = useAppStore((state) => state.setDraftOpen);
  const openMarketTicker = useAppStore((state) => state.openMarketTicker);
  const openMarketSection = useAppStore((state) => state.openMarketSection);

  const clock = useMarketClock();
  const watchlist = useMarketWatchlist();
  const { dashboard } = useMarketDashboard();
  const { brief } = useMorningBrief();

  const activeSessions = useMemo(() => sessions.filter((session) => !session.archived), [sessions]);
  const missionSessions = useMemo(() => activeSessions.slice(0, MISSION_SESSION_LIMIT), [activeSessions]);
  const missionSignature = missionSessions.map((session) => `${session.key}:${session.updatedAt || ''}`).join('|');
  const runsBySession = useMissionRuns(
    useMemo(() => missionSessions.map((session) => session.key), [missionSignature]),
    missionSignature,
  );

  const approvals = useMemo(() => {
    const byId = new Map(approvalHistory.map((approval) => [approval.approvalId, approval]));
    for (const pending of Object.values(pendingApprovalsById)) byId.set(pending.approvalId, pending);
    return [...byId.values()];
  }, [approvalHistory, pendingApprovalsById]);

  const attentionRows = useMemo(
    () => buildAttentionRows(buildMissionControlItems({ sessions, sessionStates, runsBySession, approvals })),
    [approvals, runsBySession, sessionStates, sessions],
  );

  const changeRows = useMemo(
    () => buildChangeRows(brief?.newEvidence ?? [], brief?.signalFlips ?? []),
    [brief?.newEvidence, brief?.signalFlips],
  );

  const tapeRows = useMemo(
    () => buildTapeRows(watchlist.items, brief?.movers ?? [], dashboard?.portfolio.data ?? null),
    [brief?.movers, dashboard?.portfolio.data, watchlist.items],
  );

  // Same source the market bar reads, so the two surfaces can never disagree.
  const regime = dashboard?.regime.data.current ?? '';
  const vix = dashboard?.briefing.data.vix ?? null;
  const breadthPct = dashboard?.briefing.data.breadthPct ?? null;

  const openSection = (section: 'agents' | 'market' | 'observability' | 'data-tools') => setCurrentSection(section);
  const openAttention = (row: AttentionRow) => {
    setActiveSessionKey(row.sessionKey);
    setDraftOpen(false);
    setCurrentSection(row.destination);
  };
  const startSession = () => {
    setActiveSessionKey(null);
    setDraftOpen(true);
    setCurrentSection('agents');
  };

  const blocking = attentionRows.filter((row) => row.severity === 'blocking').length;
  // Sessions already carrying something the attention queue is showing would read twice.
  const attentionKeys = useMemo(() => new Set(attentionRows.map((row) => row.sessionKey)), [attentionRows]);
  const recentSessions = useMemo(
    () => activeSessions.filter((session) => !attentionKeys.has(session.key)).slice(0, 8),
    [activeSessions, attentionKeys],
  );

  const resumeSession = (sessionKey: string) => {
    setActiveSessionKey(sessionKey);
    setDraftOpen(false);
    setCurrentSection('agents');
  };

  return (
    <div className="hc">
      <header className="hc-bar">
        <div className="hc-bar__identity">
          <h1 className="hc-bar__title">CopeNet</h1>
          <span className="hc-bar__sub">market terminal</span>
        </div>

        <span className="hc-chip" style={{ color: REGIME_COLORS[regime] ?? 'var(--mkt-dim)' }}>
          <span className="hc-chip__dot" />
          {regime ? regimeLabel(regime) : 'NO READ'}
        </span>

        <span className="hc-clock" role="status">
          {clock.label} · {clock.time}
        </span>

        <div className="hc-bar__spacer" />

        <div className="hc-stat" title="CBOE Volatility Index">
          <b>{vix == null ? '—' : formatVix(vix)}</b>
          <span>VIX</span>
        </div>
        <div className="hc-stat" title="Share of tracked names above their weekly trend">
          <b>{breadthPct == null ? '—' : formatBreadth(breadthPct)}</b>
          <span>Breadth</span>
        </div>
      </header>

      <button type="button" className="hc-headline" onClick={() => openSection('market')}>
        <span className="hc-headline__text">
          {brief?.headline ? <em>{brief.headline}</em> : 'No market read yet — run a sweep from the Market workstation.'}
        </span>
        <span className="hc-headline__go">
          Market <ArrowRight size={11} style={{ display: 'inline', verticalAlign: '-1px' }} />
        </span>
      </button>

      <div className="hc-body">
        <section className="hc-col">
          <div className="hc-col__head">
            <LineChart size={11} />
            Your tape
            <span className="hc-col__count">{tapeRows.length || ''}</span>
          </div>
          <div className="hc-col__body hc-col__body--half">
            <TapeList rows={tapeRows} onOpen={openMarketTicker} />
          </div>
          <div className="hc-col__head hc-col__head--stacked">
            <Radio size={11} />
            What changed
            <span className="hc-col__count">{changeRows.length || ''}</span>
          </div>
          <div className="hc-col__body hc-col__body--half">
            {changeRows.length === 0 ? (
              <div className="hc-empty">Nothing new since the last sweep.</div>
            ) : (
              changeRows.map((row) => (
                <button
                  key={row.id}
                  type="button"
                  className="hc-change"
                  onClick={() => openMarketSection(row.view)}
                  title={row.detail}
                >
                  <span className="hc-change__sym" style={{ color: toneColor(row.tone) }}>
                    {row.symbol}
                  </span>
                  <span className="hc-change__kind">{row.kind}</span>
                  <span className="hc-change__detail">{row.detail}</span>
                </button>
              ))
            )}
          </div>
        </section>

        {/* The desk's two questions, stacked in one column: what is blocked, and what was I
            in the middle of. Recent sits below because a blocked run outranks a resume. */}
        <section className="hc-col">
          <div className="hc-col__head">
            <Bot size={11} />
            Wants you
            <span className="hc-col__count">{blocking > 0 ? `${blocking} blocking` : attentionRows.length || ''}</span>
          </div>
          <div className="hc-col__body hc-col__body--half">
            <AttentionList rows={attentionRows} onOpen={openAttention} />
          </div>
          <div className="hc-col__head hc-col__head--stacked">
            <History size={11} />
            Pick back up
          </div>
          <div className="hc-col__body hc-col__body--half">
            {recentSessions.length === 0 ? (
              <div className="hc-empty">No sessions yet.</div>
            ) : (
              recentSessions.map((session) => (
                <button
                  key={session.key}
                  type="button"
                  className="hc-task"
                  onClick={() => resumeSession(session.key)}
                >
                  <span className="hc-task__dot" data-severity="idle" />
                  <span className="hc-task__label">{session.title?.trim() || 'Untitled session'}</span>
                  <span className="hc-task__meta">{session.model || session.provider}</span>
                  <span className="hc-task__detail">{session.provider}</span>
                </button>
              ))
            )}
          </div>
        </section>

        <section className="hc-col hc-col--desk">
          <div className="hc-col__head">
            <Activity size={11} />
            Desk
          </div>
          <div className="hc-col__body">
            <div className="hc-fact">
              <span
                className="hc-fact__dot"
                style={{
                  background:
                    wsStatus === 'connected'
                      ? 'var(--mkt-up)'
                      : wsStatus === 'connecting'
                        ? 'var(--mkt-accent)'
                        : 'var(--mkt-down)',
                }}
              />
              Gateway
              <b>{wsStatus === 'connected' ? 'live' : wsStatus.replace('_', ' ')}</b>
            </div>
            <div className="hc-fact">
              Providers
              <b>
                {providers.filter((provider) => provider.available).length}/{providers.length || 0}
              </b>
            </div>
            <div className="hc-fact">
              Tools
              <b>{tools.length}</b>
            </div>
            <div className="hc-fact">
              Sessions
              <b>{activeSessions.length}</b>
            </div>
            <div className="hc-fact">
              Unread pulses
              <b>{pulses.length}</b>
            </div>
            {dashboard?.evidence.status === 'error' && (
              <div className="hc-fact" style={{ color: 'var(--mkt-down)' }}>
                Evidence feed
                <b style={{ color: 'var(--mkt-down)' }}>error</b>
              </div>
            )}
          </div>
        </section>
      </div>

      <footer className="hc-launch">
        <button type="button" className="hc-launch__btn" data-primary="true" onClick={startSession}>
          <Bot size={12} />
          New session
        </button>
        <button type="button" className="hc-launch__btn" onClick={() => openSection('market')}>
          <LineChart size={12} />
          Market
        </button>
        <button type="button" className="hc-launch__btn" onClick={() => openSection('observability')}>
          <Activity size={12} />
          Run inspector
        </button>
        <button type="button" className="hc-launch__btn" onClick={() => openSection('data-tools')}>
          <Wrench size={12} />
          Data &amp; tools
        </button>
        <div className="hc-launch__spacer" />
        <span className="hc-launch__hint">⌘K to search</span>
      </footer>
    </div>
  );
}
