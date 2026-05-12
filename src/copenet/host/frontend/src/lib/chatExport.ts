import type { Message, Session, SessionRunRecord } from '../types/backend';

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
    return message.content.trim().length > 0;
  });
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
    sections.push('', `## ${formatRoleLabel(message.role)} — ${formatMessageTimestamp(message.timestamp)}`, message.content.trim());
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
