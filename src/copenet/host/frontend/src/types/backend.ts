export type WsStatus = 'connecting' | 'connected' | 'disconnected' | 'auth_failed';
export type ChatState = 'delta' | 'reasoning_delta' | 'final' | 'error' | 'aborted' | 'tool_called' | 'tool_result';
export type MessageRole = 'user' | 'assistant' | 'system';

export interface Session {
  key: string;
  sessionId: string;
  title: string | null;
  provider: string;
  model: string | null;
  systemPromptId: string | null;
  taskPromptId: string | null;
  personaId: string | null;
  personaFlavorId: string | null;
  personaPrivacyTier: PersonaPrivacyTier | null;
  workspaceRoot: string | null;
  archived: boolean;
  providerSessionId: string | null;
  createdAt: string;
  updatedAt: string;
  lastRunId: string | null;
  inFlightRunId: string | null;
}

export type ToolEffectKind = 'file_read' | 'repo_search' | 'shell_command' | 'file_write' | 'file_edit' | 'artifact' | 'context' | 'raw';
export type ToolEvidenceRole = 'none' | 'discovery' | 'grounding' | 'mutation' | 'verification' | 'context' | 'artifact';

export interface ToolEffect {
  schema_version: 'tool_effect.v1';
  effect_id: string;
  decision_id?: string | null;
  turn_id: string;
  tool_id: string;
  kind: ToolEffectKind;
  target?: string | null;
  preview?: Record<string, unknown> | null;
  artifact_id?: string | null;
  evidence_role: ToolEvidenceRole;
}

export interface HarnessDecision {
  user_goal: string;
  request_kind: string;
  route: string;
  next_action: string;
  risk: string;
  evidence_requirements: string[];
  tool_decision: {
    needed: boolean;
    candidate_tool_ids: string[];
    selected_tool_id?: string | null;
    trace_note: string;
  };
  missing: string[];
  assumptions: string[];
  trace_note: string;
}

export interface HarnessDecisionRecord {
  schema_version: 'harness_decision_record.v1';
  decision_id: string;
  turn_id: string;
  control_mode: 'trace_only';
  status: 'parsed' | 'repaired' | 'fallback' | 'unavailable';
  decision: HarnessDecision | null;
  error_summary?: string;
}

export interface ToolExecution {
  toolId: string;
  ok: boolean;
  summary: string;
  turnId?: string | null;
  decisionId?: string | null;
  callId?: string | null;
  channel?: string | null;
  error?: string | null;
  artifactId?: string | null;
  target?: string | null;
  workspaceRoot?: string | null;
  scope?: 'inside_workspace' | 'outside_workspace' | null;
  accessAction?: 'read' | 'write' | 'unknown' | null;
  policyDecision?: 'allowed' | 'read_roam' | 'write_blocked' | 'approval_required' | 'unsafe_unknown' | null;
  policySummary?: string | null;
  effect?: ToolEffect | null;
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
  /** Set while the socket is down but the run is believed still in-flight server-side.
   *  The UI shows "reconnecting…" instead of a false "aborted" (Phase 4.6). */
  reconnecting?: boolean;
  /** Structured part array — populated when a run emits tool_called events.
   *  The content field is kept in sync for backward compat and export.
   *  Render parts[] when present; fall back to content + toolExecution otherwise. */
  parts?: MessagePart[] | null;
}

// ---------------------------------------------------------------------------
// Message parts — structured inline tool rendering in the transcript.
// Activated on first tool_called event for a run; prior content is
// snapshotted into a TextPart. Content field kept for compat/export.
// ---------------------------------------------------------------------------

export interface TextPart {
  kind: 'text';
  content: string;
}

/** Inline reasoning-summary narration streamed between tool calls (Phase 2/4). */
export interface ThinkingPart {
  kind: 'thinking';
  text: string;
}

export interface ToolCallPart {
  kind: 'tool_call';
  callId: string;
  toolId: string;
  turnId?: string | null;
  decisionId?: string | null;
  /** One-line hint shown while the tool is in-flight — path, query, etc. */
  hint?: string | null;
  target?: string | null;
  at: string; // ISO
}

// Preview variants — bounded, always safe to truncate.
export interface FileReadPreview {
  type: 'file_read';
  path: string;
  lines: string[];         // max 20 lines shown
  totalLines?: number | null;
}

