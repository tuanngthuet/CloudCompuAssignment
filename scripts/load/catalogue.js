import http from 'k6/http';
import { check, sleep } from 'k6';
import { Trend, Counter } from 'k6/metrics';
const base = __ENV.BASE_URL;
if (!base) throw new Error('BASE_URL is required');
export const options = {
  stages: [{ duration: '1m', target: 5 }, { duration: '5m', target: Number(__ENV.VUS || 30) }, { duration: '1m', target: 0 }],
  summaryTrendStats: ['avg', 'med', 'p(95)', 'p(99)', 'max'],
  thresholds: { http_req_failed: ['rate<0.01'], http_req_duration: ['p(95)<1000'] },
};
const latency = new Trend('catalogue_latency_ms', true);
const failures = new Counter('unexpected_responses');
export default function () {
  for (const path of ['/events', '/lab-sessions', '/healthz']) {
    const r = http.get(base + path, { tags: { operation: 'catalogue' } });
    latency.add(r.timings.duration);
    if (!check(r, { 'catalogue available': x => x.status === 200 })) failures.add(1);
  }
  sleep(0.5);
}
