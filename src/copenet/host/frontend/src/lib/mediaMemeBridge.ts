import type { MediaAssetDetail } from '../types/backend';
import type { MemeAttachedMedia, MemeBrief, MemeCandidate, MemeGeneration, MediaTranscriptPack } from '../workflows/meme/types';

function compactText(value: string): string {
  return value.replace(/\s+/g, ' ').trim();
}

function uniqueLines(lines: string[], limit: number): string[] {
  const seen = new Set<string>();
  const picked: string[] = [];
  for (const line of lines) {
    const clean = compactText(line);
    if (!clean) continue;
    const key = clean.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    picked.push(clean);
    if (picked.length >= limit) break;
  }
  return picked;
}

export function buildMediaTranscriptPack(detail: MediaAssetDetail): MediaTranscriptPack {
  const transcript = detail.transcriptContent || '';
  const rawLines = transcript
    .split(/\r?\n+/)
    .map((line) => line.replace(/^[-*]\s*/, '').trim())
    .filter(Boolean);
  const keyLines = uniqueLines(rawLines.length ? rawLines : compactText(transcript).split(/[.!?]\s+/), 3);
  const notableQuotes = uniqueLines(
    keyLines.filter((line) => line.split(/\s+/).length >= 2),
    2,
  );
  const summarySource = keyLines.slice(0, 2).join(' ').trim() || compactText(detail.transcriptExcerpt || detail.title);
  const summary = detail.title && !summarySource.toLowerCase().includes(detail.title.toLowerCase())
    ? `${detail.title}: ${summarySource}`
    : summarySource;
  const toneCues: string[] = [];
  const lowered = compactText(transcript).toLowerCase();
  if (transcript.includes('?')) toneCues.push('interrogative');
  if (/(listen|bro|dude|man)\b/.test(lowered)) toneCues.push('spoken');
  if (/(lock in|discipline|routine|mindset)\b/.test(lowered)) toneCues.push('motivational');
  return {
    summary: summary || detail.title,
    keyLines: keyLines.length ? keyLines : [detail.transcriptExcerpt || detail.title],
    notableQuotes: notableQuotes.length ? notableQuotes : (keyLines[0] ? [keyLines[0]] : []),
    transcriptSource: detail.transcriptSource,
    transcriptExcerpt: detail.transcriptExcerpt || null,
    toneCues,
  };
}

export function buildAttachedMedia(detail: MediaAssetDetail): MemeAttachedMedia {
  return {
    assetId: detail.assetId,
    title: detail.title,
    sourceUrl: detail.sourceUrl,
    transcriptSource: detail.transcriptSource,
    transcriptExcerpt: detail.transcriptExcerpt,
    transcriptPack: buildMediaTranscriptPack(detail),
  };
}

export function buildMemeAgentsDraftSeed(args: {
  attachedMedia: MemeAttachedMedia;
  brief?: MemeBrief | null;
  generation?: MemeGeneration | null;
}): string {
  const { attachedMedia, brief, generation } = args;
  const lines = [
    `Use the media asset "${attachedMedia.title}" to iterate on meme captions, overlays, and post angles.`,
    '',
    `Source URL: ${attachedMedia.sourceUrl || 'Unknown'}`,
    `Transcript source: ${attachedMedia.transcriptSource || 'transcript'}`,
    `Transcript summary: ${attachedMedia.transcriptPack.summary || attachedMedia.transcriptExcerpt}`,
  ];
  if (attachedMedia.transcriptPack.keyLines.length) {
    lines.push('', 'Key lines:');
    for (const line of attachedMedia.transcriptPack.keyLines) lines.push(`- ${line}`);
  }
  if (brief) {
    lines.push('', 'Current meme brief:');
    if (brief.topic.trim()) lines.push(`- Topic: ${brief.topic.trim()}`);
    if (brief.trendSummary.trim()) lines.push(`- Trend summary: ${brief.trendSummary.trim()}`);
    if (brief.imageSpringboard.trim()) lines.push(`- Image springboard: ${brief.imageSpringboard.trim()}`);
    if (brief.toneHints.length) lines.push(`- Tone hints: ${brief.toneHints.join(', ')}`);
  }
  if (generation?.candidates.length) {
    lines.push('', 'Current top meme candidates:');
    for (const candidate of generation.candidates.slice(0, 4)) {
      lines.push(`- ${candidate.direction}: ${candidate.text}`);
    }
  }
  lines.push(
    '',
    'Please iterate on captions and angles for this post. Favor juxtaposition, artifact shells, transcript-aware humor, and sharper discovered-sentence energy.',
  );
  return lines.join('\n');
}

export function summarizeCandidates(candidates: MemeCandidate[]): string {
  return candidates.slice(0, 4).map((candidate) => `${candidate.direction}: ${candidate.text}`).join(' | ');
}
