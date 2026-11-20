import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import vm from 'node:vm';

const source = readFileSync(new URL('./booking.js', import.meta.url), 'utf8')
  .replace(/^import .*;\r?\n/gm, '')
  .replace('export const options =', 'const options =')
  .replace('export function setup()', 'function setup()')
  .replace('export default function ()', 'function run()')
  + '\nglobalThis.run = run; globalThis.setup = setup; globalThis.options = options;';

function harness(environment, fixtures, userIdForToken = token => `user-for-${token}`, queueEnabled = false, holdResponse = null) {
  const calls = [];
  const counters = {};
  const cookies = {};
  const response = (status, data) => ({ status, json: () => data });
  const http = {
    cookieJar: () => ({
      set: (_url, name, value) => { cookies[name] = value; },
      cookiesForURL: () => Object.fromEntries(Object.entries(cookies).map(([k, v]) => [k, [v]])),
    }),
    get: (url) => {
      calls.push({ method: 'GET', url });
      if (url.endsWith('/me')) return response(200, { id: userIdForToken(cookies.labseat_session),
        role: 'student', account_status: 'ACTIVE', email_verified: true });
      if (url.endsWith('/lab-sessions')) return response(200, { queue_policy: { enabled: queueEnabled } });
      if (url.endsWith('/seats')) return response(200, { items: [{ id: 'seat-1', available: true }] });
      return response(200, {});
    },
    post: (url, body, params) => {
      calls.push({ method: 'POST', url, body: JSON.parse(body), params });
      if (url.endsWith('/auth/login')) return response(200, {});
      if (url.endsWith('/queue/join')) return response(200, { status: 'ADMITTED', admission_expires_at: new Date(Date.now() + 60000).toISOString() });
      if (url.endsWith('/holds')) return holdResponse || response(200, { hold_id: 'hold-1' });
      if (url.endsWith('/confirm')) return response(200, { reservation_id: 'reservation-1' });
      return response(200, {});
    },
  };
  const context = vm.createContext({
    __ENV: environment, __VU: 1, Date, JSON, Number, Boolean, String, Set, Error,
    http, check: (r, checks) => Object.values(checks).every(fn => fn(r)), sleep: () => {},
    SharedArray: class { constructor(_name, loader) { return loader(); } },
    Counter: class { constructor(name) { this.name = name; } add(value) { counters[this.name] = (counters[this.name] || 0) + value; } }, Trend: class { add() {} },
    open: path => JSON.stringify(fixtures[path]),
  });
  vm.runInContext(source, context);
  return { context, calls, cookies, counters };
}

const base = { BASE_URL: 'https://labseat.example', SESSION_ID: 'session-1', VUS: '1', DURATION: '5m' };
const fixture = { session_token: 'private-test-token', csrf_token: 'private-test-csrf', seat_id: 'seat-1' };

test('prepared session uses its cookie, CSRF and assigned seat without login', () => {
  const h = harness({ ...base, SESSIONS_FILE: 'sessions.json',
    SESSION_EXPIRES_AT: new Date(Date.now() + 3600000).toISOString() }, { 'sessions.json': [fixture] });
  h.context.setup();
  h.context.run();
  assert.equal(h.cookies.labseat_session, fixture.session_token);
  assert.equal(h.cookies.labseat_csrf, fixture.csrf_token);
  assert.ok(h.calls.some(c => c.url.endsWith('/me')));
  assert.ok(!h.calls.some(c => c.url.endsWith('/auth/login')));
  const hold = h.calls.find(c => c.url.endsWith('/holds'));
  assert.equal(hold.body.seat_id, fixture.seat_id);
  assert.equal(hold.params.headers['X-CSRF-Token'], fixture.csrf_token);
  assert.ok(h.calls.some(c => c.url.endsWith('/reservations/reservation-1/cancel')));
});

test('credentials mode still logs in when no session file is supplied', () => {
  const h = harness({ ...base, ACCOUNTS_FILE: 'accounts.json' },
    { 'accounts.json': [{ username: 'synthetic-1', password: 'local-only' }] });
  h.cookies.labseat_pre_csrf = 'pre-csrf';
  h.cookies.labseat_csrf = 'post-csrf';
  h.context.run();
  assert.ok(h.calls.some(c => c.url.endsWith('/auth/login')));
  assert.equal(h.calls.find(c => c.url.endsWith('/auth/login')).params.headers['X-CSRF-Token'], 'pre-csrf');
  assert.equal(h.calls.find(c => c.url.endsWith('/holds')).params.headers['X-CSRF-Token'], 'post-csrf');
});

test('credentials mode rejects repeated accounts across VUs', () => {
  assert.throws(() => harness({ ...base, VUS: '2', ACCOUNTS_FILE: 'accounts.json' },
    { 'accounts.json': [{ username: 'synthetic-1', password: 'local-only' },
      { username: 'synthetic-1', password: 'local-only' }] }), /distinct account/);
});

test('prepared session rejects expired fixture before making requests', () => {
  assert.throws(() => harness({ ...base, SESSIONS_FILE: 'sessions.json',
    SESSION_EXPIRES_AT: new Date(Date.now() + 60000).toISOString() }, { 'sessions.json': [fixture] }),
  /expiry covering duration/);
});

test('prepared session rejects duplicate tokens across VUs', () => {
  assert.throws(() => harness({ ...base, VUS: '2', SESSIONS_FILE: 'sessions.json',
    SESSION_EXPIRES_AT: new Date(Date.now() + 3600000).toISOString() },
  { 'sessions.json': [fixture, { ...fixture }] }), /must be distinct/);
});

test('setup checks distinct users behind distinct tokens', () => {
  const h = harness({ ...base, VUS: '2', SESSIONS_FILE: 'sessions.json',
    SESSION_EXPIRES_AT: new Date(Date.now() + 3600000).toISOString() },
  { 'sessions.json': [fixture, { ...fixture, session_token: 'other-token' }] });
  h.context.setup();
  assert.equal(h.calls.filter(c => c.url.endsWith('/me')).length, 2);
});

test('setup rejects two sessions belonging to one user', () => {
  const h = harness({ ...base, VUS: '2', SESSIONS_FILE: 'sessions.json',
    SESSION_EXPIRES_AT: new Date(Date.now() + 3600000).toISOString() },
  { 'sessions.json': [fixture, { ...fixture, session_token: 'other-token' }] }, () => 'same-user');
  assert.throws(() => h.context.setup(), /distinct active verified students/);
});

test('admission mode refuses queue disabled before load', () => {
  const h = harness({ ...base, SESSIONS_FILE: 'sessions.json', REQUIRE_QUEUE_ENABLED: '1',
    SESSION_EXPIRES_AT: new Date(Date.now() + 3600000).toISOString() }, { 'sessions.json': [fixture] });
  assert.throws(() => h.context.setup(), /queue enabled/);
});

test('admission records expected sold-out separately from unexpected conflict and rate limit', () => {
  const config = { ...base, SESSIONS_FILE: 'sessions.json',
    SESSION_EXPIRES_AT: new Date(Date.now() + 3600000).toISOString() };
  for (const [status, code, metric] of [[409, 'sold_out', 'booking_seat_conflict'],
    [409, 'active_registration', 'booking_unexpected_conflict'],
    [429, 'rate_limited', 'booking_rate_limited']]) {
    const h = harness(config, { 'sessions.json': [fixture] }, undefined, true,
      { status, json: () => ({ code }) });
    h.context.setup();
    h.context.run();
    assert.equal(h.counters[metric], 1);
    assert.equal(h.counters.booking_unexpected_error || 0, code === 'sold_out' ? 0 : 1);
  }
});
