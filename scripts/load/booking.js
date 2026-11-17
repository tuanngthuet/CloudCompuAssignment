import http from 'k6/http';
import { check, sleep } from 'k6';
import { SharedArray } from 'k6/data';
import { Counter, Trend } from 'k6/metrics';

const base = __ENV.BASE_URL;
const session = __ENV.SESSION_ID;
if (!base || !session || !__ENV.ACCOUNTS_FILE) throw new Error('BASE_URL, SESSION_ID and ACCOUNTS_FILE are required');
const users = new SharedArray('private test accounts', () => JSON.parse(open(__ENV.ACCOUNTS_FILE)));
const vus = Number(__ENV.VUS || 20);
if (users.length < vus) throw new Error('Each VU needs a distinct account');
export const options = {
  noCookiesReset: true,
  summaryTrendStats: ['avg', 'med', 'p(95)', 'p(99)', 'max'],
  vus, duration: __ENV.DURATION || '5m',
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
    http.get(base + '/', { tags: { operation_class: 'catalogue', route: '/'  } });
    const response = http.post(base + '/auth/login', JSON.stringify(users[__VU - 1]), {
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': cookie('labseat_pre_csrf') || '' },
      tags: { operation_class: 'catalogue', route: '/auth/login' },
    });
    if (!valid(response, [200])) { sleep(5); return; }
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
  const seats = response.json().items.filter(s => s.available);
  if (!seats.length) {
    post(root + '/leave', {}, 'queue/leave'); joinedAt = 0; seenAdmission = false; sleep(5); return;
  }
  response = post('/holds', { session_id: session, seat_id: seats[(__VU - 1) % seats.length].id }, '/holds');
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
