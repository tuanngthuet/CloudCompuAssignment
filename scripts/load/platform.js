// C3 platform: 24 reads/s + 2 complete hold-confirm-cancel workflows/s = 30 requests/s.
import http from 'k6/http';
import { check, sleep } from 'k6';
import { SharedArray } from 'k6/data';
import { Counter, Rate, Trend } from 'k6/metrics';

const base = (__ENV.BASE_URL || '').replace(/\/$/, '');
const sid = __ENV.SESSION_ID;
if (!base || !sid || !__ENV.SESSIONS_FILE) throw Error('BASE_URL, SESSION_ID, SESSIONS_FILE required');
const identities = new SharedArray('private synthetic sessions', () => JSON.parse(open(__ENV.SESSIONS_FILE)));
if (identities.length < 100) throw Error('Platform requires 100 synthetic sessions');
const minimumExpiry = Date.now() + 20 * 60 * 1000;
const tokens = new Set();
const assignedSeats = new Set();
for (let i = 0; i < 100; i++) {
  const u = identities[i];
  if (!u || typeof u.session_token !== 'string' || !u.session_token ||
      typeof u.csrf_token !== 'string' || !u.csrf_token ||
      typeof u.seat_id !== 'string' || !u.seat_id || tokens.has(u.session_token)) {
    throw Error('First 100 sessions need distinct tokens, CSRF and assigned seats');
  }
  tokens.add(u.session_token);
  const expires = u.expires_at || __ENV.SESSION_EXPIRES_AT;
  if (typeof expires !== 'string' || !/(Z|[+-]\d{2}:\d{2})$/.test(expires) ||
      !Number.isFinite(Date.parse(expires)) || Date.parse(expires) < minimumExpiry) {
    throw Error('Sessions must cover the 15 minute load plus five minutes');
  }
  if (assignedSeats.has(u.seat_id)) throw Error('Assigned seats must be distinct across 100 VUs');
  assignedSeats.add(u.seat_id);
}

const failures = new Rate('platform_unexpected_failure');
const reads = new Trend('platform_read_ms');
const writes = new Trend('platform_write_ms');
const workflowsStarted = new Counter('platform_workflows_started');
const workflowsCompleted = new Counter('platform_workflows_completed');
const holds = new Counter('platform_holds_ok');
const confirms = new Counter('platform_confirms_ok');
const cancels = new Counter('platform_cancels_ok');
export const options = {
  scenarios: {
    reads: { executor: 'constant-arrival-rate', rate: 24, timeUnit: '1s', duration: '15m', preAllocatedVUs: 60, maxVUs: 60, exec: 'read' },
    writes: { executor: 'constant-arrival-rate', rate: 2, timeUnit: '1s', duration: '15m', preAllocatedVUs: 40, maxVUs: 40, exec: 'write' },
  },
  summaryTrendStats: ['avg', 'med', 'p(95)', 'p(99)', 'max'],
  thresholds: { platform_unexpected_failure: ['rate<0.01'], platform_read_ms: ['p(95)<500'], platform_write_ms: ['p(95)<1000'], dropped_iterations: ['count==0'] },
};

export function setup() {
  const r = http.get(base + '/lab-sessions', { tags: { operation_class: 'preflight', route: '/lab-sessions' } });
  if (r.status !== 200 || r.json().queue_policy.enabled) throw Error('Platform requires admission disabled');
  const listing = r.json();
  const selected = listing.items.find(x => x.id === sid);
  const serverTime = Date.parse(listing.server_time);
  const openAt = selected && Date.parse(selected.open_at);
  const closeAt = selected && Date.parse(selected.close_at);
  const startAt = selected && Date.parse(selected.start_at);
  if (!selected || ![serverTime, openAt, closeAt, startAt].every(Number.isFinite) ||
      openAt > serverTime || closeAt < serverTime + 16 * 60 * 1000 ||
      startAt < serverTime + 16 * 60 * 1000) {
    throw Error('Synthetic lab session must stay open and unstarted for the load window');
  }
  const seatsResponse = http.get(base + `/lab-sessions/${sid}/seats`, { tags: { operation_class: 'preflight', route: 'availability' } });
  if (seatsResponse.status !== 200) throw Error('Unable to verify assigned seats');
  const available = new Set(seatsResponse.json().items.filter(x => x.available).map(x => x.id));
  for (let i = 0; i < 100; i++) {
    if (!available.has(identities[i].seat_id)) throw Error('Some assigned seats are unavailable');
  }
  const seen = new Set();
  for (let i = 0; i < 100; i++) {
    http.cookieJar().set(base, 'labseat_session', identities[i].session_token);
    const me = http.get(base + '/me', { tags: { operation_class: 'preflight', route: '/me' } });
    if (me.status !== 200) throw Error('Prepared session failed /me');
    const user = me.json();
    if (!user.id || seen.has(user.id) || user.role !== 'student' ||
        user.account_status !== 'ACTIVE' || !user.email_verified) {
      throw Error('Prepared sessions must be 100 distinct active verified students');
    }
    seen.add(user.id);
    if (i < 99) sleep(0.1);
  }
}
function identity() {
  const u = identities[__VU - 1];
  if (!u) throw Error('No session assigned to this VU');
  http.cookieJar().set(base, 'labseat_session', u.session_token);
  http.cookieJar().set(base, 'labseat_csrf', u.csrf_token);
  return u;
}
function accepted(response, expected, write = false) {
  const ok = check(response, { 'Expected platform status': x => expected.includes(x.status) });
  failures.add(!ok);
  (write ? writes : reads).add(response.timings.duration);
  return ok;
}
function post(path, u, body, route) {
  return http.post(base + path, JSON.stringify(body), {
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': u.csrf_token },
    tags: { operation_class: 'platform', route },
  });
}
export function read() {
  identity();
  const path = __ITER % 2 ? '/events' : `/lab-sessions/${sid}/seats`;
  accepted(http.get(base + path, { tags: { operation_class: 'platform', route: path === '/events' ? '/events' : 'availability' } }), [200]);
}
export function write() {
  const u = identity();
  workflowsStarted.add(1);
  let response = post('/holds', u, { session_id: sid, seat_id: u.seat_id }, '/holds');
  if (!accepted(response, [200], true)) return;
  holds.add(1);
  const holdId = response.json().hold_id;
  if (!holdId) { failures.add(true); return; }
  response = post(`/holds/${holdId}/confirm`, u, {}, 'hold/confirm');
  if (!accepted(response, [200], true)) return;
  confirms.add(1);
  const reservationId = response.json().reservation_id;
  if (!reservationId) { failures.add(true); return; }
  response = post(`/reservations/${reservationId}/cancel`, u, {}, 'reservation/cancel');
  if (!accepted(response, [200], true)) return;
  cancels.add(1);
  workflowsCompleted.add(1);
}
