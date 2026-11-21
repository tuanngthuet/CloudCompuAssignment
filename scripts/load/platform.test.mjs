import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import vm from 'node:vm';

const source = readFileSync(new URL('./platform.js', import.meta.url), 'utf8')
  .replace(/^import .*;\r?\n/gm, '')
  .replace('export const options =', 'const options =')
  .replace('export function setup()', 'function setup()')
  .replace('export function read()', 'function read()')
  .replace('export function write()', 'function write()')
  + '\nglobalThis.api = { setup, read, write, options };';
const expiry = new Date(Date.now() + 60 * 60 * 1000).toISOString();
const fixture = () => Array.from({ length: 100 }, (_, i) => ({
  session_token: `local-token-${i}`, csrf_token: `local-csrf-${i}`, seat_id: `seat-${i}`,
}));
function harness(data = fixture(), { queueEnabled = false, userId = token => token, capacity = 45 } = {}) {
  const calls = [];
  const cookies = {};
  const counts = {};
  const response = (status, value) => ({ status, json: () => value, timings: { duration: 1 } });
  const http = {
    cookieJar: () => ({ set: (_url, name, value) => { cookies[name] = value; } }),
    get: url => {
      calls.push({ method: 'GET', url });
      if (url.endsWith('/me')) return response(200, { id: userId(cookies.labseat_session), role: 'student', account_status: 'ACTIVE', email_verified: true });
      if (url.endsWith('/seats')) return response(200, { items: [...new Set(data.map(u => u.seat_id))].map(id => ({ id, available: true, capacity, remaining: capacity })) });
      if (url.endsWith('/lab-sessions')) return response(200, {
        queue_policy: { enabled: queueEnabled }, server_time: new Date().toISOString(),
        items: [{ id: 'session-1', open_at: new Date(Date.now() - 60000).toISOString(),
          close_at: new Date(Date.now() + 3600000).toISOString(), start_at: new Date(Date.now() + 3600000).toISOString() }],
      });
      return response(200, {});
    },
    post: (url, body, params) => {
      calls.push({ method: 'POST', url, body: JSON.parse(body), params });
      if (url.endsWith('/holds')) return response(200, { hold_id: 'hold-1' });
      if (url.endsWith('/confirm')) return response(200, { reservation_id: 'reservation-1' });
      return response(200, {});
    },
  };
  const context = vm.createContext({
    __ENV: { BASE_URL: 'https://local.example', SESSION_ID: 'session-1', SESSIONS_FILE: 'fixture.json', SESSION_EXPIRES_AT: expiry },
    __VU: 1, __ITER: 0, Date, JSON, Number, String, Set, Map, Error,
    http, check: (r, predicates) => Object.values(predicates).every(fn => fn(r)), sleep: () => {},
    SharedArray: class { constructor(_name, loader) { return loader(); } },
    Counter: class { constructor(name) { this.name = name; } add(value) { counts[this.name] = (counts[this.name] || 0) + value; } },
    Rate: class { add() {} }, Trend: class { add() {} }, open: () => JSON.stringify(data),
  });
  vm.runInContext(source, context);
  return { context, calls, cookies, counts };
}

test('platform keeps fixed arrival rates and completes hold-confirm-cancel using reservation ID', () => {
  const h = harness();
  h.context.api.setup();
  h.context.api.write();
  const scenarios = h.context.api.options.scenarios;
  assert.equal(scenarios.reads.rate, 24);
  assert.equal(scenarios.writes.rate, 2);
  assert.equal(scenarios.reads.executor, 'constant-arrival-rate');
  assert.ok(h.calls.some(c => c.url.endsWith('/reservations/reservation-1/cancel')));
  assert.equal(h.calls.find(c => c.url.endsWith('/holds')).params.headers['X-CSRF-Token'], 'local-csrf-0');
  assert.equal(h.cookies.labseat_csrf, 'local-csrf-0');
  assert.equal(h.counts.platform_workflows_completed, 1);
  assert.equal(h.calls.filter(c => c.url.endsWith('/me')).length, 100);
});
test('platform rejects queue enabled before load', () => {
  const h = harness(fixture(), { queueEnabled: true });
  assert.throws(() => h.context.api.setup(), /admission disabled/);
});
test('platform accepts distinct users sharing four rooms within capacity', () => {
  const data = fixture().map((u,i) => ({ ...u, seat_id: `room-${i%4}` }));
  harness(data).context.api.setup();
  const insufficient = harness(data, { capacity: 17 });
  assert.throws(() => insufficient.context.api.setup(), /exceed the remaining capacity/);
});
test('platform rejects duplicate CSRF tokens', () => {
  const data=fixture();data[1].csrf_token=data[0].csrf_token;
  assert.throws(() => harness(data), /distinct tokens, CSRF/);
});
test('platform rejects two sessions belonging to one user', () => {
  const h = harness(fixture(), { userId: () => 'same-user' });
  assert.throws(() => h.context.api.setup(), /100 distinct/);
});
