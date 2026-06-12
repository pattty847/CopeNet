// Operator inbox derivation — real logic (NOT mock data). Builds a
// priority-ordered inbox from live approval history + paused-run state.
// Relocated out of runtime/mocks.ts during the Tier 4 mock purge.

import type { InboxItem } from '../types/backend';
import type { ApprovalRequest } from './types';

export function buildInboxItems(
  approvals: ApprovalRequest[],
  runPausedReason: 'awaiting_approval' | null,
): InboxItem[] {
  const items: InboxItem[] = [];

  // Paused-run urgent item (most priority)
  if (runPausedReason === 'awaiting_approval') {
    const pending = approvals.find((a) => a.status === 'pending');
    if (pending) {
      items.push({
        id: `inbox-paused-${pending.approvalId}`,
        priority: 'urgent',
        kind: 'paused_run',
        title: 'Run paused — action required',
        subtitle: `${pending.toolId} → ${pending.proposedAction.target ?? 'unknown target'}`,
        createdAt: pending.createdAt,
        sessionKey: pending.sessionKey,
        runId: pending.runId,
        approvalData: pending,
      });
    }
  }

  // Pending approvals not yet shown as paused-run
  for (const approval of approvals) {
    if (approval.status !== 'pending') continue;
    const alreadyShown = items.some((i) => i.approvalData?.approvalId === approval.approvalId);
    if (!alreadyShown) {
      items.push({
        id: `inbox-approval-${approval.approvalId}`,
        priority: 'attention',
        kind: 'pending_approval',
        title: `Pending: ${approval.toolId}`,
        subtitle: approval.proposedAction.description,
        createdAt: approval.createdAt,
        sessionKey: approval.sessionKey,
        runId: approval.runId,
        approvalData: approval,
      });
    }
  }

  // Recently resolved — show last 5
  const resolved = approvals
    .filter((a) => a.status !== 'pending')
    .slice(0, 5);

  for (const approval of resolved) {
    const decisionLabel =
      approval.status === 'approved' ? 'Approved'
      : approval.status === 'modified' ? 'Modified'
      : approval.status === 'rejected' ? 'Rejected'
      : 'Expired';
    items.push({
      id: `inbox-resolved-${approval.approvalId}`,
      priority: 'info',
      kind: 'resolved_approval',
      title: `${decisionLabel}: ${approval.toolId}`,
      subtitle: approval.proposedAction.description,
      createdAt: approval.resolvedAt ?? approval.createdAt,
      sessionKey: approval.sessionKey,
      runId: approval.runId,
      approvalData: approval,
    });
  }

  // Sort: urgent first, then attention, then info; within same priority by newest first
  const PRIORITY_ORDER: Record<string, number> = { urgent: 0, attention: 1, info: 2 };
  items.sort((a, b) => {
    const pDiff = PRIORITY_ORDER[a.priority] - PRIORITY_ORDER[b.priority];
    if (pDiff !== 0) return pDiff;
    return new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime();
  });

  return items;
}
