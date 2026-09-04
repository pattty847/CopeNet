// The ticker workspace frame.
//
// One fixed frame, no page scroll. Left edge navigates between assets, the chart owns the
// canvas, research docks beneath it on a resizable seam with snap presets. Everything the
// operator does happens
// inside this rectangle — which is the difference between an instrument and an article.

import { ChartStage, type StagePlot } from './ChartStage';
import { ChartToolbar } from './ChartToolbar';
import { CompareMenu, EventsMenu, SettingsMenu } from './chartMenus';
import { PlotsMenu } from './PlotsMenu';
import { MM } from './marketUi';
import { PriceAlertControl } from './PriceAlertControl';
import { ResearchDrawer } from './ResearchDrawer';
import { SymbolRail } from './SymbolRail';
import { SymbolJump } from './SymbolJump';
import { TabOverview } from './TabOverview';
import { TickerEvidencePanel } from './TickerEvidencePanel';
import { TickerFundamentalsPanel } from './TickerFundamentalsPanel';
import { TickerReadPanel } from './TickerReadPanel';
import { TickerAssetBar } from './TickerAssetBar';
import { TickerLoadState } from './TickerLoadState';
import { TickerAlertProvider } from './monitoring/TickerAlertContext';
import type { MarketWatchlistState } from './useMarketMonitorData';
import { isValuationPayload } from './types';
import { RESEARCH_TABS } from './tickerWorkspaceState';
import { useTickerViewModel } from './useTickerViewModel';
import { useTickerKeyboard } from './useTickerKeyboard';
import { useChartWorkspace } from './chartAgent/useChartWorkspace';
import { ViewResourceProvider } from './viewState/resources';
import { ChartWorkspaceToolbar } from './chartAgent/ChartWorkspaceToolbar';
import { ChartAgentPanel } from './chartAgent/ChartAgentPanel';
import './tickerWorkspace.css';

