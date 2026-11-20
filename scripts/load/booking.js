import http from 'k6/http';
import { check, sleep } from 'k6';
import { SharedArray } from 'k6/data';
import { Counter, Trend } from 'k6/metrics';

const base = (__ENV.BASE_URL || '').replace(/\/$/, '');
const session = __ENV.SESSION_ID;
const sessionMode = Boolean(__ENV.SESSIONS_FILE);
if (!base || !session || !(sessionMode || __ENV.ACCOUNTS_FILE)) {
  throw new Error('BASE_URL, SESSION_ID and SESSIONS_FILE or ACCOUNTS_FILE are required');
}
const vus = Number(__ENV.VUS || 20);
if (!Number.isInteger(vus) || vus < 1) throw new Error('VUS must be a positive integer');
const duration = __ENV.DURATION || '5m';
const durationMatch = /^(\d+)(s|m|h)$/.exec(duration);
if (!durationMatch || Number(durationMatch[1]) < 1) throw new Error('DURATION must be positive: Ns, Nm or Nh');
const durationMs = Number(durationMatch[1]) * { s: 1000, m: 60000, h: 3600000 }[durationMatch[2]];
const users = sessionMode ? null : new SharedArray('private test accounts', () => JSON.parse(open(__ENV.ACCOUNTS_FILE)));
const identities = sessionMode ? new SharedArray('private synthetic sessions', () => JSON.parse(open(__ENV.SESSIONS_FILE))) : null;
if (sessionMode) {
  if (identities.length < vus) throw new Error('Each VU needs a separate synthetic session');
  const tokens = new Set();
  const minimumExpiry = Date.now() + durationMs + 300000;
  for (let i = 0; i < vus; i++) {
    const item = identities[i];
    if (!item || typeof item.session_token !== 'string' || !item.session_token ||
        typeof item.csrf_token !== 'string' || !item.csrf_token ||
        typeof item.seat_id !== 'string' || !item.seat_id) {
      throw new Error('Session fixture needs session_token, csrf_token and seat_id for every VU');
    }
    if (tokens.has(item.session_token)) throw new Error('Session tokens must be distinct across VUs');
    tokens.add(item.session_token);
    const expiry = item.expires_at || __ENV.SESSION_EXPIRES_AT;
    if (typeof expiry !== 'string' || !/(Z|[+-]\d{2}:\d{2})$/.test(expiry) ||
        !Number.isFinite(Date.parse(expiry)) || Date.parse(expiry) < minimumExpiry) {
      throw new Error('Every session must have timezone-aware expiry covering duration plus five minutes');
    }
  }
} else if (!users || users.length < vus) {
  throw new Error('Each VU needs a distinct account');
} else {
  const names = new Set();
  for (let i = 0; i < vus; i++) {
    const account = users[i];
    if (!account || typeof account.username !== 'string' || !account.username ||
        typeof account.password !== 'string' || !account.password || names.has(account.username)) {
      throw new Error('Each VU needs a distinct account with username and password');
    }
    names.add(account.username);
  }
}
export const options = {
  noCookiesReset: true,
  summaryTrendStats: ['avg', 'med', 'p(95)', 'p(99)', 'max'],
  vus, duration,
  thresholds: { checks: ['rate>0.99'] },
};
const admissions = new Counter('booking_admitted');
const waitingPolls = new Counter('booking_waiting_poll');
const conflicts = new Counter('booking_seat_conflict');
const errors = new Counter('booking_unexpected_error');
const queueWait = new Trend('booking_queue_wait_ms');
let loggedIn = false;
let joinedAt = 0;
let seenAdmission = false;

export function setup() {
  if (!sessionMode) return;
  const seenUsers = new Set();
  for (let i = 0; i < vus; i++) {
    http.cookieJar().set(base, 'labseat_session', identities[i].session_token);
    const response = http.get(base + '/me', {
      tags: { operation_class: 'preflight', route: '/me' },
    });
    if (response.status !== 200) throw new Error('Prepared session failed /me preflight');
    const user = response.json();
    if (!user.id || seenUsers.has(user.id) || user.role !== 'student' ||
        user.account_status !== 'ACTIVE' || !user.email_verified) {
      throw new Error('Prepared sessions must belong to distinct active verified students');
    }
    seenUsers.add(user.id);
    if (i + 1 < vus) sleep(0.1);
  }
}

