// Trade history — every closed round trip, newest first, from the same ledger the P&L panel reads.
//
// This is where six years of closed names live so the P&L panel can stay about today's account.
// Grouping is by closed position (a symbol can appear many times); each row is one FIFO match of a
// closing fill against an opening lot, which is the smallest unit that has an honest entry, exit,
// and holding period.

import { useMemo, useState } from 'react';

import type { RealizedTrade, TradeLedger } from '../../lib/wsMarketRpc';
import { money, pnlColor } from './AllTimePnl';
import { MM, PanelCard, mono } from './marketUi';

const PAGE = 15;

function tradeDate(iso: string): string {
  const parsed = new Date(iso);
  return Number.isNaN(parsed.getTime()) ? iso.slice(0, 10) : parsed.toLocaleDateString([], { year: '2-digit', month: 'short', day: 'numeric' });
}

function price(value: number): string {
  return `$${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function TradeRow({ trade, onOpen }: { trade: RealizedTrade; onOpen: (symbol: string) => void }) {
  const isOption = trade.instrumentType === 'OPTION';
  return (
    <button
      onClick={() => onOpen(trade.symbol)}
      style={{
        cursor: 'pointer',
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        padding: '8px 0',
        borderTop: `1px solid rgba(254,252,244,.05)`,
        background: 'transparent',
        border: 'none',
        borderTopColor: 'rgba(254,252,244,.05)',
        textAlign: 'left',
        width: '100%',
      }}
    >
      <span style={{ fontFamily: mono, fontSize: 10, color: MM.dimmer, width: 62 }}>{tradeDate(trade.closedAt)}</span>
      <span style={{ fontFamily: mono, fontSize: 12, fontWeight: 600, color: MM.text, width: 58 }}>{trade.symbol}</span>
      <span style={{ flex: 1, minWidth: 0, fontFamily: mono, fontSize: 10, color: MM.dim, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
        {isOption && <span style={{ color: MM.accent }}>opt </span>}
        {trade.direction === 'short' ? 'short ' : ''}
        {trade.quantity.toLocaleString(undefined, { maximumFractionDigits: 4 })} @ {price(trade.entryPrice)} → {price(trade.exitPrice)}
        {trade.holdingDays != null && <span style={{ color: MM.dimmer }}> · {trade.holdingDays}d</span>}
      </span>
      <span style={{ fontFamily: mono, fontSize: 10.5, color: pnlColor(trade.pnl), width: 58, textAlign: 'right' }}>
        {trade.pnlPct == null ? '—' : `${trade.pnlPct > 0 ? '+' : ''}${trade.pnlPct.toFixed(1)}%`}
      </span>
      <span style={{ fontFamily: mono, fontSize: 12, color: pnlColor(trade.pnl), width: 86, textAlign: 'right' }}>{money(trade.pnl)}</span>
    </button>
  );
}

export function TradeHistory({ ledger, loading, onOpen }: { ledger: TradeLedger | null; loading: boolean; onOpen: (symbol: string) => void }) {
  const [query, setQuery] = useState('');
  const [visible, setVisible] = useState(PAGE);
  const [winnersOnly, setWinnersOnly] = useState<'all' | 'winners' | 'losers'>('all');

  const trades = useMemo(() => {
    const needle = query.trim().toUpperCase();
    return (ledger?.trades ?? []).filter((trade) => {
      if (needle && !trade.symbol.includes(needle)) return false;
      if (winnersOnly === 'winners' && trade.pnl <= 0) return false;
      if (winnersOnly === 'losers' && trade.pnl >= 0) return false;
      return true;
    });
  }, [ledger, query, winnersOnly]);

  const shown = trades.slice(0, visible);
  const netShown = trades.reduce((sum, trade) => sum + trade.pnl, 0);

  if (!ledger) {
    return (
      <PanelCard title="Trade history" status="preview" subtitle="every closed round trip from your Webull fill history">
        <div style={{ fontSize: 12, color: MM.dim }}>{loading ? 'Loading…' : 'Sync fills in the All-time P&L panel to populate this.'}</div>
      </PanelCard>
    );
  }

  const filterButton = (value: 'all' | 'winners' | 'losers', label: string) => (
    <button
      key={value}
      onClick={() => {
        setWinnersOnly(value);
        setVisible(PAGE);
      }}
      style={{
        cursor: 'pointer',
        border: `1px solid ${winnersOnly === value ? MM.borderHi : MM.border}`,
        background: winnersOnly === value ? MM.accentSoft : 'transparent',
        color: winnersOnly === value ? MM.accent : MM.muted,
        borderRadius: 7,
        padding: '3px 8px',
        font: '600 8.5px Inter',
        letterSpacing: '.06em',
        textTransform: 'uppercase',
      }}
    >
      {label}
    </button>
  );

  return (
    <PanelCard
      title="Trade history"
      status="live"
      subtitle={`${trades.length} closed round trips · net ${money(netShown)}`}
      right={<div style={{ display: 'flex', gap: 6 }}>{[filterButton('all', 'All'), filterButton('winners', 'Wins'), filterButton('losers', 'Losses')]}</div>}
      style={{ flex: 1 }}
    >
      <input
        value={query}
        onChange={(event) => {
          setQuery(event.target.value);
          setVisible(PAGE);
        }}
        placeholder="Filter by symbol…"
        style={{
          width: '100%',
          background: MM.panelInset,
          border: `1px solid ${MM.border}`,
          borderRadius: 8,
          padding: '6px 9px',
          color: MM.text,
          fontFamily: mono,
          fontSize: 11.5,
          marginBottom: 4,
        }}
      />

      {shown.length === 0 ? (
        <div style={{ fontSize: 11.5, color: MM.dim, fontStyle: 'italic', padding: '10px 0' }}>Nothing matches that filter.</div>
      ) : (
        shown.map((trade) => <TradeRow key={`${trade.contractKey}-${trade.closedAt}-${trade.entryPrice}-${trade.quantity}`} trade={trade} onOpen={onOpen} />)
      )}

      {visible < trades.length && (
        <button
          onClick={() => setVisible((value) => value + PAGE * 2)}
          style={{ marginTop: 10, alignSelf: 'flex-start', cursor: 'pointer', background: 'transparent', border: 'none', padding: 0, color: MM.muted, font: '600 9.5px Inter', letterSpacing: '.1em', textTransform: 'uppercase' }}
        >
          ▾ Show more ({trades.length - visible} left)
        </button>
      )}
    </PanelCard>
  );
}
