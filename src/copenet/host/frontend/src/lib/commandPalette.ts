export type CommandPaletteInteraction = 'idle' | 'keyboard' | 'mouse' | 'query';

export function shouldAutoScrollCommandPalette(args: {
  query: string;
  interaction: CommandPaletteInteraction;
}): boolean {
  const normalizedQuery = args.query.trim();
  if (args.interaction === 'keyboard' || args.interaction === 'mouse') return true;
  if (args.interaction === 'query' && normalizedQuery.length > 0) return true;
  return false;
}
