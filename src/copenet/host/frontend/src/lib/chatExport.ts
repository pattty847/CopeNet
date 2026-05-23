import type { Message, MessagePart, Session, SessionRunRecord, ToolResultPreview } from '../types/backend';

interface FormatConversationMarkdownArgs {
  session: Session;
  messages: Message[];
  providerLabel: string;
  modelLabel: string;
}

interface FormatConversationWithToolActivityMarkdownArgs extends FormatConversationMarkdownArgs {
  runs: SessionRunRecord[];
}

function formatMessageTimestamp(timestamp: string): string {
  const parsed = new Date(timestamp);
  if (Number.isNaN(parsed.getTime())) {
    return timestamp;
  }
  return parsed.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
}

function formatRoleLabel(role: Message['role']): string {
  return role === 'user' ? 'User' : role === 'assistant' ? 'Assistant' : 'System';
}

function visibleMessages(messages: Message[]): Message[] {
  return messages.filter((message) => {
    if (message.role === 'system') return false;
    return message.content.trim().length > 0 || !!message.parts?.length || !!message.toolExecution;
  });
}

function formatToolPreview(preview: ToolResultPreview | null | undefined): string[] {
  if (!preview) return [];
  if (preview.type === 'file_read') {
    return [`  - Preview: \`${preview.path}\``, ...preview.lines.slice(0, 8).map((line) => `    ${line}`)];
  }
  if (preview.type === 'repo_search') {
    return [
      `  - Preview: ${preview.query}`,
      ...preview.matches.slice(0, 8).map((match) => `    ${match.path}:${match.line}: ${match.snippet}`),
    ];
  }
  return preview.text.trim() ? [`  - Preview: ${preview.text.trim()}`] : [];
}

function formatMessagePartLines(part: MessagePart): string[] {
  if (part.kind === 'text') {
    return part.content.trim() ? [part.content.trim()] : [];
  }
  if (part.kind === 'thinking') {
    return part.text.trim() ? [`[thinking] ${part.text.trim()}`] : [];
  }
  if (part.kind === 'tool_call') {
    const target = part.target || part.hint;
    return [`[tool call] ${part.toolId}${target ? ` — ${target}` : ''}`];
  }
  if (part.kind === 'tool_result') {
    const lines = [`[tool result] ${part.toolId} — ${part.ok ? 'ok' : 'failed'} — ${part.summary}`];
    if (part.target) lines.push(`  - Target: \`${part.target}\``);
    if (part.error) lines.push(`  - Error: ${part.error}`);
    else if (part.policySummary) lines.push(`  - Policy: ${part.policySummary}`);
    lines.push(...formatToolPreview(part.preview));
    return lines;
  }
  const lines = [`[tool batch] ${part.label} — ${part.ok ? 'ok' : 'failed'}`];
  for (const member of part.members) {
    lines.push(`  - ${member.toolId} — ${member.ok ? 'ok' : 'failed'} — ${member.summary}`);
    if (member.target) lines.push(`    - Target: \`${member.target}\``);
    if (member.error) lines.push(`    - Error: ${member.error}`);
  }
  return lines;
}

export function formatMessageForClipboard(message: Message): string {
  if (message.parts?.length) {
    return message.parts.flatMap(formatMessagePartLines).filter(Boolean).join('\n\n').trim();
  }
  const lines = [message.content.trim()].filter(Boolean);
  if (message.toolExecution) {
    lines.push(
      `[tool result] ${message.toolExecution.toolId} — ${message.toolExecution.ok ? 'ok' : 'failed'} — ${message.toolExecution.summary}`
    );
    if (message.toolExecution.target) lines.push(`  - Target: \`${message.toolExecution.target}\``);
    if (message.toolExecution.error) lines.push(`  - Error: ${message.toolExecution.error}`);
    else if (message.toolExecution.policySummary) lines.push(`  - Policy: ${message.toolExecution.policySummary}`);
  }
  return lines.join('\n\n').trim();
}

function formatToolStepLines(run: SessionRunRecord): string[] {
  const lines: string[] = [];
  for (const step of run.toolSteps) {
    const members = Array.isArray(step.members) ? step.members : [];
    if (step.toolId === 'tool.batch' && members.length > 0) {
      for (const member of members) {
        lines.push(`- \`${member.toolId}\` — ${member.summary}`);
        if (member.target) lines.push(`  - Target: \`${member.target}\``);
        if (member.error) lines.push(`  - Error: ${member.error}`);
        else if (member.policySummary) lines.push(`  - Policy: ${member.policySummary}`);
      }
      continue;
    }
    lines.push(`- \`${step.toolId}\` — ${step.summary}`);
    if (step.target) lines.push(`  - Target: \`${step.target}\``);
    if (step.error) lines.push(`  - Error: ${step.error}`);
    else if (step.policySummary) lines.push(`  - Policy: ${step.policySummary}`);
  }
  if (run.outputSummary?.trim()) {
    lines.push(`- Output summary: ${run.outputSummary.trim()}`);
  }
  return lines;
}

export function formatConversationMarkdown({
  session,
  messages,
  providerLabel,
  modelLabel,
}: FormatConversationMarkdownArgs): string {
  const sections: string[] = [
    '# CopeNet Chat Export',
    `Session: ${session.title?.trim() || session.key}`,
    `Provider: ${providerLabel}`,
    `Model: ${modelLabel || session.model || 'default'}`,
  ];

  for (const message of visibleMessages(messages)) {
    sections.push('', `## ${formatRoleLabel(message.role)} — ${formatMessageTimestamp(message.timestamp)}`, formatMessageForClipboard(message));
  }

  return `${sections.join('\n')}\n`;
}

export function formatConversationWithToolActivityMarkdown({
  session,
  messages,
  runs,
  providerLabel,
  modelLabel,
}: FormatConversationWithToolActivityMarkdownArgs): string {
  const base = formatConversationMarkdown({ session, messages, providerLabel, modelLabel }).trimEnd();
  const lines: string[] = [base, '', '# Tool Activity'];
  const orderedRuns = [...runs].sort((a, b) => String(a.startedAt || '').localeCompare(String(b.startedAt || '')));

  if (orderedRuns.length === 0) {
    lines.push('', 'No tool activity captured for this session.');
    return `${lines.join('\n')}\n`;
  }

  for (const run of orderedRuns) {
    lines.push('', `## Run — ${formatMessageTimestamp(run.startedAt)}`);
    if (run.userMessage?.trim()) {
      lines.push(`Prompt: ${run.userMessage.trim()}`);
    }
    const stepLines = formatToolStepLines(run);
    if (stepLines.length > 0) {
      lines.push('', ...stepLines);
    } else {
      lines.push('', 'No tool steps recorded.');
    }
  }

  return `${lines.join('\n')}\n`;
}
