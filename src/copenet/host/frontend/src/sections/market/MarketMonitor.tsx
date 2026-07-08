import { useState } from 'react';
import { MM, PanelCard, mono, toneColor } from './marketUi';
import { BriefingHero, MacroBoard, ModelBadge } from './panelsTop';
import { Rrg } from './RrgChart';
import { BriefingReasoning } from './BriefingReasoning';
import { CandleChart } from './CandleChart';
import { AccumulationWatch, Contrarian, Evidence, Portfolio, SoftBottomingWatch, Speculative, TrendWatch, Watchlist } from './panelsLists';
import { useMarketDashboard, useMarketRead, useMarketWatchlist, useTickerDetail, useTickerEvidence, useTickerRead, type MarketWatchlistState } from './useMarketMonitorData';
import { BacktestLab } from './BacktestLab';
import { TickerSearch } from './TickerSearch';
import { useIsMobile } from '../../lib/responsive';
import type { EvidenceItem } from './types';

const ROW = { display: 'flex', gap: 16, flexWrap: 'wrap' as const, alignItems: 'stretch' as const };
const ROTATION_ROW = { ...ROW, alignItems: 'stretch' as const };

const CONFIDENCE_COLORS: Record<string, string> = { low: '#d96d5f', medium: '#a29b90', high: '#69c589' };

