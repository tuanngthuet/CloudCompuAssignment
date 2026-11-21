import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { test } from 'node:test';
import { csv, summarize, writeSummary } from './summarize-c3.mjs';

test('k6 summary excludes preflight requests and emits sanitized, reproducible CSV/SVG', async () => {
  const dir = mkdtempSync(join(tmpdir(), 'labseat-c3-chart-'));
  try {
    const input = join(dir, 'raw.json');
    const point = (metric, value, operation_class = 'platform') => JSON.stringify({
      type: 'Point', metric, data: { time: '2026-11-20T13:30:01Z', value,
        tags: { operation_class, url: 'https://private.example/secret-id' } },
    });
    writeFileSync(input, [point('http_reqs', 1, 'preflight'), point('http_reqs', 1),
      point('http_reqs', 1), point('http_req_duration', 120),
      point('platform_read_ms', 100), point('platform_read_ms', 200),
      point('platform_workflows_completed', 1), point('dropped_iterations', 0)].join('\n') + '\n');
    const rows = await summarize(input, 'platform');
    assert.equal(rows.length, 1);
    assert.equal(rows[0].http_reqs, 2);
    assert.equal(rows[0].read_p95_ms, 200);
    assert.equal(rows[0].http_p95_ms, 120);
    assert.equal(rows[0].workflows_completed, 1);
    assert.ok(!csv(rows).includes('private.example'));
    const out = join(dir, 'out');
    writeSummary(rows, out);
    assert.ok(readFileSync(join(out, 'load-rps.svg'), 'utf8').includes('<svg'));
  } finally {
    assert.equal(dirname(dir), tmpdir());
    rmSync(dir, { recursive: true, force: true });
  }
});
