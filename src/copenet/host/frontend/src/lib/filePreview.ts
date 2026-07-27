/**
 * Convert preview payload entries into physical source lines.
 *
 * Historical and provider-normalized payloads can contain embedded newlines
 * inside one array entry. Rendering those entries as one row makes the code
 * occupy multiple visual lines while the gutter advances only once.
 */
export function physicalFilePreviewLines(raw: unknown, maxLines = Number.POSITIVE_INFINITY): string[] {
  if (raw == null) return [];
  const entries = Array.isArray(raw) ? raw : [raw];
  const lines = entries.flatMap((entry) => String(entry ?? '').replace(/\r\n?/g, '\n').split('\n'));
  return lines.slice(0, maxLines);
}