function formatSecAsOf(value?: string) {
  if (!value) return '';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString([], { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
}

function SecActivityPanel({
  evidence,
  asOf,
  loading,
  refreshing,
  error,
  onRefresh,
}: {
  evidence: EvidenceItem[];
  asOf?: string;
  loading: boolean;
  refreshing: boolean;
  error: string | null;
  onRefresh: () => void;
}) {
  const typeBg = (t: EvidenceItem['type']) => (t === 'Insider' ? MM.accentSoft : 'rgba(254,252,244,.06)');
  const typeColor = (t: EvidenceItem['type']) => (t === 'Insider' ? MM.accent : MM.textSoft);
  return (
    <PanelCard
      title="SEC Activity"
      status={loading ? 'preview' : error ? 'error' : 'live'}
      style={{ flex: 1.25, minWidth: 320 }}
      right={
        <button
          onClick={onRefresh}
          disabled={refreshing}
          style={{ cursor: refreshing ? 'default' : 'pointer', border: `1px solid rgba(251,148,35,.3)`, background: refreshing ? 'rgba(251,148,35,.07)' : 'transparent', color: MM.accent, borderRadius: 8, padding: '5px 10px', font: '600 9px Inter', letterSpacing: '.08em', textTransform: 'uppercase', opacity: refreshing ? 0.65 : 1 }}
        >
          {refreshing ? 'Checking…' : 'Check SEC now'}
        </button>
      }
      subtitle={asOf ? `cached as of ${formatSecAsOf(asOf)}` : 'cached Form 4 and 8-K evidence'}
    >
      {error && <div style={{ fontSize: 11, color: MM.down, marginBottom: 8 }}>{error}</div>}
      {loading ? (
        <div style={{ fontSize: 11.5, color: MM.dim, fontStyle: 'italic' }}>Loading cached SEC evidence…</div>
      ) : evidence.length === 0 ? (
        <div style={{ fontSize: 11.5, color: MM.dim, fontStyle: 'italic' }}>No recent Form 4 or 8-K activity found.</div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', maxHeight: 260, overflowY: 'auto', paddingRight: 4 }}>
          {evidence.map((item, i) => {
            const row = (
              <>
                <span style={{ flex: '0 0 auto', borderRadius: 6, padding: '3px 7px', font: '600 8.5px Inter', letterSpacing: '.08em', textTransform: 'uppercase', background: typeBg(item.type), color: typeColor(item.type) }}>{item.type}</span>
                <span style={{ flex: 1, minWidth: 0, fontSize: 12, color: MM.textSoft, lineHeight: 1.4 }}>{item.headline}</span>
                <span style={{ fontSize: 10, color: MM.dim, whiteSpace: 'nowrap' }}>{item.source}</span>
              </>
            );
            const style = { display: 'flex', alignItems: 'center', gap: 10, padding: '9px 0', borderTop: i ? `1px solid rgba(254,252,244,.05)` : 'none', textAlign: 'left' as const };
            return item.url ? (
              <a key={`${item.type}-${item.t || i}-${item.headline}`} href={item.url} target="_blank" rel="noreferrer" style={{ ...style, textDecoration: 'none' }}>
                {row}
              </a>
            ) : (
              <div key={`${item.type}-${item.t || i}-${item.headline}`} style={style}>
                {row}
              </div>
            );
          })}
        </div>
      )}
    </PanelCard>
  );
}

function TickerReadPanel({ symbol }: { symbol: string }) {
  const { read, running, run } = useTickerRead(symbol);
  return (
    <div style={{ background: `linear-gradient(180deg, rgba(90,143,199,.06), transparent 45%), ${MM.panel}`, border: `1px solid rgba(90,143,199,.22)`, borderRadius: 14, padding: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, marginBottom: read ? 12 : 0, flexWrap: 'wrap' }}>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7, font: '600 9.5px Inter', letterSpacing: '.14em', textTransform: 'uppercase', color: '#8fb8e8' }}>
          ✦ Model read — {symbol}
        </span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {read && <ModelBadge model={read.model} generatedAt={read.generatedAt} />}
          <button
            onClick={() => void run()}
            disabled={running}
            style={{ cursor: running ? 'default' : 'pointer', border: `1px solid rgba(90,143,199,.35)`, background: 'rgba(90,143,199,.1)', color: '#8fb8e8', borderRadius: 9, padding: '7px 13px', font: '600 10px Inter', letterSpacing: '.05em', opacity: running ? 0.6 : 1 }}
          >
            {running ? '◍ Reading the tape…' : read ? '↻ Re-run read' : '✦ Run model read'}
          </button>
        </div>
      </div>
      {!read && !running && (
        <div style={{ fontSize: 11.5, color: MM.dim, fontStyle: 'italic', marginTop: 8 }}>
          Sends this asset's computed fact packet to GPT-5.5 for a deeper interpretation — bull case, bear case, and what would change its mind.
        </div>
      )}
      {running && !read && (
        <div style={{ fontSize: 11.5, color: MM.dim, fontStyle: 'italic', marginTop: 8 }}>The model is reading the computed facts — usually 10–30 seconds…</div>
      )}
      {read && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 13 }}>
          <div style={{ fontSize: 13, color: MM.textSoft, lineHeight: 1.6 }}>{read.read}</div>
          <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap' }}>
            <div style={{ flex: 1, minWidth: 240, borderLeft: `2px solid rgba(105,197,137,.4)`, paddingLeft: 11 }}>
              <div style={{ font: '600 9px Inter', letterSpacing: '.1em', textTransform: 'uppercase', color: MM.up, marginBottom: 5 }}>Bull case</div>
              <div style={{ fontSize: 12, color: MM.textSoft, lineHeight: 1.55 }}>{read.bullCase}</div>
            </div>
            <div style={{ flex: 1, minWidth: 240, borderLeft: `2px solid rgba(217,109,95,.4)`, paddingLeft: 11 }}>
              <div style={{ font: '600 9px Inter', letterSpacing: '.1em', textTransform: 'uppercase', color: MM.down, marginBottom: 5 }}>Bear case</div>
              <div style={{ fontSize: 12, color: MM.textSoft, lineHeight: 1.55 }}>{read.bearCase}</div>
            </div>
          </div>
          <div style={{ borderLeft: `2px solid rgba(251,148,35,.35)`, paddingLeft: 11 }}>
            <div style={{ font: '600 9px Inter', letterSpacing: '.1em', textTransform: 'uppercase', color: MM.accent, marginBottom: 5 }}>What would change its mind</div>
            <div style={{ fontSize: 12, color: MM.textSoft, lineHeight: 1.55 }}>{read.whatWouldChangeMyMind}</div>
          </div>
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: 14, flexWrap: 'wrap' }}>
            <span style={{ borderRadius: 999, border: `1px solid ${MM.border}`, padding: '3px 9px', font: '600 9px Inter', letterSpacing: '.1em', textTransform: 'uppercase', color: CONFIDENCE_COLORS[read.confidence] || MM.muted }}>
              confidence: {read.confidence}
            </span>
            <span style={{ fontSize: 11, color: MM.dim, fontStyle: 'italic', flex: 1, minWidth: 200 }}>{read.confidenceReason}</span>
          </div>
          {read.keyFacts.length > 0 && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {read.keyFacts.map((f, i) => (
                <span key={i} style={{ fontFamily: mono, fontSize: 10, color: MM.muted, border: `1px solid ${MM.border}`, borderRadius: 7, padding: '3px 8px' }}>{f}</span>
              ))}
            </div>
          )}
          <div style={{ fontSize: 10, color: MM.dimmer, fontStyle: 'italic' }}>
            Model interpretation of computed facts — an opinion with caveats, not a forecast. Base rates quoted from calibration.
          </div>
        </div>
      )}
    </div>
  );
}

