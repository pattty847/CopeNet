// All-time account P&L — realized round trips replayed FIFO from Webull fill history, plus
// unrealized from the live position snapshot. The caveats are part of the answer, not fine print:
// dividends, fees, and split-driven share changes are invisible to the order feed, so they are
// stated rather than absorbed. See core/market/webull/pnl.py.

import { useCallback, useEffect, useState } from 'react';

import { wsClient } from '../../lib/wsClient';
import type { SymbolPnl, TradeLedger } from '../../lib/wsMarketRpc';
import { MM, PanelCard, mono } from './marketUi';
import { PnlCurve } from './PnlCurve';

function money(value: number | undefined | null, { sign = true }: { sign?: boolean } = {}): string {
  if (value == null) return '—';
  const formatted = Math.abs(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const prefix = !sign ? '' : value < 0 ? '−' : '+';
  return `${prefix}$${formatted}`;
}

function pnlColor(value: number | undefined | null): string {
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
    <div style={{ minWidth: 120 }}>
      <div style={{ font: '600 8.5px Inter', letterSpacing: '.12em', textTransform: 'uppercase', color: MM.dimmer, marginBottom: 4 }}>{caption}</div>
      <div style={{ fontFamily: mono, fontSize: 15, color: color ?? MM.text }}>{value}</div>
    </div>
  );
}

function SymbolRow({ row, onOpen }: { row: SymbolPnl; onOpen: (symbol: string) => void }) {
  return (
    <button
      onClick={() => onOpen(row.symbol)}
      style={{
        cursor: 'pointer',
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        padding: '7px 0',
        borderTop: `1px solid rgba(254,252,244,.05)`,
        background: 'transparent',
        border: 'none',
        borderTopColor: 'rgba(254,252,244,.05)',
        textAlign: 'left',
        width: '100%',
      }}
    >
      <span style={{ fontFamily: mono, fontSize: 12.5, fontWeight: 600, color: MM.text, width: 64 }}>{row.symbol}</span>
      <span style={{ flex: 1, fontFamily: mono, fontSize: 10.5, color: MM.dim }}>
        {row.tradeCount ? `${row.winCount}/${row.tradeCount} winners` : 'open position only'}
      </span>
      <span style={{ fontFamily: mono, fontSize: 11.5, color: pnlColor(row.realizedPnl), width: 92, textAlign: 'right' }}>{money(row.realizedPnl)}</span>
      <span style={{ fontFamily: mono, fontSize: 11.5, color: pnlColor(row.unrealizedPnl), width: 92, textAlign: 'right' }}>
        {row.unrealizedPnl == null ? '—' : money(row.unrealizedPnl)}
      </span>
      <span style={{ fontFamily: mono, fontSize: 12.5, color: pnlColor(row.totalPnl), width: 96, textAlign: 'right' }}>{money(row.totalPnl)}</span>
    </button>
  );
}

