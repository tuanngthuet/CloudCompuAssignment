import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

const root = path.resolve(import.meta.dirname, '../..');
const manifestPaths = [
  'evidence/assessment/20261119T034356Z-b3-functional/manifest.json',
  'evidence/assessment/20261119T043844Z-b4-preflight/manifest.json',
  'evidence/assessment/20261119T050938Z-b5-s3-restore/manifest.json',
  'evidence/assessment/20261119T172832Z-b4-c1-preflight/manifest.json',
  'evidence/assessment/20261120T130757Z-c2-local/manifest.json',
];
const digest = data => crypto.createHash('sha256').update(data).digest('hex');
const results = [];
for (const relative of manifestPaths) {
  const filename = path.join(root, relative);
  if (!fs.existsSync(filename)) {
    results.push({ manifest: relative, status: 'MISSING' });
    continue;
  }
  const manifest = JSON.parse(fs.readFileSync(filename, 'utf8'));
  let passed = 0;
  const failures = [];
  for (const entry of manifest.files ?? []) {
    const target = path.resolve(path.dirname(filename), entry.path);
    if (!target.startsWith(path.dirname(filename) + path.sep) || !fs.existsSync(target)) {
      failures.push({ path: entry.path, reason: 'missing_or_outside' });
      continue;
    }
    const bytes = fs.readFileSync(target);
    const raw = digest(bytes);
    const normalized = /\.(json|md|csv|svg|txt|log)$/i.test(target)
      ? digest(Buffer.from(bytes.toString('utf8').replace(/\r\n/g, '\n')))
      : raw;
    if (entry.sha256?.toLowerCase() === raw || entry.sha256?.toLowerCase() === normalized) passed++;
    else failures.push({ path: entry.path, reason: 'hash_mismatch' });
  }
  results.push({ manifest: relative, task: manifest.task_id, run_id: manifest.run_id,
    status: failures.length ? 'FAIL' : 'PASS', passed, total: (manifest.files ?? []).length, failures });
}

const markdownRoots = ['docs/assessment', 'evidence/assessment'];
function walk(dir) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap(entry => {
    const file = path.join(dir, entry.name);
    return entry.isDirectory() ? walk(file) : file.endsWith('.md') ? [file] : [];
  });
}
const missingLinks = [];
let checkedLinks = 0;
for (const dir of markdownRoots) for (const filename of walk(path.join(root, dir))) {
  const markdown = fs.readFileSync(filename, 'utf8');
  for (const match of markdown.matchAll(/\[[^\]]*\]\((<?[^)]+>?)\)/g)) {
    let ref = match[1].replace(/^<|>$/g, '').split('#')[0].split('?')[0];
    if (!ref || /^(?:[a-z][a-z\d+.-]*:|\/\/|\/)/i.test(ref)) continue;
    try { ref = decodeURIComponent(ref); } catch { /* keep literal reference */ }
    checkedLinks++;
    if (!fs.existsSync(path.resolve(path.dirname(filename), ref)))
      missingLinks.push({ source: path.relative(root, filename).replaceAll('\\', '/'), target: ref });
  }
}
const csv = fs.readFileSync(path.join(root, 'docs/assessment/functional/test-cases.csv'), 'utf8');
const statuses = Object.fromEntries(['PASS', 'FAIL', 'BLOCKED', 'NOT_RUN'].map(status =>
  [status, (csv.match(new RegExp(`,${status},`, 'g')) ?? []).length]));
const output = { manifestChecks: results, markdown: { checkedLinks, missingLinks }, b3StatusCounts: statuses };
process.stdout.write(JSON.stringify(output, null, 2) + '\n');
if (results.some(x => x.status !== 'PASS') || missingLinks.length) process.exitCode = 1;