export interface RepoSearchPreview {
  type: 'repo_search';
  query: string;
  matches: Array<{ path: string; line: number; snippet: string }>; // max 8
  totalMatches?: number | null;
}

export interface RawPreview {
  type: 'raw';
  text: string;            // truncated summary
}
/** files.write / files.edit — unified diff of the change, rendered green/red. */
export interface DiffPreview {
  type: 'diff';
  path: string;
  diff: string;            // unified diff text (bounded by the backend)
  linesAdded: number;
  linesRemoved: number;
  truncated?: boolean;
  created?: boolean;       // true when the write created a new file
  afterDigest?: string;    // digest the edit left the file at — the revert key
}

export type ToolResultPreview = FileReadPreview | RepoSearchPreview | RawPreview | DiffPreview;

export interface ToolResultPart {
  kind: 'tool_result';
  callId: string;
  toolId: string;
  turnId?: string | null;
  decisionId?: string | null;
  ok: boolean;
  summary: string;
  error?: string | null;
  artifactId?: string | null;
  target?: string | null;
  workspaceRoot?: string | null;
  scope?: 'inside_workspace' | 'outside_workspace' | null;
  accessAction?: 'read' | 'write' | 'unknown' | null;
  policyDecision?: 'allowed' | 'read_roam' | 'write_blocked' | 'approval_required' | 'unsafe_unknown' | null;
  policySummary?: string | null;
  preview?: ToolResultPreview | null;
  effect?: ToolEffect | null;
  at: string; // ISO
}

export interface ToolBatchMember {
  callId: string;
  toolId: string;
  turnId?: string | null;
  decisionId?: string | null;
  ok: boolean;
  summary: string;
  error?: string | null;
  artifactId?: string | null;
  target?: string | null;
  workspaceRoot?: string | null;
  scope?: 'inside_workspace' | 'outside_workspace' | null;
  accessAction?: 'read' | 'write' | 'unknown' | null;
  policyDecision?: 'allowed' | 'read_roam' | 'write_blocked' | 'approval_required' | 'unsafe_unknown' | null;
  policySummary?: string | null;
  preview?: ToolResultPreview | null;
  effect?: ToolEffect | null;
}

/** tool.batch — one collapsed card for N grouped file reads or search passes. */
export interface ToolBatchPart {
  kind: 'tool_batch';
  batchId: string;
  label: string;           // e.g. "Read 8 files"
  members: ToolBatchMember[];
  ok: boolean;
  workspaceRoot?: string | null;
  at: string; // ISO
}

export type MessagePart = TextPart | ThinkingPart | ToolCallPart | ToolResultPart | ToolBatchPart;

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
  riskClass?: string;
  approvalMode?: string;
  evidenceRole?: ToolEvidenceRole | string;
  sideEffect?: 'none' | 'read' | 'write' | 'external' | string;
  requiresConfirmation?: boolean;
}

export interface PromptOption {
  id: string;
  name: string;
}

export interface PromptOptimizationVariant {
  id: string;
  label: string;
  prompt: string;
  rationale: string;
}

export interface PromptOptimizationResult {
  variants: PromptOptimizationVariant[];
  provider: string;
  model: string | null;
}

export type DataToolsRoute = 'hub' | 'sources' | 'media' | 'web' | 'messaging' | 'persona';

export interface DraftSettings {
  provider: string;
  model: string;
  systemPromptId: string;
  taskPromptId: string;
  personaId: string;
  personaFlavorId: string;
  personaPrivacyTier: PersonaPrivacyTier;
  workspaceRoot: string;
}

export type PersonaPrivacyTier = 'private' | 'safe' | 'off';

export interface PersonaHomeSummary {
  personaId: string;
  personaFlavorId: string | null;
  personaPrivacyTier: PersonaPrivacyTier;
  active: boolean;
  rootDir: string;
  loadedFiles: string[];
}

export interface PersonaSettingsOverride {
  personaId: string;
  flavorId: string | null;
}

export interface PersonaSettings {
  defaultPersonaId: string;
  defaultPrivacyTier: PersonaPrivacyTier;
  modelOverrides: Record<string, PersonaSettingsOverride>;
}

export interface PersonaContextPayload {
  personaId: string;
  personaFlavorId: string | null;
  personaPrivacyTier: PersonaPrivacyTier;
  prompt: string;
  loadedFiles: string[];
}

