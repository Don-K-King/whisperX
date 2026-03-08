import test from 'node:test';
import assert from 'node:assert/strict';
import { parseToken, sanitizedError } from '../utils.js';

test('parseToken extracts tenant and roles', () => {
  const payload = Buffer.from(JSON.stringify({ tenant_id: 't-1', roles: ['admin'] })).toString('base64');
  const auth = parseToken(`h.${payload}.s`);
  assert.equal(auth.tenant_id, 't-1');
  assert.deepEqual(auth.roles, ['admin']);
});

test('sanitizedError hides details and keeps correlation id', () => {
  assert.equal(sanitizedError({ error_code: 'auth.invalid', correlation_id: 'corr-1', detail: 'secret' }), 'auth.invalid (corr-1)');
});
