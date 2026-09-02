// All-time account P&L — realized round trips replayed FIFO from Webull fill history, plus
// unrealized from the live position snapshot.
//
// The symbol table here lists ONLY what the broker still holds. Six years of closed names belong
// in TradeHistory, not in the panel you open to see how the account stands today. Caveats and
// broker reconciliation sit behind a disclosure for the same reason: they matter, and they are
// still one click away, but they are not the answer. See core/market/webull/pnl.py.

import { useState } from 'react';

import type { SymbolPnl, TradeLedger } from '../../lib/wsMarketRpc';
import { MM, PanelCard, mono } from './marketUi';
import { PnlCurve } from './PnlCurve';

export function money(value: number | undefined | null): string {
  if (value == null) return '—';
  const formatted = Math.abs(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return `${value < 0 ? '−' : '+'}$${formatted}`;
}

export function pnlColor(value: number | undefined | null): string {
  if (value == null || value === 0) return MM.muted;
  return value > 0 ? MM.up : MM.down;
}

function shortDate(iso?: string): string {
  if (!iso) return '—';
  const parsed = new Date(iso);
  return Number.isNaN(parsed.getTime()) ? '—' : parsed.toLocaleDateString([], { year: 'numeric', month: 'short', day: 'numeric' });
}

function Stat({ caption, value, color }: { caption: string; value: string; color?: string }) {
  return (
    <div style={{ minWidth: 108 }}>
      <div style={{ font: '600 8.5px var(--mkt-sans)', letterSpacing: '.12em', textTransform: 'uppercase', color: MM.dimmer, marginBottom: 4 }}>{caption}</div>
      <div style={{ fontFamily: mono, fontSize: 15, color: color ?? MM.text }}>{value}</div>
    </div>
  );
}

function HoldingRow({ row, onOpen }: { row: SymbolPnl; onOpen: (symbol: string) => void }) {
  return (
    <button
      onClick={() => onOpen(row.symbol)}
      style={{
        cursor: 'pointer',
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        padding: '8px 0',
        borderTop: `1px solid rgba(254,252,244,.05)`,
        background: 'transparent',
        border: 'none',
        borderTopColor: 'rgba(254,252,244,.05)',
        textAlign: 'left',
        width: '100%',
      }}
    >
      <span style={{ fontFamily: mono, fontSize: 12.5, fontWeight: 600, color: MM.text, width: 60 }}>{row.symbol}</span>
      <span style={{ flex: 1, fontFamily: mono, fontSize: 10.5, color: MM.dim }}>
        {row.tradeCount ? `${row.winCount}/${row.tradeCount} closed winners` : 'never trimmed'}
      </span>
      <span style={{ fontFamily: mono, fontSize: 11.5, color: pnlColor(row.realizedPnl), width: 88, textAlign: 'right' }}>{money(row.realizedPnl)}</span>
      <span style={{ fontFamily: mono, fontSize: 11.5, color: pnlColor(row.unrealizedPnl), width: 88, textAlign: 'right' }}>{money(row.unrealizedPnl)}</span>
      <span style={{ fontFamily: mono, fontSize: 12.5, color: pnlColor(row.totalPnl), width: 92, textAlign: 'right' }}>{money(row.totalPnl)}</span>
    </button>
  );
}

export function AllTimePnl({
  ledger,
  loading,
  syncing,
  error,
  onSync,
  onOpen,
}: {
  ledger: TradeLedger | null;
  loading: boolean;
  syncing: boolean;
  error: string | null;
  onSync: () => void;
  onOpen: (symbol: string) => void;
}) {
  const [showWorkings, setShowWorkings] = useState(false);

  const syncButton = (
    <button
      onClick={onSync}
      disabled={syncing}
      title="Re-pull every fill from Webull back to account open (read-only)"
      style={{
        cursor: syncing ? 'default' : 'pointer',
        border: `1px solid ${MM.border}`,
        background: 'transparent',
        color: MM.muted,
        borderRadius: 8,
        padding: '5px 10px',
        font: '600 9px var(--mkt-sans)',
        letterSpacing: '.08em',
        textTransform: 'uppercase',
        opacity: syncing ? 0.6 : 1,
      }}
    >
      {syncing ? '◍ Pulling…' : '↻ Fills'}
    </button>
  );

  if (!ledger) {
    return (
      <PanelCard title="All-time P&L" status="preview" subtitle="realized round trips + open positions, replayed from your Webull fill history" right={syncButton}>
        <div style={{ fontSize: 12, color: MM.dim, lineHeight: 1.6 }}>
          {loading ? 'Loading…' : error ?? 'No fill history synced yet — pull it with ↻ Fills to see whether the account is green since it opened.'}
        </div>
      </PanelCard>
    );
  }

  const holdings = ledger.bySymbol.filter((row) => row.openPosition);
  const closed = ledger.bySymbol.filter((row) => !row.openPosition);
  const closedRealized = closed.reduce((sum, row) => sum + row.realizedPnl, 0);
  const workings = ledger.reconciliation.length + ledger.caveats.length;

  return (
    <PanelCard
      title="All-time P&L"
      status="live"
      subtitle={`${ledger.tradeCount} closed trades from ${ledger.fillCount} fills since ${shortDate(ledger.firstFillAt)}`}
      right={syncButton}
      style={{ flex: 1 }}
    >
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, marginBottom: 12, flexWrap: 'wrap' }}>
        <div style={{ fontFamily: mono, fontSize: 32, color: pnlColor(ledger.allTimePnl) }}>{money(ledger.allTimePnl)}</div>
        <div style={{ fontSize: 11, color: MM.dim, fontStyle: 'italic' }}>since the account opened</div>
      </div>

      {ledger.curve?.length > 1 && <PnlCurve points={ledger.curve} />}

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 18, padding: '14px 0', borderTop: `1px solid ${MM.border}`, borderBottom: `1px solid ${MM.border}` }}>
        <Stat caption="Realized" value={money(ledger.realizedPnl)} color={pnlColor(ledger.realizedPnl)} />
        <Stat caption="Unrealized" value={money(ledger.unrealizedPnl)} color={pnlColor(ledger.unrealizedPnl)} />
        {!!ledger.unaccountedPositionPl && (
          <Stat caption="Vanished" value={money(ledger.unaccountedPositionPl)} color={pnlColor(ledger.unaccountedPositionPl)} />
        )}
        <Stat caption="Win rate" value={ledger.winRatePct == null ? '—' : `${ledger.winRatePct}%`} />
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 0 2px', font: '600 8.5px var(--mkt-sans)', letterSpacing: '.1em', textTransform: 'uppercase', color: MM.dimmer }}>
        <span style={{ width: 60 }}>Holding</span>
        <span style={{ flex: 1 }}>Record</span>
        <span style={{ width: 88, textAlign: 'right' }}>Realized</span>
        <span style={{ width: 88, textAlign: 'right' }}>Open</span>
        <span style={{ width: 92, textAlign: 'right' }}>Total</span>
      </div>
      {holdings.length === 0 ? (
        <div style={{ fontSize: 11.5, color: MM.dim, fontStyle: 'italic', padding: '8px 0' }}>No open positions at the broker.</div>
      ) : (
        holdings.map((row) => <HoldingRow key={row.symbol} row={row} onOpen={onOpen} />)
      )}

      <div style={{ marginTop: 12, paddingTop: 10, borderTop: `1px solid ${MM.border}`, fontSize: 11, color: MM.dim }}>
        Closed out: <span style={{ fontFamily: mono, color: MM.textSoft }}>{closed.length}</span> symbols,{' '}
        <span style={{ fontFamily: mono, color: pnlColor(closedRealized) }}>{money(closedRealized)}</span> realized — see Trade history.
      </div>

      {workings > 0 && (
        <>
          <button
            onClick={() => setShowWorkings((value) => !value)}
            style={{ marginTop: 10, alignSelf: 'flex-start', cursor: 'pointer', background: 'transparent', border: 'none', padding: 0, color: MM.muted, font: '600 9px var(--mkt-sans)', letterSpacing: '.1em', textTransform: 'uppercase' }}
          >
            {showWorkings ? '▴ Hide the workings' : `▾ How this was calculated (${workings})`}
          </button>
          {showWorkings && (
            <div style={{ marginTop: 10 }}>
              {ledger.reconciliation.length > 0 && (
                <div style={{ marginBottom: 10 }}>
                  <div style={{ font: '600 8.5px var(--mkt-sans)', letterSpacing: '.12em', textTransform: 'uppercase', color: MM.accent, marginBottom: 6 }}>
                    ◆ Unreconciled with the broker
                  </div>
                  {ledger.reconciliation.map((row) => (
                    <div key={row.symbol} style={{ fontSize: 11, color: MM.textSoft, lineHeight: 1.6 }}>
                      <span style={{ fontFamily: mono, color: MM.text }}>{row.symbol}</span>{' '}
                      <span style={{ color: MM.dim }}>
                        replay {row.replayedQuantity} vs broker {row.brokerQuantity ?? 'none'} — {row.note}
                      </span>
                    </div>
                  ))}
                </div>
              )}
              <div style={{ fontSize: 10.5, color: MM.dimmer, lineHeight: 1.6 }}>
                {ledger.caveats.map((caveat) => (
                  <div key={caveat}>· {caveat}</div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </PanelCard>
  );
}