export function TickerWorkspace({
  symbol,
  onClose,
  onNavigate,
  watchlist,
}: {
  symbol: string;
  onClose: () => void;
  onNavigate: (symbol: string, type?: 'symbol' | 'formula') => void;
  watchlist: MarketWatchlistState;
}) {
  const view = useTickerViewModel(symbol, watchlist);
  const {
    ticker, viewSymbol, sec, priceAlerts, overlayMetrics, timeframe,
    setTimeframe, range, setRange, logScale, setLogScale, showVolume,
    setShowVolume, tab, indicators, indicatorLayout, handlePaneStretch, railCollapsed,
    setRailCollapsed, overlayMetric, setOverlayMetric, effectiveFrequency, setOverlayFrequency, comparisons,
    setComparisons, showInsider, setShowInsider, insiderLookback, setInsiderLookback, insiderDisplay,
    setInsiderDisplay, alertPlacing, setAlertPlacing, pickedAlertPrice, setPickedAlertPrice, railCursor,
    setRailCursor, jumpOpen, setJumpOpen, jumpSeed, setJumpSeed, watchBusy,
    setWatchBusy, normalized, detail, profile, snap, drawerSize,
    setSnap, resizeDrawer, cycleDrawerSnap, comparing, overlaySeries, overlayIsValuation,
    rawBars, bars, computedIndicators, comparisonLines, comparisonWarning, overlayPoints,
    railEntries, chartEvidence, chartEventRows, openTab, plotMetric, indicatorActions,
    addIndicatorToLayout, addComparison,
  } = view;

  const chartWorkspace = useChartWorkspace(view);

  useTickerKeyboard(view, onNavigate);

  if (!detail) {
    return <TickerLoadState symbol={normalized} error={ticker.error} onClose={onClose} onRetry={ticker.reload} />;
  }

  const watched = watchlist.symbols.has(detail.symbol);
  const toggleWatch = async () => {
    setWatchBusy(true);
    try {
      if (watched) await watchlist.remove(detail.symbol);
      else await watchlist.add(detail.symbol, detail.name);
    } finally {
      setWatchBusy(false);
    }
  };

  const overlayInfo = overlayMetric ? overlayMetrics.find((entry) => entry.id === overlayMetric) ?? null : null;
  const overlayLatest = overlaySeries.data?.observations?.filter((row) => row.value != null).slice(-1)[0];
  const plots: StagePlot[] = [];
  if (overlayInfo && overlayPoints?.length) {
    plots.push({
      id: overlayInfo.id,
      label: overlayInfo.label,
      color: MM.info,
      value: overlayLatest?.value == null
        ? undefined
        : overlayIsValuation
          ? `${overlayLatest.value.toFixed(1)}×`
          : undefined,
      onRemove: () => setOverlayMetric(null),
    });
  }

  const secWarnings = (sec.payload?.warnings?.length ?? 0) + (sec.error ? 1 : 0);
  const overlayWarnings = overlaySeries.error ? 1 : 0;
  const dataWarning = detail.intelligence?.dataQuality.thinHistory
    ? `Thin history — ${detail.intelligence.dataQuality.historyWeeks} weeks. Trend conclusions are lower confidence.`
    : null;

  return (
    <ViewResourceProvider resources={chartWorkspace.resources}>
    <TickerAlertProvider symbol={viewSymbol} timeframe={timeframe}>
    <div className="tw">
      <TickerAssetBar
        detail={detail}
        profile={profile}
        watched={watched}
        watchBusy={watchBusy}
        pending={ticker.stale ? symbol.trim().toUpperCase() : null}
        onBack={onClose}
        onToggleWatch={() => void toggleWatch()}
        onOpenPosition={() => openTab('overview')}
      />

      <div className="tw-body">
        <SymbolRail
          entries={railEntries}
          current={detail.symbol}
          cursor={railCursor}
          collapsed={railCollapsed}
          onToggle={() => setRailCollapsed((value) => !value)}
          onSelect={onNavigate}
        />

        <div className="tw-main">
          <ChartToolbar
            timeframe={timeframe}
            onTimeframe={setTimeframe}
            range={range}
            onRange={setRange}
            logScale={logScale}
            onLogScale={setLogScale}
            comparisonActive={comparing}
            comparisonCount={comparisons.length}
            plotCount={plots.length + indicators.length}
            eventsActive={showInsider}
            drawerOpen={snap !== 'collapsed'}
            onToggleDrawer={() => setSnap(snap === 'collapsed' ? 'half' : 'collapsed')}
            plotsMenu={(anchor, open, close) => (
              <PlotsMenu
                anchor={anchor}
                open={open}
                onClose={close}
                metrics={overlayMetrics}
                metric={overlayMetric}
                frequency={effectiveFrequency}
                onFrequency={setOverlayFrequency}
                onClearMetric={() => setOverlayMetric(null)}
                onMetric={plotMetric}
                showVolume={showVolume}
                onShowVolume={setShowVolume}
                comparisonActive={comparing}
                indicators={indicators}
                computedIndicators={computedIndicators}
                onAddIndicator={addIndicatorToLayout}
                indicatorActions={indicatorActions}
              />
            )}
            compareMenu={(anchor, open, close) => (
              <CompareMenu
                anchor={anchor}
                open={open}
                onClose={close}
                expressions={comparisons}
                onAdd={addComparison}
                onRemove={(expression) => setComparisons((current) => current.filter((item) => item !== expression))}
                onClear={() => setComparisons([])}
              />
            )}
            eventsMenu={(anchor, open, close) => (
              <EventsMenu
                anchor={anchor}
                open={open}
                onClose={close}
                showInsider={showInsider}
                onShowInsider={setShowInsider}
                lookback={insiderLookback}
                onLookback={setInsiderLookback}
                displayMode={insiderDisplay}
                onDisplayMode={setInsiderDisplay}
                disabled={comparing}
              />
            )}
            alertControl={
              <PriceAlertControl
                alerts={priceAlerts.alerts}
                currentPrice={detail.quote.price ?? 0}
                pickedPrice={pickedAlertPrice}
                placing={alertPlacing}
                loading={priceAlerts.loading}
                error={priceAlerts.error}
                disabled={comparing}
                onStartPlacing={() => setAlertPlacing(true)}
                onStopPlacing={() => { setAlertPlacing(false); setPickedAlertPrice(null); }}
                onCreate={async (direction, threshold) => {
                  const created = await priceAlerts.create(direction, threshold);
                  if (created) setPickedAlertPrice(null);
                  return created;
                }}
                onCancel={priceAlerts.cancel}
              />
            }
            settingsMenu={(anchor, open, close) => (
              <SettingsMenu
                anchor={anchor}
                open={open}
                onClose={close}
                intelligence={detail.intelligence}
                priceBasis={detail.quote.priceBasis}
                barCount={bars.length}
                plotSource={
                  overlayInfo && overlaySeries.data
                    ? {
                        label: overlayInfo.label,
                        count: overlaySeries.data.observations.length,
                        form: overlayLatest?.sources?.[0]?.form,
                        accession: overlayLatest?.sources?.[0]?.accessionNumber,
                        url: overlayLatest?.sources?.[0]?.sourceUrl,
                        warnings: overlaySeries.data.warnings ?? [],
                      }
                    : null
                }
              />
            )}
          />

          <ChartWorkspaceToolbar workspace={chartWorkspace} comparing={comparing} />
          <ChartStage
            chartWorkspace={chartWorkspace.bridge}
            symbol={detail.symbol}
            timeframe={timeframe}
            bars={bars}
            events={chartEventRows}
            evidence={chartEvidence}
            plots={plots}
            warning={dataWarning}
            comparisonMode={comparing}
            comparisonLines={comparisonLines}
            comparisonError={comparing ? comparisonWarning : null}
            financialOverlay={comparing ? undefined : overlayPoints}
            financialOverlayKind={overlayMetric ?? undefined}
            financialOverlayUnit={
              !overlaySeries.data ? undefined : isValuationPayload(overlaySeries.data) ? 'ratio' : overlaySeries.data.observations[0]?.unit
            }
            financialOverlayValuation={overlayIsValuation}
            financialOverlayInverted={overlaySeries.data != null && isValuationPayload(overlaySeries.data) && overlaySeries.data.inverted === true}
            priceAlerts={comparing ? [] : priceAlerts.alerts}
            draftAlertPrice={pickedAlertPrice}
            alertPlacementActive={alertPlacing}
            onAlertPriceSelected={(price) => { setPickedAlertPrice(price); setAlertPlacing(false); }}
            insiderDisplayMode={insiderDisplay}
            logScale={logScale}
            showVolume={showVolume}
            // Comparison rebases the price pane to indexed percent, so every price-anchored
            // indicator is genuinely inapplicable while it is on. The LAYOUT is untouched, so
            // leaving Compare restores exactly what was there.
            indicators={comparing ? [] : computedIndicators}
            indicatorActions={indicatorActions}
            indicatorPriceStretch={indicatorLayout.priceStretch}
            onIndicatorPaneStretch={handlePaneStretch}
            layoutKey={`${snap}:${Math.round(drawerSize ?? 0)}:${railCollapsed}:${chartWorkspace.open}`}
            overlay={
              jumpOpen ? (
                <SymbolJump
                  seed={jumpSeed}
                  onClose={() => setJumpOpen(false)}
                  onPick={(picked, type) => { setJumpOpen(false); onNavigate(picked, type); }}
                />
              ) : null
            }
          />

          <ResearchDrawer
            tab={tab}
            onTab={openTab}
            entries={RESEARCH_TABS.filter((entry) => profile.tabs.includes(entry.id))}
            snap={snap}
            onSnap={setSnap}
            size={drawerSize}
            onResize={resizeDrawer}
            onCycleSnap={cycleDrawerSnap}
            warnings={{ evidence: secWarnings, fundamentals: overlayWarnings }}
          >
            {/* Each panel receives `active`, which is how Codex's panels gate their own
                fetching and lazily import Recharts — the drawer's tab state drives it for
                free, so nothing below the chart loads until you open it. */}
            {tab === 'overview' && <TabOverview detail={detail} profile={profile} />}
            {tab === 'fundamentals' && <TickerFundamentalsPanel symbol={detail.symbol} active={tab === 'fundamentals'} />}
            {tab === 'evidence' && <TickerEvidencePanel symbol={detail.symbol} state={sec} active={tab === 'evidence'} />}
            {tab === 'synthesis' && <TickerReadPanel symbol={detail.symbol} />}
          </ResearchDrawer>
        </div>
        <ChartAgentPanel workspace={chartWorkspace} symbol={detail.symbol} timeframe={timeframe} />
      </div>
    </div>
    </TickerAlertProvider>
    </ViewResourceProvider>
  );
}
