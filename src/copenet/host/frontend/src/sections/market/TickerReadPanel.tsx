import { MM, ModelBadge, mono } from './marketUi';
import { useTickerRead } from './useMarketMonitorData';

const CONFIDENCE_COLORS: Record<string, string> = {
  low: '#d96d5f',
  medium: '#a29b90',
  high: '#69c589',
};

export function TickerReadPanel({ symbol }: { symbol: string }) {
  const { read, running, error, run } = useTickerRead(symbol);

  return (
    <section className="ticker-synthesis-panel is-embedded" aria-labelledby="ticker-model-read" style={{ background: 'transparent', border: 'none', borderRadius: 0, padding: 14 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, marginBottom: read ? 12 : 0, flexWrap: 'wrap' }}>
        <span id="ticker-model-read" style={{ display: 'inline-flex', alignItems: 'center', gap: 7, font: '600 9.5px Inter', letterSpacing: '.14em', textTransform: 'uppercase', color: '#8fb8e8' }}>
          ✦ Model synthesis
        </span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {read && <ModelBadge model={read.model} generatedAt={read.generatedAt} />}
          <button type="button" onClick={() => void run()} disabled={running} style={{ cursor: running ? 'default' : 'pointer', border: `1px solid rgba(90,143,199,.35)`, background: 'rgba(90,143,199,.1)', color: '#8fb8e8', borderRadius: 9, padding: '7px 13px', font: '600 10px Inter', letterSpacing: '.05em', opacity: running ? 0.6 : 1 }}>
            {running ? 'Reading evidence…' : read ? 'Re-run read' : 'Run model read'}
          </button>
        </div>
      </div>

      {error && <p role="alert" style={{ margin: '8px 0 0', color: MM.down, fontSize: 11.5 }}>{error}</p>}

      {!read && (
        <p style={{ fontSize: 11.5, color: MM.dim, fontStyle: 'italic', margin: '8px 0 0' }}>
          {running
            ? 'Building an interpretation from the current fact packet…'
            : `Default read · weekly / positional · VOO benchmark. Interpret ${symbol}'s price structure, deterministic signals, point-in-time fundamentals, SEC evidence, and recent context. Ad hoc chart zoom and overlay state are not included.`}
        </p>
      )}

      {read && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 13 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            {read.lean && (
              <span style={{ borderRadius: 999, border: `1px solid ${MM.border}`, padding: '3px 10px', font: '600 9px Inter', letterSpacing: '.1em', textTransform: 'uppercase', color: read.lean === 'bullish' ? MM.up : read.lean === 'bearish' ? MM.down : MM.muted }}>
                {read.lean} lean
              </span>
            )}
            <span style={{ borderRadius: 999, border: `1px solid ${MM.border}`, padding: '3px 9px', font: '600 9px Inter', letterSpacing: '.1em', textTransform: 'uppercase', color: CONFIDENCE_COLORS[read.confidence] || MM.muted }}>
              {read.confidence} confidence
            </span>
            <span style={{ flex: 1, minWidth: 220, fontSize: 10.5, color: MM.dim }}>{read.confidenceReason}</span>
          </div>
          <p style={{ margin: 0, fontSize: 13, color: MM.textSoft, lineHeight: 1.6 }}>{read.read}</p>
          <div className="market-read-cases">
            <ReadCase label="Bull case" color={MM.up} text={read.bullCase} />
            <ReadCase label="Bear case" color={MM.down} text={read.bearCase} />
          </div>
          <ReadCase label="What would change its mind" color={MM.accent} text={read.whatWouldChangeMyMind} />
          {read.keyFacts.length > 0 && (
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {read.keyFacts.map((fact) => (
                <span key={fact} style={{ fontFamily: mono, fontSize: 10, color: MM.muted, border: `1px solid ${MM.border}`, borderRadius: 7, padding: '3px 8px' }}>{fact}</span>
              ))}
            </div>
          )}
          <span style={{ fontSize: 10, color: MM.dimmer, fontStyle: 'italic' }}>
            Generated from CopeNet's current ticker fact packet. Inspect the deterministic panels above for source and freshness context.
          </span>
        </div>
      )}
    </section>
  );
}

function ReadCase({ label, color, text }: { label: string; color: string; text: string }) {
  return (
    <div style={{ flex: 1, minWidth: 240, borderLeft: `2px solid ${color}66`, paddingLeft: 11 }}>
      <div style={{ font: '600 9px Inter', letterSpacing: '.1em', textTransform: 'uppercase', color, marginBottom: 5 }}>{label}</div>
      <div style={{ fontSize: 12, color: MM.textSoft, lineHeight: 1.55 }}>{text}</div>
    </div>
  );
}