function TickerDetail({ symbol, onClose, watchlist }: { symbol: string; onClose: () => void; watchlist: MarketWatchlistState }) {
  const td = useTickerDetail(symbol);
  const sec = useTickerEvidence(symbol);
  const [tf, setTf] = useState<'D' | 'W' | 'M'>('W');
  const [watchBusy, setWatchBusy] = useState(false);
  const isWatched = watchlist.symbols.has(symbol.toUpperCase());
  const toggleWatch = async () => {
    setWatchBusy(true);
    try {
      if (isWatched) await watchlist.remove(symbol);
      else await watchlist.add(symbol, td.name);
    } finally {
      setWatchBusy(false);
    }
  };
  const series = tf === 'D' ? td.series.daily : tf === 'M' ? td.series.monthly : td.series.weekly;
  const chartEvents = sec.payload ? sec.payload.events : td.events;
  const secEvidence = sec.payload?.evidence ?? [];
  const tfLabel = tf === 'D' ? 'Daily' : tf === 'M' ? 'Monthly' : 'Weekly';
  const tfBtn = (key: 'D' | 'W' | 'M', label: string) => (
    <button
      key={key}
      onClick={() => setTf(key)}
      style={{ cursor: 'pointer', border: 'none', borderRadius: 5, padding: '4px 11px', font: '600 10px Inter', background: tf === key ? MM.accent : 'transparent', color: tf === key ? '#1a1205' : MM.muted }}
    >
      {label}
    </button>
  );
  return (
    <div style={{ padding: 22, display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
        <button onClick={onClose} style={{ cursor: 'pointer', border: `1px solid rgba(254,252,244,.08)`, background: MM.panel, color: MM.muted, borderRadius: 9, padding: '8px 13px', font: '600 11px Inter' }}>← Market Monitor</button>
        <span style={{ fontFamily: mono, fontSize: 26, fontWeight: 600, color: MM.text, letterSpacing: '-.02em' }}>{td.symbol}</span>
        <span style={{ fontFamily: "'Cormorant Garamond', serif", fontSize: 22, color: MM.muted }}>{td.name}</span>
        <button
          onClick={() => void toggleWatch()}
          disabled={watchBusy}
          style={{
            cursor: watchBusy ? 'default' : 'pointer',
            border: `1px solid ${isWatched ? MM.borderHi : MM.border}`,
            background: isWatched ? MM.accentSoft : 'transparent',
            color: isWatched ? MM.accent : MM.muted,
            borderRadius: 9,
            padding: '6px 12px',
            font: '600 10.5px Inter',
            letterSpacing: '.03em',
            opacity: watchBusy ? 0.6 : 1,
          }}
        >
          {watchBusy ? '◍' : isWatched ? '✓ Watching' : '+ Watchlist'}
        </button>
        <div style={{ flex: 1 }} />
        <span style={{ fontFamily: mono, fontSize: 22, color: MM.text }}>{td.last}</span>
        <span style={{ fontFamily: mono, fontSize: 14, color: toneColor(td.tone) }}>{td.change}</span>
      </div>
      <PanelCard
        title={`Price · ${tfLabel}`}
        status={series.length ? 'live' : 'preview'}
        right={
          <div style={{ display: 'flex', gap: 3, background: '#050506', border: `1px solid ${MM.border}`, borderRadius: 8, padding: 3 }}>
            {tfBtn('D', '1D')}
            {tfBtn('W', '1W')}
            {tfBtn('M', '1M')}
          </div>
        }
      >
        <CandleChart bars={series} events={chartEvents} height={620} />
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: 8, borderTop: `1px solid rgba(254,252,244,.05)`, paddingTop: 8 }}>
          <span style={{ fontSize: 10, color: MM.dimmer, display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ width: 13, height: 13, borderRadius: 3, background: '#2a2f3a', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: 8, color: '#7d8aa0' }}>TV</span>
            Charts by TradingView · ▲/▼ insider Form 4 buys/sells · ▪ 8-K filings
          </span>
          <span style={{ fontSize: 10, color: MM.dim, fontStyle: 'italic' }}>~5y history · weekly primary, daily confirmation</span>
        </div>
      </PanelCard>
      <div style={ROW}>
        {td.insight?.softBottoming && (
          <div style={{ flex: 1, minWidth: 260, background: `linear-gradient(180deg, rgba(105,197,137,.07), transparent 52%), ${MM.panel}`, border: `1px solid rgba(105,197,137,.25)`, borderRadius: 14, padding: 16 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 9 }}>
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7, font: '600 9.5px Inter', letterSpacing: '.14em', textTransform: 'uppercase', color: MM.up }}>
                <span style={{ width: 7, height: 7, borderRadius: '50%', background: MM.up }} /> Soft Bottoming
              </span>
              <span style={{ fontFamily: mono, fontSize: 12, color: MM.up }}>score {td.insight.score.toFixed(2)}</span>
            </div>
            {td.insight.baseRate ? (
              <div style={{ fontSize: 12.5, color: MM.textSoft, lineHeight: 1.5, marginBottom: 12 }}>
                {td.insight.baseRate.headline}.
                <span style={{ color: MM.dim }}> Calibrated on real history — a base rate, not a forecast.</span>
              </div>
            ) : (
              <div style={{ fontSize: 11.5, color: MM.dim, fontStyle: 'italic', marginBottom: 12 }}>Base rate calibrating…</div>
            )}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '5px 12px' }}>
              {td.insight.components.map((c, i) => (
                <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, color: c.met ? MM.textSoft : MM.dim }}>
                  <span style={{ color: c.met ? MM.up : MM.dimmer, fontFamily: mono }}>{c.met ? '✓' : '·'}</span>
                  {c.label}
                </div>
              ))}
            </div>
          </div>
        )}
        <SecActivityPanel
          evidence={secEvidence}
          asOf={sec.payload?.asOf}
          loading={sec.loading}
          refreshing={sec.refreshing}
          error={sec.error}
          onRefresh={() => void sec.refresh()}
        />
        <PanelCard title="Signal Readout" status="preview" style={{ flex: 1, minWidth: 260 }}>
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            {td.signals.map((s, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '7px 0', borderTop: i ? `1px solid rgba(254,252,244,.05)` : 'none' }}>
                <span style={{ fontSize: 11.5, color: MM.muted }}>{s.key}</span>
                <span style={{ fontFamily: mono, fontSize: 11.5, color: toneColor(s.tone) }}>{s.value}</span>
              </div>
            ))}
          </div>
        </PanelCard>
        <div style={{ flex: 1, minWidth: 260, background: `linear-gradient(180deg, rgba(251,148,35,.05), transparent 50%), ${MM.panel}`, border: `1px solid rgba(251,148,35,.16)`, borderRadius: 14, padding: 16 }}>
          <div style={{ font: '600 9.5px Inter', letterSpacing: '.14em', textTransform: 'uppercase', color: MM.accent, marginBottom: 9 }}>◆ What would make this wrong</div>
          <div style={{ fontSize: 12, color: MM.textSoft, lineHeight: 1.55 }}>{td.kill}</div>
        </div>
      </div>
      <TickerReadPanel symbol={symbol} />
    </div>
  );
}

