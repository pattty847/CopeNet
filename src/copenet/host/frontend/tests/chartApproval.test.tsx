import assert from 'node:assert/strict';
import test from 'node:test';
import { renderToStaticMarkup } from 'react-dom/server';
import { ApprovalRequestCard } from '../src/components/ApprovalRequestCard';
import { normalizeMessage } from '../src/lib/wsNormalizers';
import type { ApprovalRequest } from '../src/types/backend';

test('Chart approval displays its exact drawing batch and cannot grant standing shell access', () => {
  const approval: ApprovalRequest = {
    approvalId: 'approval', sessionKey: 'market', runId: 'run', status: 'pending', actionClass: 'chart_annotation',
    toolId: 'market.chart.apply', proposedAction: { description: 'Apply drawings', payload: {
      documentId: 'document', expectedRevision: 3, operationId: 'batch', operations: [{ kind: 'update', objectId: 'support', patch: { label: 'Revised support' } }],
    } }, rationale: 'External prose was captured', createdAt: '', resolvedAt: null, outcome: null,
  };
  const html = renderToStaticMarkup(<ApprovalRequestCard approval={approval} />);
  assert.match(html, /Chart Annotation/);
  assert.match(html, /Revised support/);
  assert.match(html, /expectedRevision/);
  assert.match(html, /Approve/);
  assert.doesNotMatch(html, /Always allow/);
});

test('Transcript chart references survive normalization with old-message safe fallback', () => {
  const marketContext = { observationId: 'observation', documentId: 'document', viewId: 'view', detail: 'deep', access: 'read', hasExternalProse: true, symbol: 'TEST', timeframe: 'D' };
  const message = normalizeMessage({ content: 'Hello', marketContext }, 'market', 'message', 'user', 'final');
  assert.deepEqual(message.marketContext, marketContext);
  assert.equal(normalizeMessage({ content: 'Old message' }, 'market', 'old', 'user', 'final').marketContext, null);
});

test('Chart forecast approval exposes its exact setup without allowing standing execution', () => {
  const approval: ApprovalRequest = {
    approvalId: 'forecast-approval', sessionKey: 'forecast-lane', runId: 'run', status: 'pending', actionClass: 'chart_forecast',
    toolId: 'market.forecast.submit', proposedAction: { description: 'Record simulated setup', payload: {
      kind: 'setup', direction: 'long', entry: { kind: 'limit', price: 100 }, stop: 90, targets: [{ price: 120, fraction: 1 }], thesis: 'Test setup',
    } }, rationale: 'Captured external prose needs review', createdAt: '', resolvedAt: null, outcome: null,
  };
  const html = renderToStaticMarkup(<ApprovalRequestCard approval={approval} />);
  assert.match(html, /Chart Forecast/); assert.match(html, /simulated trade/);
  assert.match(html, /entry/); assert.match(html, /stop/); assert.match(html, /targets/);
  assert.doesNotMatch(html, /Process Execution|Always allow/);
});
