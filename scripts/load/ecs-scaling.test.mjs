import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import vm from 'node:vm';

const source = readFileSync(new URL('./ecs-scaling.js', import.meta.url), 'utf8')
  .replace(/^import .*;\r?\n/gm, '')
  .replace('export const options =', 'const options =')
  .replace('export default function ()', 'function run()')
  + '\nglobalThis.api = { options, run };';
function load(vus, hold = '15') {
  const context = vm.createContext({ __ENV: { BASE_URL: 'https://local.example', VUS: String(vus), HOLD_MINUTES: hold },
    Number, Error, http: { get: () => ({ status: 200 }) }, check: () => true, sleep: () => {} });
  vm.runInContext(source, context);
  return context.api.options;
}
test('scaling stages hold an allowed level at least 15 minutes', () => {
  const options = load(150);
  assert.equal(options.stages[1].target, 150);
  assert.equal(options.stages[2].duration, '15m');
});
test('scaling refuses more than 200 VUs or short holds', () => {
  assert.throws(() => load(201), /60, 100, 150 or 200/);
  assert.throws(() => load(60, '14'), /15-25/);
});