export function AllTimePnl({ onOpen }: { onOpen: (symbol: string) => void }) {
  const [ledger, setLedger] = useState<TradeLedger | null>(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    let alive = true;
    wsClient
      .marketWebullPnlGet()
      .then((next) => {
        if (alive) setLedger(next);
      })
      .catch(() => {
        /* backend offline — the panel stays in its empty state */
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, []);

  const sync = useCallback(async () => {
    setSyncing(true);
    setError(null);
    try {
      setLedger(await wsClient.marketWebullOrdersSync());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'fill history sync failed');
    } finally {
      setSyncing(false);
    }
  }, []);

  const syncButton = (
    <button
      onClick={() => void sync()}
      disabled={syncing}
      title="Re-pull every fill from Webull back to account open (read-only)"
      style={{
        cursor: syncing ? 'default' : 'pointer',
        border: `1px solid ${MM.border}`,
        background: 'transparent',
        color: MM.muted,
        borderRadius: 8,
        padding: '5px 10px',
        font: '600 9px Inter',
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

  const visible = expanded ? ledger.bySymbol : ledger.bySymbol.slice(0, 8);

  return (
    <PanelCard
      title="All-time P&L"
      status="live"
      subtitle={`${ledger.tradeCount} closed trades from ${ledger.fillCount} fills since ${shortDate(ledger.firstFillAt)}`}
      right={syncButton}
      style={{ flex: 1 }}
    >
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, marginBottom: 14 }}>
        <div style={{ fontFamily: mono, fontSize: 32, color: pnlColor(ledger.allTimePnl) }}>{money(ledger.allTimePnl)}</div>
        <div style={{ fontSize: 11, color: MM.dim, fontStyle: 'italic' }}>since the account opened</div>
      </div>

      {ledger.curve?.length > 1 && <PnlCurve points={ledger.curve} />}

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 20, padding: '14px 0', borderTop: `1px solid ${MM.border}`, borderBottom: `1px solid ${MM.border}` }}>
        <Stat caption="Realized" value={money(ledger.realizedPnl)} color={pnlColor(ledger.realizedPnl)} />
        {!!ledger.expiredOptionPl && (
          <Stat caption="Expired options" value={money(ledger.expiredOptionPl)} color={pnlColor(ledger.expiredOptionPl)} />
        )}
        {!!ledger.unaccountedPositionPl && (
          <Stat caption="Vanished positions" value={money(ledger.unaccountedPositionPl)} color={pnlColor(ledger.unaccountedPositionPl)} />
        )}
        <Stat caption="Unrealized" value={money(ledger.unrealizedPnl)} color={pnlColor(ledger.unrealizedPnl)} />
        <Stat caption="Win rate" value={ledger.winRatePct == null ? '—' : `${ledger.winRatePct}%`} />
        {ledger.bestTrade && <Stat caption="Best trade" value={`${ledger.bestTrade.symbol} ${money(ledger.bestTrade.pnl)}`} color={MM.up} />}
        {ledger.worstTrade && <Stat caption="Worst trade" value={`${ledger.worstTrade.symbol} ${money(ledger.worstTrade.pnl)}`} color={MM.down} />}
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 0 2px', font: '600 8.5px Inter', letterSpacing: '.1em', textTransform: 'uppercase', color: MM.dimmer }}>
        <span style={{ width: 64 }}>Symbol</span>
        <span style={{ flex: 1 }}>Record</span>
        <span style={{ width: 92, textAlign: 'right' }}>Realized</span>
        <span style={{ width: 92, textAlign: 'right' }}>Open</span>
        <span style={{ width: 96, textAlign: 'right' }}>Total</span>
      </div>
      {visible.map((row) => (
        <SymbolRow key={row.symbol} row={row} onOpen={onOpen} />
      ))}
      {ledger.bySymbol.length > 8 && (
        <button
          onClick={() => setExpanded((value) => !value)}
          style={{ marginTop: 10, alignSelf: 'flex-start', cursor: 'pointer', background: 'transparent', border: 'none', color: MM.muted, font: '600 9.5px Inter', letterSpacing: '.1em', textTransform: 'uppercase' }}
        >
          {expanded ? '▴ Show top 8' : `▾ Show all ${ledger.bySymbol.length}`}
        </button>
      )}

      {ledger.reconciliation.length > 0 && (
        <div style={{ marginTop: 14, paddingTop: 12, borderTop: `1px solid ${MM.border}` }}>
          <div style={{ font: '600 8.5px Inter', letterSpacing: '.12em', textTransform: 'uppercase', color: MM.accent, marginBottom: 6 }}>
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

      <div style={{ marginTop: 12, paddingTop: 10, borderTop: `1px solid ${MM.border}`, fontSize: 10.5, color: MM.dimmer, lineHeight: 1.6 }}>
        {ledger.caveats.map((caveat) => (
          <div key={caveat}>· {caveat}</div>
        ))}
      </div>
    </PanelCard>
  );
}
