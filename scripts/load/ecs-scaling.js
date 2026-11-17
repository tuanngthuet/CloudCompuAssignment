// Approved synthetic environment only. This collects load metrics, never claims autoscaling success.
import http from 'k6/http';
import { check, sleep } from 'k6';
if (!__ENV.BASE_URL) throw new Error('BASE_URL required');
export const options = {
  stages: [
    { duration: '2m', target: 5 },
    { duration: '3m', target: Number(__ENV.VUS || 60) },
    { duration: '15m', target: Number(__ENV.VUS || 60) },
    { duration: '5m', target: 0 },
  ],
  summaryTrendStats: ['avg', 'med', 'p(95)', 'p(99)', 'max'],
  thresholds: { http_req_failed: ['rate<0.01'], http_req_duration: ['p(95)<1000'] },
};
export default function () {
  for (const path of ['/events', '/lab-sessions']) {
    const response = http.get(__ENV.BASE_URL + path);
    check(response, { available: r => r.status === 200 });
  }
  sleep(0.25);
}
