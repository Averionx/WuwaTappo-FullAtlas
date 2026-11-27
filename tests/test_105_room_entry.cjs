const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const acorn = require('../tools/acorn.cjs');

const build = path.resolve(process.env.WUWA_BUILD_ROOT || path.join(__dirname, '../build'));
const manifest = JSON.parse(fs.readFileSync(path.join(build, 'build_manifest_v2.json'), 'utf8'));
assert.equal(manifest.version, '1.0.5');
const main = fs.readFileSync(path.join(build, 'frontend_v2/assets', manifest.main), 'utf8');
const ast = acorn.parse(main, {ecmaVersion: 'latest', sourceType: 'module'});
const cases = new Map();
const functions = new Map();
function walk(node) {
  if (!node?.type) return;
  if (node.type === 'SwitchCase' && ['join-room', 'random-join-room'].includes(node.test?.value)) {
    cases.set(node.test.value, node.consequent[0]?.expression);
  }
  if (node.type === 'FunctionDeclaration') functions.set(node.id.name, node);
  for (const value of Object.values(node)) {
    if (Array.isArray(value)) value.forEach(walk);
    else walk(value);
  }
}
walk(ast);
const manual = cases.get('join-room');
const random = cases.get('random-join-room');
assert.equal(random.callee.name, manual.callee.name);
const handler = functions.get(random.callee.name);
const source = main.slice(handler.start, handler.end);
const [, toast, dismiss, store, join] = source.match(
  /if\(__lg\.enabled\.value\)\{([\w$]+)\([^\n]+\n\s*if \(([\w$]+)\(\), !([\w$]+)\.isLoggedIn\)[\s\S]+?\n\s*await ([\w$]+)\(e\)/
);
const mode = {value: true};
const calls = [];
let blocked = 0;
const context = vm.createContext({
  __lg: {enabled: mode},
  [toast]: () => blocked++,
  [dismiss]: () => {},
  [store]: {isLoggedIn: true},
  [join]: async randomMatch => calls.push(randomMatch),
});
vm.runInContext(source, context);

async function verify() {
  const enter = action => vm.runInContext(main.slice(action.start, action.end), context);
  await enter(manual);
  await enter(random);
  assert.equal(blocked, 2);
  assert.deepEqual(calls, []);
  mode.value = false;
  await enter(manual);
  await enter(random);
  assert.deepEqual(calls, [false, true]);
  console.log('1.0.5 generated room handlers block both join paths in local mode and preserve normal/random dispatch online.');
}
verify().catch(error => { console.error(error); process.exitCode = 1; });
