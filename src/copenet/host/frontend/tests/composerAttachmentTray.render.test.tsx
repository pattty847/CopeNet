import assert from 'node:assert/strict';
import test from 'node:test';
import { renderToStaticMarkup } from 'react-dom/server';
import {
  ComposerAttachmentTray,
  DISCUSS_PROMPTS,
  DiscussPromptChips,
  isTextAttachment,
  type PendingAttachment,
} from '../src/components/agents/ComposerAttachmentTray';

const transcript: PendingAttachment = {
  localId: 'att-t',
  filename: 'Sleep Myths.txt',
  previewUrl: '',
  status: 'ready',
  attachment: { attachmentId: 't', mimeType: 'text/plain', filename: 'Sleep Myths.txt' },
};
const image: PendingAttachment = {
  localId: 'att-i',
  filename: 'chart.png',
  previewUrl: 'blob:chart',
  status: 'ready',
  attachment: { attachmentId: 'i', mimeType: 'image/png', filename: 'chart.png' },
};

test('A discussed transcript shows as a named file chip, never as a broken image', () => {
  const html = renderToStaticMarkup(<ComposerAttachmentTray attachments={[transcript, image]} onRemove={() => undefined} />);
  assert.match(html, /Sleep Myths\.txt/);
  assert.equal((html.match(/<img /g) || []).length, 1);
  assert.match(html, /src="blob:chart"/);
});

test('Only text attachments count as transcripts', () => {
  assert.equal(isTextAttachment(transcript.attachment), true);
  assert.equal(isTextAttachment(image.attachment), false);
  assert.equal(isTextAttachment(null), false);
});

test('Discuss prompt chips offer the learning openers', () => {
  const html = renderToStaticMarkup(<DiscussPromptChips onPick={() => undefined} />);
  for (const item of DISCUSS_PROMPTS) assert.ok(html.includes(`>${item.label}<`), item.label);
  assert.match(html, /Check the claims/);
});
