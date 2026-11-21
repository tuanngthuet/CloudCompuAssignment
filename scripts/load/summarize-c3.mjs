// Convert private k6 NDJSON metrics into sanitized minute CSV and reproducible SVG charts.
// Usage: node scripts/load/summarize-c3.mjs <k6-raw.json> <output-dir> [operation-class]
import { createReadStream, mkdirSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { createInterface } from 'node:readline';
import { fileURLToPath } from 'node:url';

const fields = ['http_reqs', 'http_req_failed', 'platform_unexpected_failure', 'dropped_iterations',
  'platform_workflows_started', 'platform_workflows_completed', 'platform_holds_ok',
  'platform_confirms_ok', 'platform_cancels_ok'];
function percentile(values, fraction) {
  if (!values.length) return null;
  values.sort((a, b) => a - b);
  return values[Math.ceil(values.length * fraction) - 1];
}
function numeric(value) { return Number.isFinite(value) ? value : null; }
export async function summarize(input, operationClass = '') {
  const buckets = new Map();
  let lines = 0;
  for await (const line of createInterface({ input: createReadStream(input), crlfDelay: Infinity })) {
    if (!line.trim()) continue;
    lines++;
    let item;
    try { item = JSON.parse(line); } catch { throw Error(`Invalid k6 JSON at line ${lines}`); }
    if (item.type !== 'Point' || !item.data || !item.metric) continue;
    const metric = item.metric;
    if (!fields.includes(metric) && !['http_req_duration', 'platform_read_ms', 'platform_write_ms'].includes(metric)) continue;
    if (operationClass && ['http_reqs', 'http_req_failed', 'http_req_duration'].includes(metric) &&
        item.data.tags?.operation_class !== operationClass) continue;
    const time = Date.parse(item.data.time);
    const value = Number(item.data.value);
    if (!Number.isFinite(time) || !Number.isFinite(value)) throw Error(`Invalid point at line ${lines}`);
    const bucket = new Date(Math.floor(time / 60000) * 60000).toISOString();
    if (!buckets.has(bucket)) buckets.set(bucket, Object.fromEntries(fields.map(x => [x, 0])));
    const row = buckets.get(bucket);
    row.read = row.read || [];
    row.write = row.write || [];
    row.http = row.http || [];
    if (metric === 'platform_read_ms') row.read.push(value);
    else if (metric === 'platform_write_ms') row.write.push(value);
    else if (metric === 'http_req_duration') row.http.push(value);
    else row[metric] += value;
  }
  if (!buckets.size) throw Error('No matching k6 points found');
  return [...buckets.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([bucket_utc, x]) => ({
    bucket_utc, http_reqs: x.http_reqs, rps: numeric(x.http_reqs / 60),
    http_req_failed: x.http_req_failed, unexpected_errors: x.platform_unexpected_failure,
    dropped_iterations: x.dropped_iterations, workflows_started: x.platform_workflows_started,
    workflows_completed: x.platform_workflows_completed, holds_ok: x.platform_holds_ok,
    confirms_ok: x.platform_confirms_ok, cancels_ok: x.platform_cancels_ok,
    http_p95_ms: percentile(x.http || [], 0.95),
    read_p95_ms: percentile(x.read || [], 0.95), write_p95_ms: percentile(x.write || [], 0.95),
  }));
}
const columns = ['bucket_utc', 'http_reqs', 'rps', 'http_req_failed', 'unexpected_errors',
  'dropped_iterations', 'workflows_started', 'workflows_completed', 'holds_ok', 'confirms_ok',
  'cancels_ok', 'http_p95_ms', 'read_p95_ms', 'write_p95_ms'];
export function csv(rows) {
  return [columns.join(','), ...rows.map(row => columns.map(key => row[key] ?? '').join(','))].join('\n') + '\n';
}
function svg(rows, title, series) {
  const width = 1100, height = 400, left = 80, top = 48, plotWidth = 980, plotHeight = 295;
  const max = Math.max(1, ...series.flatMap(s => rows.map(r => r[s.key]).filter(Number.isFinite)));
  const x = i => left + (rows.length === 1 ? plotWidth / 2 : i * plotWidth / (rows.length - 1));
  const y = value => top + plotHeight * (1 - value / max);
  const lines = series.map(s => {
    const points = rows.map((row, i) => Number.isFinite(row[s.key]) ? `${x(i)},${y(row[s.key])}` : null)
      .filter(Boolean).join(' ');
    return `<polyline fill="none" stroke="${s.color}" stroke-width="2" points="${points}"/>`;
  }).join('');
  const legend = series.map((s, i) => `<text x="${left + i * 240}" y="390" fill="${s.color}">${s.label}</text>`).join('');
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
<rect width="${width}" height="${height}" fill="white"/><text x="${left}" y="28" font-size="20">${title}</text>
<path d="M${left} ${top}V${top + plotHeight}H${left + plotWidth}" fill="none" stroke="#444"/>
<text x="10" y="${top + 8}">${max.toFixed(2)}</text><text x="35" y="${top + plotHeight}">0</text>
<text x="${left}" y="365">${rows[0].bucket_utc}</text><text x="820" y="365">${rows.at(-1).bucket_utc}</text>
${lines}${legend}</svg>\n`;
}
export function writeSummary(rows, outputDir) {
  mkdirSync(outputDir, { recursive: true });
  writeFileSync(join(outputDir, 'k6-minute.csv'), csv(rows), 'utf8');
  writeFileSync(join(outputDir, 'load-rps.svg'), svg(rows, 'Actual HTTP requests per second by UTC minute',
    [{ key: 'rps', label: 'Actual RPS', color: '#1769aa' }]), 'utf8');
  writeFileSync(join(outputDir, 'latency-p95.svg'), svg(rows, 'p95 latency by UTC minute (ms)',
    [{ key: 'http_p95_ms', label: 'HTTP p95 ms', color: '#1769aa' },
      { key: 'read_p95_ms', label: 'Read p95 ms', color: '#268b4a' },
      { key: 'write_p95_ms', label: 'Write p95 ms', color: '#d04b31' }]), 'utf8');
  writeFileSync(join(outputDir, 'errors-dropped.svg'), svg(rows, 'Errors and dropped iterations by UTC minute',
    [{ key: 'http_req_failed', label: 'HTTP failed', color: '#b02121' },
      { key: 'unexpected_errors', label: 'Unexpected errors', color: '#d04b31' },
      { key: 'dropped_iterations', label: 'Dropped iterations', color: '#7b42a8' }]), 'utf8');
}
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const [, , input, outputDir, operationClass = ''] = process.argv;
  if (!input || !outputDir) throw Error('Usage: node summarize-c3.mjs <k6-raw.json> <output-dir> [operation-class]');
  const rows = await summarize(input, operationClass);
  writeSummary(rows, outputDir);
  console.log(`Wrote ${rows.length} UTC buckets to ${resolve(outputDir)}`);
}
