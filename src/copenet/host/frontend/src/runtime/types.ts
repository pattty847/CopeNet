// Frontend-local types for the new runtime UI surfaces.
//
// These describe the conceptual runtime state (working set, artifacts, run
// activity, causal breadcrumbs) that the backend is evolving toward. The
// frontend renders them today from mocked data so the UI is ready to wire up
// when the backend lands. Keep this file small and focused — it is not a
// backend contract.

import type { ApprovalRequest, OutboundMessageRecord } from '../types/backend';
export type {
  ApprovalRequest,
  ApprovalOutcome,
  ApprovalStatus,
  ApprovalActionClass,
  OutboundMessageRecord,
  OutboundMessageStatus,
  OrchestrationRun,
  OrchestrationRunStatus,
  OrchestrationToolInvocation,
  InboxItem,
  InboxItemPriority,
  InboxItemKind,
  RunTimeline,
  RunTimelineEvent,
  RunTimelineEventKind,
  RunTimelineEventStatus,
  MessageDestination,
  MessagingConfig,
  TelegramBotConfig,
  MessagingApprovalPolicy,
  MessagingPlatform,
  PlatformConnectionStatus,
  ProviderAuthStatus,
  ProviderAuthType,
  ProviderAuthLoginInfo,
  LiveToolCall,
  ToolExecutionState,
  TurnStateSnapshot,
  // Pat Profile + Return Briefing
  PatProfile,
  PatProfileSource,
  PatProfilePriority,
  PatProfileGoal,
  PatProfileTonePreference,
  ProfileChangelogItem,
  ProfileChangelogChangeKind,
  BriefingAttentionItem,
  BriefingActivityItem,
  BriefingWatchItem,
  ReturnBriefingPayload,
} from '../types/backend';

export type RuntimeStatus = 'thinking' | 'executing' | 'awaiting_input' | 'idle';

export interface WorkingSetEntity {
  id: string;
  kind: 'file' | 'symbol' | 'url' | 'asset' | 'note';
  label: string;
  detail?: string;
}

export interface WorkingSetConstraint {
  id: string;
  text: string;
  severity?: 'info' | 'warn' | 'block';
}

export interface WorkingSetQuestion {
  id: string;
  text: string;
  answeredAt?: string | null;
}

export interface WorkingSet {
  taskSummary: string;
  status: RuntimeStatus;
  updatedAt: string;
  entities: WorkingSetEntity[];
  constraints: WorkingSetConstraint[];
  questions: WorkingSetQuestion[];
  referencedArtifactIds: string[];
}

export type ArtifactKind = 'summary' | 'patch_plan' | 'answer' | 'tool_bundle' | 'diff' | 'approval_request' | 'outbound_message' | 'orchestration_run';

export interface ArtifactFile {
  path: string;
  additions: number;
  deletions: number;
}

export interface ArtifactDiffBlock {
  path: string;
  hunkHeader: string;
  lines: { kind: 'add' | 'remove' | 'ctx'; text: string }[];
}

export interface Artifact {
  id: string;
  kind: ArtifactKind;
  title: string;
  oneLine: string;
  producedAt: string;
  runId?: string | null;
  // Optional shape hints for inspection
  bodyMarkdown?: string;
  files?: ArtifactFile[];
  diffBlocks?: ArtifactDiffBlock[];
  toolIds?: string[];
  promoted?: boolean;
  // approval_request kind
  approvalData?: ApprovalRequest;
  // outbound_message kind
  outboundData?: OutboundMessageRecord;
  // orchestration_run kind
  orchestrationData?: import('../types/backend').OrchestrationRun;
}

export type ActivityItemKind = 'tool_call' | 'read_batch' | 'bundle' | 'note';

export interface ActivityToolCall {
  id: string;
  kind: 'tool_call';
  toolId: string;
  summary: string;
  ok: boolean;
  durationMs: number;
  at: string;
}

export interface ActivityReadBatch {
  id: string;
  kind: 'read_batch';
  label: string;
  at: string;
  calls: ActivityToolCall[];
  mergedSummary?: string;
}

export interface ActivityBundle {
  id: string;
  kind: 'bundle';
  label: string;
  at: string;
  calls: ActivityToolCall[];
  producedArtifactId?: string;
}

export interface ActivityNote {
  id: string;
  kind: 'note';
  at: string;
  text: string;
}

export type ActivityItem =
  | ActivityToolCall
  | ActivityReadBatch
  | ActivityBundle
  | ActivityNote;

export interface RunActivity {
  runId: string;
  startedAt: string;
  endedAt?: string | null;
  items: ActivityItem[];
}

// What the InspectorDrawer is showing. Kept narrow; each target type is a
// small typed payload so the drawer can render the right view without
// passing around ad-hoc props.
export type InspectorTarget =
  | { kind: 'artifact'; artifactId: string }
  | { kind: 'diff'; artifactId: string }
  | { kind: 'batch'; batchId: string };
