import { useEffect, useRef, useState } from 'react';
import { createChart, ColorType, AreaSeries, LineSeries, type IChartApi } from 'lightweight-charts';
import { LucideIcon, Play, RefreshCw, Sliders, Calendar, TrendingUp, AlertTriangle, ShieldAlert, Award, ArrowUpRight, ArrowDownRight, History } from 'lucide-react';
import { useAppStore } from '../../store/useAppStore';
import { wsClient } from '../../lib/wsClient';
import { MM, PanelCard, mono } from './marketUi';
import type { BacktestPayload } from '../../lib/wsMarketRpc';

// Ticker lists for tech fallback detection in weights sync
const TECH_SYMBOLS = new Set(['GOOG', 'XLK', 'NVDA', 'TSLA', 'AMZN', 'INTC', 'SOX', 'SMH', 'CRWV']);

// Account-neutral example weights. Real holdings are supplied only by local broker data.
const DEFAULT_WEIGHTS: Record<string, number> = {
  VOO: 20,
  QQQ: 20,
  IWM: 20,
  EFA: 20,
  VWO: 20,
};

interface MetricCardProps {
  label: string;
  value: string | number;
  sub?: string;
  tone?: 'up' | 'down' | 'neutral';
  icon?: LucideIcon;
}

function MetricCard({ label, value, sub, tone = 'neutral', icon: Icon }: MetricCardProps) {
  let valColor: string = MM.text;
  let bgGradient = 'rgba(254,252,244,.01)';
  let borderColor: string = MM.border;

  if (tone === 'up') {
    valColor = MM.up;
    bgGradient = 'linear-gradient(180deg, rgba(105,197,137,.04), transparent)';
    borderColor = 'rgba(105,197,137,.15)';
  } else if (tone === 'down') {
    valColor = MM.down;
    bgGradient = 'linear-gradient(180deg, rgba(217,109,95,.04), transparent)';
    borderColor = 'rgba(217,109,95,.15)';
  }

  return (
    <div
      style={{
        flex: 1,
        minWidth: 150,
        background: bgGradient,
        backgroundColor: MM.panelInset,
        border: `1px solid ${borderColor}`,
        borderRadius: 12,
        padding: '12px 16px',
        display: 'flex',
        flexDirection: 'column',
        gap: 4,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%' }}>
        <span style={{ font: '600 8.5px var(--mkt-sans)', letterSpacing: '.12em', textTransform: 'uppercase', color: MM.muted }}>
          {label}
        </span>
        {Icon && <Icon size={12} style={{ color: tone === 'neutral' ? MM.dim : valColor }} />}
      </div>
      <span style={{ fontSize: 18, fontWeight: 600, color: valColor, fontFamily: mono, letterSpacing: '-0.02em' }}>
        {value}
      </span>
      {sub && <span style={{ fontSize: 10, color: MM.dim }}>{sub}</span>}
    </div>
  );
}

function EquityChart({ portfolio, benchmark, height = 300 }: { portfolio: { date: string; value: number }[]; benchmark: { date: string; value: number }[]; height?: number }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const chart = createChart(el, {
      width: el.clientWidth,
      height,
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: MM.muted,
        fontFamily: mono,
        fontSize: 9.5,
      },
      grid: {
        vertLines: { color: 'rgba(254,252,244,.03)' },
        horzLines: { color: 'rgba(254,252,244,.03)' },
      },
      rightPriceScale: { borderColor: 'rgba(254,252,244,.06)' },
      timeScale: { borderColor: 'rgba(254,252,244,.06)', rightOffset: 4 },
      crosshair: { mode: 0 },
    });

    const pSeries = chart.addSeries(AreaSeries, {
      lineColor: '#8fb8e8',
      topColor: 'rgba(143, 184, 232, 0.22)',
      bottomColor: 'rgba(143, 184, 232, 0.0)',
      lineWidth: 2,
      priceFormat: { type: 'custom', formatter: (v: number) => `$${v.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}` },
    });

    const bSeries = chart.addSeries(LineSeries, {
      color: 'rgba(254, 252, 244, 0.35)',
      lineWidth: 2,
      lineStyle: 2, // dashed
      priceFormat: { type: 'custom', formatter: (v: number) => `$${v.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}` },
    });

    chartRef.current = chart;

    const ro = new ResizeObserver(() => {
      if (containerRef.current) chart.applyOptions({ width: containerRef.current.clientWidth });
    });
    ro.observe(el);

    // Map series data
    if (portfolio.length > 0) {
      pSeries.setData(portfolio.map(p => ({ time: p.date, value: p.value })));
    }
    if (benchmark.length > 0) {
      bSeries.setData(benchmark.map(b => ({ time: b.date, value: b.value })));
    }

    chart.timeScale().fitContent();

    return () => {
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
    };
  }, [portfolio, benchmark, height]);

  return <div ref={containerRef} style={{ width: '100%', position: 'relative' }} />;
}

