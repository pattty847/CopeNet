import type { Message, Session } from '../types/backend';

interface FormatConversationMarkdownArgs {
  session: Session;
  messages: Message[];
  providerLabel: string;
  modelLabel: string;
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

  const visibleMessages = messages.filter((message) => {
    if (message.role === 'system') return false;
    return message.content.trim().length > 0;
  });

  for (const message of visibleMessages) {
    sections.push('', `## ${formatRoleLabel(message.role)} — ${formatMessageTimestamp(message.timestamp)}`, message.content.trim());
  }

  return `${sections.join('\n')}\n`;
}
