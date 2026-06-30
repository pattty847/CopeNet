import { useState } from 'react';
import { MM, PanelCard, mono, toneColor } from './marketUi';
import { BriefingHero, MacroBoard, Rrg } from './panelsTop';
import { BriefingReasoning } from './BriefingReasoning';
import { CandleChart } from './CandleChart';
import { AccumulationWatch, Contrarian, Evidence, Portfolio, Speculative, TrendWatch } from './panelsLists';
import { useMarketDashboard, useTickerDetail } from './useMarketMonitorData';

const ROW = { display: 'flex', gap: 16, flexWrap: 'wrap' as const, alignItems: 'stretch' as const };

function TickerDetail({ symbol, onClose }: { symbol: string; onClose: () => void }) {
  const td = useTickerDetail(symbol);
  const [tf, setTf] = useState<'D' | 'W' | 'M'>('W');
  const series = tf === 'D' ? td.series.daily : tf === 'M' ? td.series.monthly : td.series.weekly;
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
    <div style={{ padding: 22, maxWidth: 1640, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
        <button onClick={onClose} style={{ cursor: 'pointer', border: `1px solid rgba(254,252,244,.08)`, background: MM.panel, color: MM.muted, borderRadius: 9, padding: '8px 13px', font: '600 11px Inter' }}>← Market Monitor</button>
        <span style={{ fontFamily: mono, fontSize: 26, fontWeight: 600, color: MM.text, letterSpacing: '-.02em' }}>{td.symbol}</span>
        <span style={{ fontFamily: "'Cormorant Garamond', serif", fontSize: 22, color: MM.muted }}>{td.name}</span>
        <div style={{ flex: 1 }} />
        <span style={{ fontFamily: mono, fontSize: 22, color: MM.text }}>{td.last}</span>
        <span style={{ fontFamily: mono, fontSize: 14, color: toneColor(td.tone) }}>{td.change}</span>
      </div>
      <div style={ROW}>
        <PanelCard
          title={`Price · ${tfLabel}`}
          status={series.length ? 'live' : 'preview'}
          style={{ flex: 1.7, minWidth: 420 }}
          right={
            <div style={{ display: 'flex', gap: 3, background: '#050506', border: `1px solid ${MM.border}`, borderRadius: 8, padding: 3 }}>
              {tfBtn('D', '1D')}
              {tfBtn('W', '1W')}
              {tfBtn('M', '1M')}
            </div>
          }
        >
          <CandleChart bars={series} height={400} />
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: 8, borderTop: `1px solid rgba(254,252,244,.05)`, paddingTop: 8 }}>
            <span style={{ fontSize: 10, color: MM.dimmer, display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{ width: 13, height: 13, borderRadius: 3, background: '#2a2f3a', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: 8, color: '#7d8aa0' }}>TV</span>
              Charts by TradingView
            </span>
            <span style={{ fontSize: 10, color: MM.dim, fontStyle: 'italic' }}>~5y history · weekly primary, daily confirmation</span>
          </div>
        </PanelCard>
        <div style={{ flex: 1, minWidth: 320, display: 'flex', flexDirection: 'column', gap: 16 }}>
          <PanelCard title="Signal Readout" status="preview">
            <div style={{ display: 'flex', flexDirection: 'column' }}>
              {td.signals.map((s, i) => (
                <div key={i} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '7px 0', borderTop: i ? `1px solid rgba(254,252,244,.05)` : 'none' }}>
                  <span style={{ fontSize: 11.5, color: MM.muted }}>{s.key}</span>
                  <span style={{ fontFamily: mono, fontSize: 11.5, color: toneColor(s.tone) }}>{s.value}</span>
                </div>
              ))}
            </div>
          </PanelCard>
          <div style={{ background: `linear-gradient(180deg, rgba(251,148,35,.05), transparent 50%), ${MM.panel}`, border: `1px solid rgba(251,148,35,.16)`, borderRadius: 14, padding: 16 }}>
            <div style={{ font: '600 9.5px Inter', letterSpacing: '.14em', textTransform: 'uppercase', color: MM.accent, marginBottom: 9 }}>◆ What would make this wrong</div>
            <div style={{ fontSize: 12, color: MM.textSoft, lineHeight: 1.55 }}>{td.kill}</div>
          </div>
        </div>
      </div>
    </div>
  );
}

export function MarketMonitor() {
  const { dashboard: dash, refreshing, live, refresh } = useMarketDashboard();
  const [activeTicker, setActiveTicker] = useState<string | null>(null);
  const [reasoningOpen, setReasoningOpen] = useState(false);

  if (activeTicker) {
    return (
      <div style={{ background: MM.bg, minHeight: '100%', color: MM.text }}>
        <TickerDetail symbol={activeTicker} onClose={() => setActiveTicker(null)} />
      </div>
    );
  }

  const open = (s: string) => setActiveTicker(s);

  return (
    <div style={{ background: MM.bg, minHeight: '100%', color: MM.text }}>
      <div style={{ padding: 22, display: 'flex', flexDirection: 'column', gap: 16, maxWidth: 1640, margin: '0 auto' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7, font: '600 9.5px Inter', letterSpacing: '.14em', textTransform: 'uppercase', color: MM.muted }}>
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: live ? MM.up : MM.dim }} />
            {live ? 'Live data' : 'Illustrative preview'} · {dash.asOf}
          </span>
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
        </div>
        <BriefingHero panel={dash.briefing} onOpen={open} onExplain={() => setReasoningOpen(true)} />
        <MacroBoard panel={dash.macro} />
        <div style={ROW}>
          <Rrg panel={dash.rrg} onOpen={open} />
          <div style={{ flex: 1, minWidth: 320, display: 'flex', flexDirection: 'column', gap: 16 }}>
            <AccumulationWatch panel={dash.accumulation} onOpen={open} />
            <TrendWatch panel={dash.trend} onOpen={open} />
          </div>
        </div>
        <div style={ROW}>
          <Portfolio panel={dash.portfolio} onOpen={open} />
          <Speculative panel={dash.speculative} onOpen={open} />
        </div>
        <div style={ROW}>
          <Evidence panel={dash.evidence} onOpen={open} />
          <Contrarian panel={dash.contrarian} />
        </div>
        <div style={{ textAlign: 'center', fontSize: 10.5, color: MM.dimmer, padding: '6px 0 14px' }}>
          Reads are evidence-based with caveats — never forecasts. Panels marked “preview” are illustrative until their live data loads.
        </div>
      </div>
      {reasoningOpen && <BriefingReasoning dash={dash} onClose={() => setReasoningOpen(false)} />}
    </div>
  );
}