function cookie(name) {
  const values = http.cookieJar().cookiesForURL(base + '/')[name];
  return values && values[0];
}
function post(path, body, route) {
  return http.post(base + path, JSON.stringify(body), {
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': cookie('labseat_csrf') || '' },
    tags: { operation_class: 'booking', route },
  });
}
function valid(response, codes) {
  const ok = check(response, { 'Expected Booking response': r => codes.includes(r.status) });
  if (!ok) errors.add(1);
  return ok;
}
export default function () {
  if (!loggedIn) {
    if (sessionMode) {
      const identity = identities[__VU - 1];
      http.cookieJar().set(base, 'labseat_session', identity.session_token);
      http.cookieJar().set(base, 'labseat_csrf', identity.csrf_token);
      const me = http.get(base + '/me', { tags: { operation_class: 'booking', route: '/me' } });
      if (!valid(me, [200])) { sleep(5); return; }
      const account = me.json();
      if (account.role !== 'student' || account.account_status !== 'ACTIVE' || !account.email_verified) {
        errors.add(1); sleep(5); return;
      }
    } else {
      http.get(base + '/', { tags: { operation_class: 'catalogue', route: '/'  } });
      const response = http.post(base + '/auth/login', JSON.stringify(users[__VU - 1]), {
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': cookie('labseat_pre_csrf') || '' },
        tags: { operation_class: 'catalogue', route: '/auth/login' },
      });
      if (!valid(response, [200])) { sleep(5); return; }
    }
    loggedIn = true;
  }
  const root = `/lab-sessions/${session}/queue`;
  let response;
  if (!joinedAt) {
    response = post(root + '/join', {}, 'queue/join');
    joinedAt = Date.now();
  } else response = post(root + '/heartbeat', {}, 'queue/heartbeat');
  if (!valid(response, [200])) { joinedAt = 0; sleep(5); return; }
  const state = response.json();
  if (state.status === 'WAITING') { waitingPolls.add(1); sleep(5); return; }
  if (!['ADMITTED', 'DISABLED'].includes(state.status)) { joinedAt = 0; seenAdmission = false; sleep(5); return; }
  if (state.status==='ADMITTED' && !seenAdmission) { admissions.add(1); queueWait.add(Date.now() - joinedAt); seenAdmission = true; }
  // Do not extend the admission lease; honour the server's deadline.
  if (state.status==='ADMITTED' && Date.parse(state.admission_expires_at) <= Date.now()) { joinedAt = 0; seenAdmission = false; return; }
  response = http.get(base + `/lab-sessions/${session}/seats`, { tags: { operation_class: 'booking', route: 'availability' } });
  if (!valid(response, [200])) { sleep(5); return; }
  const available = response.json().items.filter(s => s.available);
  const seat = sessionMode ? available.find(s => s.id === identities[__VU - 1].seat_id)
                           : available[(__VU - 1) % available.length];
  if (!seat) {
    if (sessionMode) errors.add(1);
    post(root + '/leave', {}, 'queue/leave'); joinedAt = 0; seenAdmission = false; sleep(5); return;
  }
  response = post('/holds', { session_id: session, seat_id: seat.id }, '/holds');
  if (!valid(response, [200, 409])) { sleep(5); return; }
  if (response.status === 409) { conflicts.add(1); sleep(1); return; }
  const hold = response.json().hold_id;
  response = post(`/holds/${hold}/confirm`, {}, 'hold/confirm');
  if (valid(response, [200])) {
    const reservation = response.json().reservation_id;
    valid(post(`/reservations/${reservation}/cancel`, {}, 'reservation/cancel'), [200]);
  }
  joinedAt = 0; seenAdmission = false; sleep(5);
}
