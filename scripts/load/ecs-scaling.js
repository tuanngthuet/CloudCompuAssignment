// C3 scaling probe. Run each level separately and record actual throughput and AWS activity.
import http from 'k6/http';
import { check, sleep } from 'k6';
const base = (__ENV.BASE_URL || '').replace(/\/$/, '');
const vus = Number(__ENV.VUS || 60);
const holdMinutes = Number(__ENV.HOLD_MINUTES || 15);
const pauseSeconds = Number(__ENV.PAUSE_SECONDS || 1);
if (!base) throw new Error('BASE_URL required');
if (!Number.isInteger(vus) || ![60, 100, 150, 200].includes(vus)) throw new Error('C3 scaling VUS must be 60, 100, 150 or 200');
if (!Number.isInteger(holdMinutes) || holdMinutes < 15 || holdMinutes > 25) throw new Error('HOLD_MINUTES must be 15-25');
if (!Number.isFinite(pauseSeconds) || pauseSeconds < 0.25) throw new Error('PAUSE_SECONDS must be at least 0.25');
export const options = {
  stages: [
    { duration: '2m', target: 5 },
    { duration: '3m', target: vus },
    { duration: `${holdMinutes}m`, target: vus },
    { duration: '5m', target: 0 },
  ],
  summaryTrendStats: ['avg', 'med', 'p(95)', 'p(99)', 'max'],
  thresholds: { http_req_failed: ['rate<0.01'], http_req_duration: ['p(95)<1000'] },
};
export default function () {
  for (const path of ['/events', '/lab-sessions']) {
    const response = http.get(base + path, { tags: { operation_class: 'scaling', route: path } });
    check(response, { available: r => r.status === 200 });
  }
  sleep(pauseSeconds);
}
