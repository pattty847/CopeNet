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

// ---------------------------------------------------------------------------
// Messaging platform configuration (operator settings)
// ---------------------------------------------------------------------------

export type MessagingPlatform = 'telegram' | 'slack' | 'discord';
export type PlatformConnectionStatus = 'connected' | 'disconnected' | 'error' | 'unconfigured';

export interface TelegramBotConfig {
  botUsername: string | null;           // e.g. "@CopeNetBot" — resolved on connect
  tokenMasked: string | null;           // e.g. "tg:7321...xxxx" — never full token
  connectionStatus: PlatformConnectionStatus;
  lastVerifiedAt: string | null;        // ISO timestamp
  errorMessage: string | null;
}

export interface MessagingApprovalPolicy {
  requireApprovalByDefault: boolean;    // global default; per-destination overrides apply
  hardlineBlocklist: string[];          // destination targets that can NEVER be sent to by the agent
}

export interface MessagingConfig {
  telegram: TelegramBotConfig | null;
  destinations: MessageDestination[];
  approvalPolicy: MessagingApprovalPolicy;
}

// ---------------------------------------------------------------------------
// Orchestration runs (future execute_code-style tool)
// ---------------------------------------------------------------------------

export type OrchestrationRunStatus =
  | 'pending'
  | 'running'
  | 'completed'
  | 'failed'
  | 'approval_required'
  | 'cancelled';

export interface OrchestrationToolInvocation {
  toolId: string;
  count: number;
  summary: string;              // e.g. "probe output paths → 12 files"
}

export interface OrchestrationRun {
  orchestrationId: string;
  runId: string;
  sessionKey: string;
  status: OrchestrationRunStatus;
  goal: string;                 // operator-readable description of what the script does
  scriptSummary: string | null; // one-sentence description of the script logic
  toolsUsed: OrchestrationToolInvocation[];
  toolBudget: number;           // max tool calls allowed
  toolCallsUsed: number;
  timeoutSeconds: number;
  durationMs: number | null;    // null if not yet completed
  outputSummary: string | null;
  relatedArtifactIds: string[];
  approvalRequired: boolean;    // whether any step required approval
  approvalId: string | null;    // linked approval if approvalRequired
  startedAt: string;
  completedAt: string | null;
  error: string | null;
}

// ---------------------------------------------------------------------------
// Operator inbox / action center
// ---------------------------------------------------------------------------

export type InboxItemPriority = 'urgent' | 'attention' | 'info';
export type InboxItemKind =
  | 'paused_run'
  | 'pending_approval'
  | 'failed_send'
  | 'resolved_approval'
  | 'sent_message';

export interface InboxItem {
  id: string;
  priority: InboxItemPriority;
  kind: InboxItemKind;
  title: string;
  subtitle: string;
  createdAt: string;
  sessionKey: string;
  runId: string | null;
  // Linked data — at most one will be set
  approvalData?: ApprovalRequest;
  outboundData?: OutboundMessageRecord;
}

// ---------------------------------------------------------------------------
// Run timeline (paused-run lifecycle view)
// ---------------------------------------------------------------------------

export type RunTimelineEventKind =
  | 'run_started'
  | 'tool_called'
  | 'tool_result'
  | 'approval_requested'
  | 'decision_made'
  | 'run_resumed'
  | 'run_completed'
  | 'run_failed'
  | 'note';

export type RunTimelineEventStatus = 'ok' | 'pending' | 'paused' | 'error' | 'skipped';

export interface RunTimelineEvent {
  id: string;
  kind: RunTimelineEventKind;
  at: string;                        // ISO timestamp
  label: string;                     // short label for the event
  detail?: string | null;            // one-line contextual detail
  status: RunTimelineEventStatus;
  toolId?: string | null;            // for tool_called / tool_result
  linkedApprovalId?: string | null;  // for approval_requested / decision_made
  durationMs?: number | null;
}

export interface RunTimeline {
  runId: string;
  sessionKey: string;
  pausedAt: string | null;           // ISO — when/if the run paused; null if not paused
  resumedAt: string | null;
  events: RunTimelineEvent[];
}

// ---------------------------------------------------------------------------
// Provider auth (openai-codex OAuth flow + future providers)
// Mirrors openai_codex.py OpenAICodexAuthService.status() return shape.
// ---------------------------------------------------------------------------

export type ProviderAuthType = 'oauth' | 'api_key' | 'none';

export interface ProviderAuthStatus {
  provider: string;                   // e.g. "openai-codex"
  profileId: string;                  // e.g. "openai-codex:default"
  requiresAuth: boolean;
  authType: ProviderAuthType;
  authenticated: boolean;
  expired: boolean;
  accountId: string | null;           // user account identifier if known
  expiresAt: number | null;           // unix ms — when the token expires
  scopes: string[];                   // OAuth scopes granted
  // storePath is backend-only, not surfaced in UI
}

export interface ProviderAuthLoginInfo {
  loginId: string;                    // correlates begin → complete
  authorizeUrl: string;               // open in browser to authenticate
  redirectUri: string;
  state: string;
}

// ---------------------------------------------------------------------------
// Live tool execution (frontend-only, for in-flight run visibility)
// Populated from toolExecution payloads on streaming delta/final events.
// ---------------------------------------------------------------------------

// The five states the operator can observe for a tool call during a run.
// 'queued' is a frontend-only state (pre-first-call in a run).
// 'blocked' matches tool_loop policy rejections (channel: "policy").
export type ToolExecutionState = 'queued' | 'running' | 'success' | 'blocked' | 'failed';

export interface LiveToolCall {
  id: string;                         // locally generated (runId + index)
  toolId: string;
  state: ToolExecutionState;
  summary: string;
  error?: string | null;
  startedAt: string;                  // ISO — when we first saw this tool
  completedAt?: string | null;        // ISO — when toolExecution arrived
}

// Turn-level summary snapshot: extracted from turnState on final events.
// Mirrors the subset of TurnState.to_public_dict() we care about in the UI.
export interface TurnStateSnapshot {
  toolCallCount: number;
  visitedTools: string[];
  visitedPaths: string[];
  groundingActions: string[];
  failedActions: Array<{ toolId: string; summary: string; error: string | null }>;
  openQuestions: string[];
  lastToolResultSummary: string;
  terminalReason: string | null;
  transitionReason: string;
}
