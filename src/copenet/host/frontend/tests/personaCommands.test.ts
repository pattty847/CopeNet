import assert from 'node:assert/strict';
import test from 'node:test';

import { buildPersonaCommandHelpText, parsePersonaSlashCommand } from '../src/lib/personaCommands';

test('parsePersonaSlashCommand resolves supported persona commands', () => {
  assert.deepEqual(parsePersonaSlashCommand('/persona'), { kind: 'summary' });
  assert.deepEqual(parsePersonaSlashCommand('/persona files'), { kind: 'files' });
  assert.deepEqual(parsePersonaSlashCommand('/persona onboard'), { kind: 'onboard' });
  assert.deepEqual(parsePersonaSlashCommand('/persona onboard this model'), { kind: 'onboard' });
  assert.deepEqual(parsePersonaSlashCommand('/persona privacy safe'), { kind: 'privacy', privacyTier: 'safe' });
});

test('parsePersonaSlashCommand returns help for malformed persona commands', () => {
  assert.deepEqual(parsePersonaSlashCommand('/persona privacy weird'), { kind: 'help' });
  assert.deepEqual(parsePersonaSlashCommand('/persona mystery'), { kind: 'help' });
  assert.equal(parsePersonaSlashCommand('hello there'), null);
});

test('buildPersonaCommandHelpText documents the supported commands', () => {
  const help = buildPersonaCommandHelpText();

  assert.match(help, /\/persona onboard this model/);
  assert.match(help, /\/persona privacy safe/);
  assert.match(help, /Persona Home commands/i);
});