export interface PersonaFlavorDraft {
  displayName: string;
  identityMarkdown: string;
  soulMarkdown: string;
  notesMarkdown: string;
}

export interface WorkspaceIntelSummary {
  workspaceRoot: string;
  cacheStatus: 'cached' | 'fresh' | 'refreshed' | 'stale';
  languages: string[];
  packageManagers: string[];
  recommendedDefaultChecks: string[];
}

export interface WebExtractDocument {
  url: string;
  title: string;
  text: string;
  markdown: string;
  excerpt: string;
  wordCount: number;
}

export interface RuntimeContext {
  workspaceRoot: string;
  fileToolScope: 'workspace_home_visible_roaming';
  shellToolScope: 'cwd_default';
  shellAllowlist: string[];
  workspaceIntel?: WorkspaceIntelSummary | null;
  note: string;
}

export interface PublicMessagePayload {
  runId?: string | null;
  role?: string | null;
  content?: string | null;
  parts?: unknown[] | null;
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
  /** Present on reasoning_delta events: one chunk of inline thinking text. */
  text?: string | null;
  provider?: string | null;
  model?: string | null;
  capabilities?: Record<string, unknown> | null;
  toolExecution?: ToolExecution | null;
  toolCall?: Record<string, unknown> | null;
  turnState?: Record<string, unknown> | null;
  harnessDecision?: HarnessDecisionRecord | null;
  identityContext?: IdentityContextRuntime | null;
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

export interface SessionArtifactRecord {
  artifactId: string;
  sessionKey: string;
  runId: string;
  type: string;
  title: string;
  body: string;
  sourceAssetIds: string[];
  sourceArtifactIds: string[];
  createdAt: string;
  updatedAt: string;
  metadata: Record<string, unknown>;
}

export interface RunStep {
  callId?: string | null;
  toolId: string;
  ok: boolean;
  summary: string;
  error?: string | null;
  artifactId?: string | null;
  /** Primary call target — file path, search query, or URI. Backend contract: Codex to populate. */
  target?: string | null;
  workspaceRoot?: string | null;
  scope?: 'inside_workspace' | 'outside_workspace' | null;
  accessAction?: 'read' | 'write' | 'unknown' | null;
  policyDecision?: 'allowed' | 'read_roam' | 'write_blocked' | 'approval_required' | 'unsafe_unknown' | null;
  policySummary?: string | null;
  members?: ToolBatchMember[];
  turnId?: string | null;
  decisionId?: string | null;
  effect?: ToolEffect | null;
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
  starter_intent?: string | null;
  topical_tags?: string[];
  plan_snapshot: Record<string, unknown>;
  relevant_asset_ids: string[];
  relevant_artifact_ids: string[];
  merge_state?: Record<string, unknown>;
  pulse_state?: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface SessionMergeSource {
  sessionKey: string;
  title: string;
  status: 'pending' | 'running' | 'complete' | 'failed';
  summary: string | null;
  error: string | null;
  decisionCount: number;
  openQuestionCount: number;
}

export interface SessionMergeState {
  status: 'pending' | 'running' | 'complete' | 'failed';
  sourceSessionKeys: string[];
  totalSources: number;
  completedSources: number;
  startedAt: string;
  completedAt: string | null;
  briefRunId: string | null;
  briefArtifactId: string | null;
  conflicts: string[];
  sources: SessionMergeSource[];
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

export interface TelegramRuntimeDefaults {
  provider: string | null;
  model: string | null;
  systemPromptId: string | null;
  taskPromptId: string | null;
}

export interface TelegramSessionRoute {
  id: string;
  platform: string;
  chatId: string;
  threadId: string | null;
  sessionKey: string;
  titleOverride: string | null;
}

export interface MessagingConfig {
  telegram: TelegramBotConfig | null;
  destinations: MessageDestination[];
  approvalPolicy: MessagingApprovalPolicy;
  telegramDefaults: TelegramRuntimeDefaults | null;
  routes: TelegramSessionRoute[];
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
  | 'sent_message'
  | 'pulse';

export type PulseStatus = 'new' | 'saved' | 'dismissed';

export interface PulseRecord {
  pulseId: string;
  status: PulseStatus;
  title: string;
  summary: string;
  whyNow: string;
  sourceSessionKeys: string[];
  sourceRunIds: string[];
  sourceSessions: Array<{ sessionKey: string; title: string }>;
  createdAt: string;
  updatedAt: string;
  savedAt: string | null;
  dismissedAt: string | null;
}

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
  pulseData?: PulseRecord;
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

// ---------------------------------------------------------------------------
// Pat Profile — wire types
// Backend contract is documented in docs/investigations/pat-profile-frontend-contract.md
// These types are stubs until the backend RPC ships.
// ---------------------------------------------------------------------------

export type PatProfileSource = 'template' | 'explicit' | 'inferred' | 'session_observation';

export interface PatProfilePriority {
  id: string;
  label: string;
  weight: number;        // 0–1 relative weight among priorities
}

export interface PatProfileGoal {
  id: string;
  text: string;
  source: PatProfileSource;
  updatedAt: string;
}

export interface PatProfileTonePreference {
  directness: 'terse' | 'balanced' | 'verbose';
  formality: 'casual' | 'professional';
  preferBullets: boolean;
}

export interface PatProfile {
  profileId: string;
  displayName: string;
  active: boolean;
  source: PatProfileSource;
  priorities: PatProfilePriority[];
  goals: PatProfileGoal[];
  tonePreference: PatProfileTonePreference;
  noiseFilters: string[];         // topics/signals to suppress
  lastUpdatedAt: string;          // ISO
  changelogCount: number;         // total entries in the changelog
}

export interface IdentityContextPayload {
  stableIdentity: string | null;
  situationalBriefing: string | null;
}

export type MemoryCategory = 'preference' | 'project_convention' | 'ongoing_priority' | 'fact';

export interface MemoryItem {
  id: string;
  category: MemoryCategory;
  title: string;
  summary: string;
  detail?: string | null;
  tags: string[];
  source: string;
  confidence: number;
  createdAt: string;
  updatedAt: string;
  archived: boolean;
  lastSessionKey?: string | null;
}

export interface IdentityContextRuntime {
  profileActive: boolean;
  memoryCount: number;
  memoryItemIds: string[];
  personaActive?: boolean;
  personaId?: string | null;
  personaFlavorId?: string | null;
  personaPrivacyTier?: PersonaPrivacyTier | null;
}

export interface MemoryChangeEvent {
  item: MemoryItem;
  reason: string;
  sessionKey?: string | null;
  runId?: string | null;
}

export type ProfileChangelogChangeKind =
  | 'priority_updated'
  | 'goal_added'
  | 'goal_removed'
  | 'tone_updated'
  | 'noise_filter_added'
  | 'noise_filter_removed'
  | 'schedule_updated'
  | 'constraint_updated';

export interface ProfileChangelogItem {
  id: string;
  kind: ProfileChangelogChangeKind;
  summary: string;                         // one-line human-readable change description
  detail?: string | null;
  source: PatProfileSource;
  rationale?: string | null;               // why CopeNet made this change
  triggeredBySessionKey?: string | null;
  changedAt: string;                       // ISO
}

// Return Briefing — payload for the "I'm back" re-entry surface.
// Sections mirror the spec: attention now / did while away / watching / one thing noticed.
export interface BriefingAttentionItem {
  id: string;
  title: string;
  urgency: 'high' | 'medium' | 'low';
  source: string;           // e.g. "Agents · CopeNet Core session"
  detail?: string | null;
}

export interface BriefingActivityItem {
  id: string;
  summary: string;          // what CopeNet did
  sessionKey?: string | null;
  toolsUsed?: number;
  at: string;               // ISO
}

export interface BriefingWatchItem {
  id: string;
  label: string;
  signal: string;           // developing signal description
  source?: string | null;
}

export interface ReturnBriefingPayload {
  briefingId: string;
  generatedAt: string;                      // ISO
  attentionItems: BriefingAttentionItem[];  // Section 1: What needs your attention now
  activityItems: BriefingActivityItem[];   // Section 2: What CopeNet did while you were away
  watchItems: BriefingWatchItem[];          // Section 3: What it's watching
  noticeText: string | null;               // Section 4: One thing it noticed (personality slot)
  noticeSource?: string | null;
}

// ---------------------------------------------------------------------------
// Turn-level summary snapshot: extracted from turnState on final events.
// Mirrors the subset of TurnState.to_public_dict() we care about in the UI.
export interface TurnStateSnapshot {
  turnId?: string | null;
  decisionId?: string | null;
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
