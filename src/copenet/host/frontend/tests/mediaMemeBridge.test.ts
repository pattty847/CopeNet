import assert from 'node:assert/strict';
import test from 'node:test';

import { buildAttachedMedia, buildMediaTranscriptPack } from '../src/lib/mediaMemeBridge';

test('buildMediaTranscriptPack compresses transcript into a summary and key lines', () => {
  const pack = buildMediaTranscriptPack({
    assetId: 'media-1',
    appId: 'app',
    sourceType: 'url',
    sourceUrl: 'https://example.com/video',
    sourcePath: null,
    title: 'Gym authority clip',
    mediaPath: null,
    transcriptPath: null,
    transcriptSource: 'youtube-captions',
    transcriptExcerpt: 'After three weeks of discipline he is talking like a human worth auditor.',
    metadata: {},
    durationSeconds: 12,
    latencyMs: 30,
    createdAt: '2026-04-20T00:00:00Z',
    updatedAt: '2026-04-20T00:00:00Z',
    transcriptContent: 'After three weeks of discipline he is talking like a human worth auditor.\nYou need routines.\nPeople are spiritually unemployed.',
  });

  assert.match(pack.summary || '', /Gym authority clip/);
  assert.deepEqual(pack.keyLines.slice(0, 2), [
    'After three weeks of discipline he is talking like a human worth auditor.',
    'You need routines.',
  ]);
});

test('buildAttachedMedia keeps transcript pack ready for meme workflows', () => {
  const attached = buildAttachedMedia({
    assetId: 'media-1',
    appId: 'app',
    sourceType: 'url',
    sourceUrl: 'https://example.com/video',
    sourcePath: null,
    title: 'Gym authority clip',
    mediaPath: null,
    transcriptPath: null,
    transcriptSource: 'whisper',
    transcriptExcerpt: 'People are spiritually unemployed.',
    metadata: {},
    durationSeconds: 12,
    latencyMs: 30,
    createdAt: '2026-04-20T00:00:00Z',
    updatedAt: '2026-04-20T00:00:00Z',
    transcriptContent: 'People are spiritually unemployed.',
  });

  assert.equal(attached.assetId, 'media-1');
  assert.equal(attached.transcriptPack.keyLines[0], 'People are spiritually unemployed.');
});