export function BacktestLab() {
  const activeSessionKey = useAppStore((state) => state.activeSessionKey);
  const [symbolsStr, setSymbolsStr] = useState('VOO, QQQ, IWM, EFA, VWO');
  const [weightsMap, setWeightsMap] = useState<Record<string, number>>(DEFAULT_WEIGHTS);
  const [startDate, setStartDate] = useState('2022-01-01');
  const [endDate, setEndDate] = useState('2022-12-31');
  const [benchmark, setBenchmark] = useState('VOO');
  const [rebalance, setRebalance] = useState<'buy_and_hold' | 'periodic'>('buy_and_hold');
  const [rebalanceInterval, setRebalanceInterval] = useState<'daily' | 'weekly' | 'monthly'>('monthly');

  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<BacktestPayload | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  
  // Historical runs loaded from session artifacts ledger
  const [runsList, setRunsList] = useState<any[]>([]);

  // Derived symbols list
  const symbolsList = symbolsStr
    .split(',')
    .map(s => s.trim().toUpperCase())
    .filter(Boolean);

  // Load previous backtests from session artifacts on mount/session changes
  const loadHistory = async () => {
    if (!activeSessionKey) return;
    try {
      const resp = await wsClient.listSessionArtifacts(activeSessionKey, 15);
      if (resp && Array.isArray(resp)) {
        const filtered = resp.filter(art => art.type === 'backtest');
        setRunsList(filtered);
      }
    } catch {
      // offline or not configured
    }
  };

  useEffect(() => {
    void loadHistory();
  }, [activeSessionKey]);

  // Keep weights synchronized when symbols change
  useEffect(() => {
    setWeightsMap(prev => {
      const next: Record<string, number> = {};
      const remainingWeight = 100;
      const count = symbolsList.length;
      if (count === 0) return next;

      // Equal split or default matching
      symbolsList.forEach(symbol => {
        if (prev[symbol] !== undefined) {
          next[symbol] = prev[symbol];
        } else if (DEFAULT_WEIGHTS[symbol] !== undefined) {
          next[symbol] = DEFAULT_WEIGHTS[symbol];
        } else {
          next[symbol] = Math.round(remainingWeight / count);
        }
      });
      return next;
    });
  }, [symbolsStr]);

  const totalWeight = Object.values(weightsMap).reduce((a, b) => a + b, 0);

  const handleWeightChange = (symbol: string, val: number) => {
    setWeightsMap(prev => ({
      ...prev,
      [symbol]: val,
    }));
  };

  const runBacktest = async () => {
    setLoading(true);
    setErrorMsg(null);
    try {
      const weights = symbolsList.map(s => (weightsMap[s] || 0) / 100);
      const res = await wsClient.marketBacktestRun({
        sessionKey: activeSessionKey || '',
        symbols: symbolsList,
        weights,
        startDate,
        endDate,
        benchmark,
        rebalance,
        rebalanceInterval: rebalance === 'periodic' ? rebalanceInterval : null,
      });
      setResult(res as BacktestPayload);
      void loadHistory(); // refresh history list
    } catch (err: any) {
      setErrorMsg(err.message || 'Backtest execution failed.');
    } finally {
      setLoading(false);
    }
  };

  const runStressTest = async (scenarioKey: string) => {
    setLoading(true);
    setErrorMsg(null);
    try {
      // Fetch current synced positions if available, otherwise backend defaults to basis
      const status = await wsClient.marketWebullStatus();
      let positions: any[] = [];
      
      if (status.positionCount && status.positionCount > 0) {
        // backend Webull client sync is authed, pull snapshot positions
        try {
          const snapshot = await wsClient.marketDashboard();
          if (snapshot.portfolio?.data?.positions) {
            positions = snapshot.portfolio.data.positions;
          }
        } catch {
          // fallback
        }
      }

      const res = await wsClient.marketBacktestStressTest({
        sessionKey: activeSessionKey || '',
        scenarioKey,
        positions,
      });
      setResult(res as BacktestPayload);
      void loadHistory(); // refresh history list
    } catch (err: any) {
      setErrorMsg(err.message || 'Stress test simulation failed.');
    } finally {
      setLoading(false);
    }
  };

  const applyPreset = (preset: '2022_tech_dump' | '2020_covid_crash') => {
    setSymbolsStr('GOOG, XLK, VTI, SOFI, SLI');
    setWeightsMap(DEFAULT_WEIGHTS);
    setBenchmark('VOO');
    if (preset === '2022_tech_dump') {
      setStartDate('2022-01-01');
      setEndDate('2022-12-31');
      setRebalance('buy_and_hold');
      void runStressTest('2022_tech_dump');
    } else {
      setStartDate('2020-02-15');
      setEndDate('2020-04-15');
      setRebalance('buy_and_hold');
      void runStressTest('2020_covid_crash');
    }
  };

  const loadRunFromArtifact = (artifact: any) => {
    if (artifact.metadata) {
      setResult(artifact.metadata as BacktestPayload);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16, maxWidth: 1640, margin: '0 auto' }}>
      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
        {/* Left Side — Controls panel */}
        <div style={{ flex: '1 1 400px', display: 'flex', flexDirection: 'column', gap: 16 }}>
          <PanelCard title="Parameters" status="live">
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              
              {/* Preset Scenarios Block */}
              <div>
                <span style={{ font: '600 8.5px var(--mkt-sans)', letterSpacing: '.12em', textTransform: 'uppercase', color: MM.dim, display: 'block', marginBottom: 6 }}>
                  Macro Scenario Presets
                </span>
                <div style={{ display: 'flex', gap: 8 }}>
                  <button
                    onClick={() => applyPreset('2022_tech_dump')}
                    style={{
                      flex: 1,
                      cursor: 'pointer',
                      border: `1px solid rgba(217,109,95,.22)`,
                      background: 'rgba(217,109,95,.06)',
                      color: MM.down,
                      borderRadius: 8,
                      padding: '8px 12px',
                      font: '600 10.5px var(--mkt-sans)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: 6,
                    }}
                  >
                    <ShieldAlert size={12} />
                    '22 Tech Dump
                  </button>
                  <button
                    onClick={() => applyPreset('2020_covid_crash')}
                    style={{
                      flex: 1,
                      cursor: 'pointer',
                      border: `1px solid rgba(251,148,35,.22)`,
                      background: 'rgba(251,148,35,.06)',
                      color: MM.accent,
                      borderRadius: 8,
                      padding: '8px 12px',
                      font: '600 10.5px var(--mkt-sans)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: 6,
                    }}
                  >
                    <AlertTriangle size={12} />
                    '20 Covid Crash
                  </button>
                </div>
              </div>

              {/* Ticker inputs */}
              <div>
                <label style={{ font: '600 8.5px var(--mkt-sans)', letterSpacing: '.12em', textTransform: 'uppercase', color: MM.muted, display: 'block', marginBottom: 5 }}>
                  Tickers (comma separated)
                </label>
                <input
                  type="text"
                  value={symbolsStr}
                  onChange={(e) => setSymbolsStr(e.target.value)}
                  style={{
                    width: '100%',
                    background: MM.panelInset,
                    border: `1px solid ${MM.border}`,
                    borderRadius: 8,
                    padding: '8px 12px',
                    color: MM.text,
                    fontFamily: mono,
                    fontSize: 12,
                    outline: 'none',
                  }}
                />
              </div>

              {/* Dynamic Weight Sliders */}
              {symbolsList.length > 0 && (
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                    <span style={{ font: '600 8.5px var(--mkt-sans)', letterSpacing: '.12em', textTransform: 'uppercase', color: MM.muted }}>
                      Portfolio Allocation Weights
                    </span>
                    <span style={{ fontFamily: mono, fontSize: 10.5, color: totalWeight === 100 ? MM.up : MM.accent }}>
                      Total: {totalWeight}%
                    </span>
                  </div>
                  <div
                    style={{
                      maxHeight: 180,
                      overflowY: 'auto',
                      border: `1px solid ${MM.border}`,
                      borderRadius: 8,
                      padding: '8px 12px',
                      backgroundColor: MM.panelInset,
                      display: 'flex',
                      flexDirection: 'column',
                      gap: 8,
                    }}
                  >
                    {symbolsList.map((symbol) => (
                      <div key={symbol} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        <span style={{ width: 50, fontFamily: mono, fontSize: 11, fontWeight: 600 }}>{symbol}</span>
                        <input
                          type="range"
                          min="0"
                          max="100"
                          value={weightsMap[symbol] || 0}
                          onChange={(e) => handleWeightChange(symbol, parseInt(e.target.value) || 0)}
                          style={{ flex: 1, accentColor: MM.accent, cursor: 'pointer' }}
                        />
                        <span style={{ width: 35, textAlign: 'right', fontFamily: mono, fontSize: 11, color: MM.muted }}>
                          {weightsMap[symbol] || 0}%
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Date pickers */}
              <div style={{ display: 'flex', gap: 10 }}>
                <div style={{ flex: 1 }}>
                  <label style={{ font: '600 8.5px var(--mkt-sans)', letterSpacing: '.12em', textTransform: 'uppercase', color: MM.muted, display: 'block', marginBottom: 5 }}>
                    Start Date
                  </label>
                  <input
                    type="date"
                    value={startDate}
                    onChange={(e) => setStartDate(e.target.value)}
                    style={{
                      width: '100%',
                      background: MM.panelInset,
                      border: `1px solid ${MM.border}`,
                      borderRadius: 8,
                      padding: '7px 10px',
                      color: MM.text,
                      fontSize: 11.5,
                      outline: 'none',
                    }}
                  />
                </div>
                <div style={{ flex: 1 }}>
                  <label style={{ font: '600 8.5px var(--mkt-sans)', letterSpacing: '.12em', textTransform: 'uppercase', color: MM.muted, display: 'block', marginBottom: 5 }}>
                    End Date
                  </label>
                  <input
                    type="date"
                    value={endDate}
                    onChange={(e) => setEndDate(e.target.value)}
                    style={{
                      width: '100%',
                      background: MM.panelInset,
                      border: `1px solid ${MM.border}`,
                      borderRadius: 8,
                      padding: '7px 10px',
                      color: MM.text,
                      fontSize: 11.5,
                      outline: 'none',
                    }}
                  />
                </div>
              </div>

              {/* Benchmark Input */}
              <div>
                <label style={{ font: '600 8.5px var(--mkt-sans)', letterSpacing: '.12em', textTransform: 'uppercase', color: MM.muted, display: 'block', marginBottom: 5 }}>
                  Benchmark Index
                </label>
                <input
                  type="text"
                  value={benchmark}
                  onChange={(e) => setBenchmark(e.target.value)}
                  style={{
                    width: '100%',
                    background: MM.panelInset,
                    border: `1px solid ${MM.border}`,
                    borderRadius: 8,
                    padding: '8px 12px',
                    color: MM.text,
                    fontFamily: mono,
                    fontSize: 12,
                    outline: 'none',
                  }}
                />
              </div>

              {/* Rebalancing Strategy */}
              <div>
                <label style={{ font: '600 8.5px var(--mkt-sans)', letterSpacing: '.12em', textTransform: 'uppercase', color: MM.muted, display: 'block', marginBottom: 5 }}>
                  Rebalancing Mode
                </label>
                <select
                  value={rebalance}
                  onChange={(e) => setRebalance(e.target.value as 'buy_and_hold' | 'periodic')}
                  style={{
                    width: '100%',
                    background: MM.panelInset,
                    border: `1px solid ${MM.border}`,
                    borderRadius: 8,
                    padding: '8px 12px',
                    color: MM.text,
                    fontSize: 12,
                    outline: 'none',
                  }}
                >
                  <option value="buy_and_hold">Buy & Hold</option>
                  <option value="periodic">Periodic Rebalancing</option>
                </select>
              </div>

              {rebalance === 'periodic' && (
                <div>
                  <label style={{ font: '600 8.5px var(--mkt-sans)', letterSpacing: '.12em', textTransform: 'uppercase', color: MM.muted, display: 'block', marginBottom: 5 }}>
                    Rebalance Interval
                  </label>
                  <select
                    value={rebalanceInterval}
                    onChange={(e) => setRebalanceInterval(e.target.value as 'daily' | 'weekly' | 'monthly')}
                    style={{
                      width: '100%',
                      background: MM.panelInset,
                      border: `1px solid ${MM.border}`,
                      borderRadius: 8,
                      padding: '8px 12px',
                      color: MM.text,
                      fontSize: 12,
                      outline: 'none',
                    }}
                  >
                    <option value="daily">Daily</option>
                    <option value="weekly">Weekly</option>
                    <option value="monthly">Monthly</option>
                  </select>
                </div>
              )}

              {/* Run button */}
              <button
                onClick={runBacktest}
                disabled={loading || totalWeight !== 100}
                style={{
                  cursor: loading || totalWeight !== 100 ? 'default' : 'pointer',
                  border: `1px solid ${MM.borderHi}`,
                  background: MM.accentSoft,
                  color: MM.accent,
                  borderRadius: 9,
                  padding: '10px 16px',
                  font: '600 12px var(--mkt-sans)',
                  letterSpacing: '.05em',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 8,
                  opacity: loading || totalWeight !== 100 ? 0.6 : 1,
                  marginTop: 6,
                }}
              >
                {loading ? <RefreshCw size={14} className="animate-spin" /> : <Play size={14} />}
                {loading ? 'Executing Engine...' : 'Run Historical Backtest'}
              </button>
            </div>
          </PanelCard>

          {/* Historical Runs Ledger list */}
          {runsList.length > 0 && (
            <PanelCard title="Session Runs Ledger" status="live">
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8, maxHeight: 220, overflowY: 'auto' }}>
                {runsList.map((run) => (
                  <button
                    key={run.artifactId}
                    onClick={() => loadRunFromArtifact(run)}
                    style={{
                      cursor: 'pointer',
                      border: `1px solid ${MM.border}`,
                      background: 'rgba(254,252,244,.02)',
                      borderRadius: 8,
                      padding: '8px 12px',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      width: '100%',
                      outline: 'none',
                      textAlign: 'left',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <History size={13} style={{ color: MM.muted }} />
                      <span style={{ fontSize: 11, color: MM.textSoft, fontWeight: 500 }} className="truncate max-w-[190px]">
                        {run.title}
                      </span>
                    </div>
                    <span style={{ font: '600 8px var(--mkt-sans)', color: MM.dim }}>
                      {new Date(run.createdAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </span>
                  </button>
                ))}
              </div>
            </PanelCard>
          )}
        </div>

        {/* Right Side — Results workspace */}
        <div style={{ flex: '2 1 600px', display: 'flex', flexDirection: 'column', gap: 16 }}>
          {errorMsg && (
            <div style={{ background: 'rgba(217,109,95,.08)', border: `1px solid ${MM.down}`, borderRadius: 10, padding: 14, color: MM.down, fontSize: 12 }}>
              {errorMsg}
            </div>
          )}

          {!result && !loading && (
            <div
              style={{
                flex: 1,
                minHeight: 480,
                border: `1px dotted ${MM.border}`,
                borderRadius: 14,
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                color: MM.dim,
                gap: 12,
                padding: 40,
                textAlign: 'center',
              }}
            >
              <Sliders size={48} strokeWidth={1} style={{ color: MM.dimmer }} />
              <div style={{ fontSize: 13, fontWeight: 600, color: MM.muted }}>Laboratory Simulation Ready</div>
              <div style={{ fontSize: 11, maxWidth: 360, lineHeight: 1.5 }}>
                Configure ticker weights, target dates, or run one of the macro presets to simulate portfolio return paths, calculate annualized Sharp Ratio, and stress-test tech exposure.
              </div>
            </div>
          )}

          {loading && (
            <div
              style={{
                flex: 1,
                minHeight: 480,
                background: MM.panel,
                border: `1px solid ${MM.border}`,
                borderRadius: 14,
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                color: MM.muted,
                gap: 12,
              }}
            >
              <RefreshCw size={24} className="animate-spin" style={{ color: MM.accent }} />
              <span style={{ fontSize: 12, fontStyle: 'italic' }}>Simulating daily tape returns...</span>
            </div>
          )}

          {result && !loading && (
            <>
              {/* Metrics cards grid */}
              <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                <MetricCard
                  label="Total Return"
                  value={`${result.metrics.total_return}%`}
                  tone={result.metrics.total_return > 0 ? 'up' : result.metrics.total_return < 0 ? 'down' : 'neutral'}
                  icon={result.metrics.total_return > 0 ? ArrowUpRight : ArrowDownRight}
                />
                <MetricCard
                  label="Max Drawdown"
                  value={`${result.metrics.max_drawdown}%`}
                  tone="down"
                  icon={AlertTriangle}
                />
                <MetricCard
                  label="Sharpe Ratio"
                  value={result.metrics.sharpe}
                  tone={result.metrics.sharpe > 1.0 ? 'up' : result.metrics.sharpe > 0.0 ? 'neutral' : 'down'}
                  icon={Award}
                />
                <MetricCard
                  label="Beta / Volatility"
                  value={`${result.metrics.beta} / ${result.metrics.volatility}%`}
                  sub={`Correlation vs VOO: ${result.metrics.correlation}`}
                />
              </div>

              {/* Equity chart */}
              <PanelCard
                title={result.metadata.scenarioName ? `Stress Simulation Path · ${result.metadata.scenarioName}` : `Portfolio Equity Curve vs Benchmark (${result.metadata.benchmark || 'VOO'})`}
                status="live"
              >
                <div style={{ height: 320, width: '100%', marginTop: 8 }}>
                  <EquityChart portfolio={result.portfolioSeries} benchmark={result.benchmarkSeries} height={320} />
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: MM.dim, borderTop: `1px solid ${MM.border}`, paddingTop: 8, marginTop: 8 }}>
                  <span>Area: Portfolio Equity Curve · Dashed: Benchmark</span>
                  <span style={{ fontFamily: mono }}>{result.metadata.startDate} to {result.metadata.endDate}</span>
                </div>
              </PanelCard>

              {/* Scenario details / warning diagnostics */}
              {result.metadata.scenarioName && (
                <div
                  style={{
                    background: `linear-gradient(180deg, rgba(251,148,35,.04), transparent), ${MM.panel}`,
                    border: `1px solid rgba(251,148,35,.15)`,
                    borderRadius: 14,
                    padding: 16,
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 8,
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: MM.accent, fontSize: 12, fontWeight: 600 }}>
                    <ShieldAlert size={14} />
                    Macro stress simulation impact diagnostic
                  </div>
                  <div style={{ fontSize: 12, color: MM.textSoft, lineHeight: 1.55 }}>
                    Under the <strong>{result.metadata.scenarioName}</strong> preset (simulating a {result.metadata.durationWeeks}-week dump), your portfolio projects a maximum drawdown of <strong>{result.metrics.max_drawdown}%</strong>, returning <strong>{result.metrics.total_return}%</strong>.
                    {result.metadata.usedFallbackPositions && (
                      <p style={{ marginTop: 6, color: MM.accent }}>
                        No live portfolio was available — this used an illustrative example allocation, not your real holdings.
                      </p>
                    )}
                    {(() => {
                      const shocks = result.metadata.shockDetails || {};
                      const techHits = Object.keys(shocks).filter((s) => TECH_SYMBOLS.has(s));
                      if (techHits.length === 0) return null;
                      const sliShock = shocks['SLI'];
                      return (
                        <p style={{ marginTop: 6, color: MM.muted }}>
                          This scenario shocks {techHits.join('/')} directly, so correlation to the VOO index ({result.metrics.correlation}) is driven mostly by that tech exposure.
                          {sliShock !== undefined && (
                            <> High-risk speculative positions (like SLI) see a {sliShock}% shock in this preset — exceeding core thesis exits will invalidate small speculative sized lanes.</>
                          )}
                        </p>
                      );
                    })()}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