export function MarketMonitor() {
  const { dashboard: dash, refreshing, live, refresh, reload } = useMarketDashboard();
  const { read: marketRead, running: reading, run: runRead } = useMarketRead();
  const watchlist = useMarketWatchlist();
  const isMobile = useIsMobile();
  const [activeTicker, setActiveTicker] = useState<string | null>(null);
  const [reasoningOpen, setReasoningOpen] = useState(false);
  const [webullSyncing, setWebullSyncing] = useState(false);
  const [activeTab, setActiveTab] = useState<'monitor' | 'backtest'>('monitor');

  const syncWebull = async () => {
    setWebullSyncing(true);
    try {
      const { wsClient } = await import('../../lib/wsClient');
      await wsClient.marketWebullSync();
      for (let i = 0; i < 8; i += 1) {
        await new Promise((resolve) => setTimeout(resolve, 5000));
        await reload();
      }
    } catch {
    } finally {
      setWebullSyncing(false);
    }
  };

  if (activeTicker) {
    return (
      <div style={{ background: MM.bg, minHeight: '100%', color: MM.text }}>
        <TickerDetail symbol={activeTicker} onClose={() => setActiveTicker(null)} watchlist={watchlist} />
      </div>
    );
  }

  const open = (s: string) => setActiveTicker(s);

  return (
    <div style={{ background: MM.bg, minHeight: '100%', color: MM.text }}>
      <div style={{ padding: 22, display: 'flex', flexDirection: 'column', gap: 16, maxWidth: 1640, margin: '0 auto' }}>
        <div style={{ display: 'flex', flexDirection: isMobile ? 'column' : 'row', alignItems: isMobile ? 'stretch' : 'center', justifyContent: 'space-between', gap: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7, font: '600 9.5px Inter', letterSpacing: '.14em', textTransform: 'uppercase', color: MM.muted, whiteSpace: 'nowrap' }}>
              <span style={{ width: 6, height: 6, borderRadius: '50%', background: live ? MM.up : MM.dim, flex: '0 0 auto' }} />
              {live ? 'Live data' : 'Illustrative preview'} · {dash.asOf}
            </span>
            <div style={{ display: 'flex', gap: 4, background: '#050506', border: `1px solid ${MM.border}`, borderRadius: 8, padding: 3 }}>
              <button
                onClick={() => setActiveTab('monitor')}
                style={{
                  cursor: 'pointer',
                  border: 'none',
                  borderRadius: 5,
                  padding: '4px 11px',
                  font: '600 10.5px Inter',
                  background: activeTab === 'monitor' ? MM.accent : 'transparent',
                  color: activeTab === 'monitor' ? '#1a1205' : MM.muted,
                }}
              >
                Monitor
              </button>
              <button
                onClick={() => setActiveTab('backtest')}
                style={{
                  cursor: 'pointer',
                  border: 'none',
                  borderRadius: 5,
                  padding: '4px 11px',
                  font: '600 10.5px Inter',
                  background: activeTab === 'backtest' ? MM.accent : 'transparent',
                  color: activeTab === 'backtest' ? '#1a1205' : MM.muted,
                }}
              >
                Backtest Lab
              </button>
            </div>
          </div>
          {activeTab === 'monitor' && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
              <button
                onClick={() => void runRead()}
                disabled={reading}
                style={{
                  cursor: reading ? 'default' : 'pointer',
                  border: `1px solid rgba(90,143,199,.35)`,
                  background: 'rgba(90,143,199,.1)',
                  color: '#8fb8e8',
                  borderRadius: 9,
                  padding: '7px 13px',
                  font: '600 10px Inter',
                  letterSpacing: '.05em',
                  opacity: reading ? 0.6 : 1,
                }}
              >
                {reading ? '◍ Reading the tape…' : '✦ Model read'}
              </button>
              <button
                onClick={() => void refresh()}
                disabled={refreshing}
                style={{
                  cursor: refreshing ? 'default' : 'pointer',
                  border: `1px solid ${MM.borderHi}`,
                  background: MM.accentSoft,
                  color: MM.accent,
                  borderRadius: 9,
                  padding: '7px 13px',
                  font: '600 10px Inter',
                  letterSpacing: '.05em',
                  opacity: refreshing ? 0.6 : 1,
                }}
              >
                {refreshing ? '◍ Refreshing…' : '↻ Refresh data'}
              </button>
              <TickerSearch onSelect={(s) => open(s)} fullWidth={isMobile} />
            </div>
          )}
        </div>

        {activeTab === 'backtest' ? (
          <BacktestLab />
        ) : (
          <>
            <Watchlist items={watchlist.items} loading={watchlist.loading} onOpen={open} onRemove={(s) => void watchlist.remove(s)} />
            <BriefingHero panel={dash.briefing} onOpen={open} onExplain={() => setReasoningOpen(true)} read={marketRead} />
            <MacroBoard panel={dash.macro} />
            {dash.softBottoming && <SoftBottomingWatch panel={dash.softBottoming} onOpen={open} />}
            <div style={ROTATION_ROW}>
              <Rrg panel={dash.rrg} onOpen={open} note={marketRead?.rotationRead} />
              <div style={{ flex: 1, minWidth: 320, display: 'flex', flexDirection: 'column', gap: 16 }}>
                <AccumulationWatch panel={dash.accumulation} onOpen={open} />
                <TrendWatch panel={dash.trend} onOpen={open} />
              </div>
            </div>
            <div style={ROW}>
              <Portfolio panel={dash.portfolio} onOpen={open} onSyncWebull={() => void syncWebull()} syncing={webullSyncing} />
              <Speculative panel={dash.speculative} onOpen={open} comment={marketRead?.speculativeComment} />
            </div>
            <div style={ROW}>
              <Evidence panel={dash.evidence} onOpen={open} />
              <Contrarian
                panel={
                  marketRead && marketRead.thesisKillers.length
                    ? { status: 'live', data: marketRead.thesisKillers, note: 'model read' }
                    : dash.contrarian
                }
              />
            </div>
          </>
        )}
        <div style={{ textAlign: 'center', fontSize: 10.5, color: MM.dimmer, padding: '6px 0 14px' }}>
          Reads are evidence-based with caveats — never forecasts. Panels marked “preview” are illustrative until their live data loads.
        </div>
      </div>
      {reasoningOpen && <BriefingReasoning dash={dash} read={marketRead} onClose={() => setReasoningOpen(false)} />}
    </div>
  );
}
