export type WsStatus = 'connecting' | 'connected' | 'disconnected' | 'auth_failed';
export type ChatState = 'delta' | 'final' | 'error' | 'aborted';
export type MessageRole = 'user' | 'assistant' | 'system';

export interface Session {
  key: string;
  sessionId: string;
  title: string | null;
  provider: string;
  model: string | null;
  systemPromptId: string | null;
  taskPromptId: string | null;
  archived: boolean;
  providerSessionId: string | null;
  createdAt: string;
  updatedAt: string;
  lastRunId: string | null;
  inFlightRunId: string | null;
}

export interface ToolExecution {
  toolId: string;
  ok: boolean;
  summary: string;
  error?: string | null;
}

export interface Message {
  localId: string;
  sessionKey: string;
  runId: string | null;
  role: MessageRole;
  content: string;
  timestamp: string;
  provider: string | null;
  model: string | null;
  providerSessionId: string | null;
  state: ChatState | null;
  toolExecution: ToolExecution | null;
  errorMessage: string | null;
  optimistic: boolean;
}

export interface Provider {
  id: string;
  displayName: string;
  available: boolean;
  error?: string;
  capabilities?: Record<string, boolean>;
}

export interface Model {
  id: string;
  displayName: string;
  provider: string;
  description?: string | null;
  kind: string;
  capabilities: Record<string, boolean>;
  recommendedFor: string[];
  metadata: Record<string, unknown>;
}

export interface ToolDescriptor {
  id: string;
  name: string;
  description: string;
  category: string;
  inputSchema: Record<string, unknown>;
  safetyLevel: string;
  capabilities: string[];
}

export interface PromptOption {
  id: string;
  name: string;
}

export type DataToolsRoute = 'hub' | 'sources' | 'media';

export interface DraftSettings {
  provider: string;
  model: string;
  systemPromptId: string;
  taskPromptId: string;
}

export interface PublicMessagePayload {
  runId?: string | null;
  role?: string | null;
  content?: string | null;
  provider?: string | null;
  model?: string | null;
  providerSessionId?: string | null;
  timestamp?: string | null;
  state?: string | null;
  toolExecution?: ToolExecution | null;
}

export interface ChatEventPayload {
  runId?: string | null;
  sessionKey: string;
  seq: number;
  state: ChatState;
  message?: PublicMessagePayload | null;
  errorMessage?: string | null;
  provider?: string | null;
  model?: string | null;
  capabilities?: Record<string, unknown> | null;
  toolExecution?: ToolExecution | null;
}

export interface RpcErrorPayload {
  code: string;
  message: string;
  details?: unknown;
}

export interface ResponseFrame<TPayload = Record<string, unknown>> {
  type: 'res';
  id: string;
  ok: boolean;
  payload?: TPayload;
  error?: RpcErrorPayload;
}

export interface EventFrame<TPayload = Record<string, unknown>> {
  type: 'event';
  event: string;
  payload?: TPayload;
  seq?: number;
}

export type IncomingFrame = ResponseFrame | EventFrame;

export interface MediaAsset {
  assetId: string;
  appId: string;
  sourceType: string;
  sourceUrl: string | null;
  sourcePath: string | null;
  title: string;
  mediaPath: string | null;
  transcriptPath: string | null;
  transcriptSource: string | null;
  transcriptExcerpt: string;
  metadata: Record<string, unknown>;
  durationSeconds: number | null;
  latencyMs: number | null;
  createdAt: string;
  updatedAt: string;
}

export interface MediaAssetDetail extends MediaAsset {
  transcriptContent: string;
}

export interface SessionExportPayload {
  session: Session;
  messages: PublicMessagePayload[];
  markdown: string;
}

export interface RunStep {
  toolId: string;
  ok: boolean;
  summary: string;
  error?: string | null;
}

export interface SessionRunRecord {
  runId: string;
  sessionKey: string;
  provider: string;
  model: string | null;
  status: string;
  userMessage: string;
  toolExecutionMode: string;
  willAttemptToolLoop: boolean;
  startedAt: string;
  completedAt: string | null;
  workingSet: Record<string, unknown>;
  toolSteps: RunStep[];
  artifactIds: string[];
  outputSummary: string;
  error: string | null;
  metadata: Record<string, unknown>;
}

export interface SessionStateRecord {
  session_key: string;
  task_summary: string | null;
  goals: string[];
  active_entities: string[];
  working_set_refs: string[];
  constraints: string[];
  unresolved_questions: string[];
  prior_decisions: string[];
  plan_snapshot: Record<string, unknown>;
  relevant_asset_ids: string[];
  relevant_artifact_ids: string[];
  created_at: string;
  updated_at: string;
}

// ---------------------------------------------------------------------------
// Approval subsystem
// ---------------------------------------------------------------------------

export type ApprovalStatus = 'pending' | 'approved' | 'rejected' | 'modified' | 'expired';

export type ApprovalActionClass =
  | 'external_communication'
  | 'filesystem_write'
  | 'process_execution'
  | 'network_side_effect'
  | 'credential_or_sensitive_target';

export interface ApprovalOutcome {
  decision: 'approved' | 'rejected' | 'modified';
  modifiedPayload?: Record<string, unknown>;
  note?: string | null;
  decidedAt: string;
}

export interface ApprovalRequest {
  approvalId: string;
  runId: string;
  sessionKey: string;
  status: ApprovalStatus;
  actionClass: ApprovalActionClass;
  toolId: string;
  proposedAction: {
    description: string;
    target?: string | null;
    payload?: Record<string, unknown>;
  };
  rationale: string | null;
  createdAt: string;
  resolvedAt: string | null;
  outcome: ApprovalOutcome | null;
}

// ---------------------------------------------------------------------------
// Outbound messaging
// ---------------------------------------------------------------------------

export type OutboundMessageStatus = 'drafted' | 'pending_approval' | 'approved' | 'sent' | 'failed';

export interface OutboundMessageRecord {
  messageId: string;
  runId: string;
  sessionKey: string;
  platform: string;
  target: string;
  targetDisplayName: string | null;
  messageText: string;
  status: OutboundMessageStatus;
  approvalId: string | null;
  sentAt: string | null;
  failureReason: string | null;
  createdAt: string;
}

// ---------------------------------------------------------------------------
// Messaging destinations (operator-configured address book)
// ---------------------------------------------------------------------------

export type DestinationStatus = 'configured' | 'unconfigured' | 'error';

export interface MessageDestination {
  id: string;
  platform: string;             // 'telegram', 'slack', etc.
  target: string;               // canonical target, e.g. "telegram:@copenet_ops"
  displayName: string;          // human-readable label
  threadLabel?: string | null;  // optional topic/thread label
  isDefault: boolean;           // home/default destination for this platform
  requiresApproval: boolean;    // whether sends to this destination need operator approval
  status: DestinationStatus;
}
