const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert/strict');
const root = path.join(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'src/local_atlas_controller.js'), 'utf8');
const catalog = JSON.parse(fs.readFileSync(path.join(root, 'build/payload/cache/offline_catalog.json')));
const atlas = JSON.parse(fs.readFileSync(path.join(root, 'build/payload/cache/atlas.json'))).data;
const checks = [];
const record = (name, fn) => { fn(); checks.push(name); };
let firewall = false, rejectMode = false, realRemoteCalls = 0, modeRequests = [];
const storage = new Map(), listeners = {}, sockets = [], xhrs = [];
class FakeXHR {
  open(method, url) { this.url = url; }
  addEventListener() {}
  send() { realRemoteCalls++; }
  abort() { this.aborted = true; }
}
class FakeSocket {
  constructor(url) { this.url = url; sockets.push(this); }
  addEventListener() {}
  close() { this.closed = true; }
}
FakeSocket.OPEN = 1;
const window = {
  location: {href: 'http://tauri.localhost/index.html', origin: 'http://tauri.localhost'},
  fetch: async (url, opts) => {
    if (!String(url).startsWith('http://127.0.0.1:43219/')) { realRemoteCalls++; return {ok: true, json: async () => ({})}; }
    let body;
    if (url.endsWith('/status')) body = {ready: true, enabled: firewall, firewall_verified: false, mode_verified: true, network_policy: 'rooms-only'};
    if (url.endsWith('/offline-data')) body = {catalog, atlas};
    if (url.endsWith('/mode')) {
      modeRequests.push(JSON.parse(opts.body).enabled);
      if (rejectMode) return {ok: false, json: async () => ({error: 'mode policy rejected'})};
      firewall = JSON.parse(opts.body).enabled;
      body = {enabled: firewall, firewall_verified: false, mode_verified: true, network_policy: 'rooms-only', ready: true};
    }
    return {ok: true, json: async () => body};
  },
  XMLHttpRequest: FakeXHR, WebSocket: FakeSocket, EventSource: FakeSocket,
  navigator: {sendBeacon() { realRemoteCalls++; return true; }},
  __TAURI_INTERNALS__: {invoke: async () => { realRemoteCalls++; return 'called'; }},
  addEventListener(name, cb) { listeners[name] = cb; },
  dispatchEvent() {}, CustomEvent: class { constructor(type, init) { this.type = type; Object.assign(this, init); } }
};
const context = {URL, AbortController, console};
Object.defineProperty(window.__TAURI_INTERNALS__, 'invoke', {value:window.__TAURI_INTERNALS__.invoke,writable:false});
vm.createContext(context); vm.runInContext(source + '\nthis.factory=createLocalAtlasController;', context);
let current = null, restored = 0;
const factory = context.factory;
const controller = factory({
  ref: value => ({value}), window,
  reloadOnDisable: false,
  storage: {getItem: key => storage.get(key), setItem: (key, val) => storage.set(key, val)},
  origin: 'http://127.0.0.1:43219', token: 'test', atlasCount: atlas.length,
  normalizeAtlasList: value => value,
  resolvePetAssetIdFromAppearanceId(id) { for (const type of ['character_skin_atlas','accessory_atlas','emote_atlas']) if (catalog[type][id]) return catalog[type][id].height_light_id; return id; },
  getAppearanceAssetById(id) { for (const type of ['character_skin','accessory','emote']) if (catalog[type][id]) return {...catalog[type][id], asset_id: id, asset_type: type}; return null; },
  snapshotCatalog: () => ({original: true}), applyOfflineCatalog: value => { current = value; },
  restoreCatalog: () => { current = null; restored++; }, onError: error => { throw error; }
});
(async () => {
  await controller.ready;
  record('starts disabled', () => assert.equal(controller.enabled.value, false));
  const official = {id: 99, character: {id: 1004, name: 'original.png'}, accessory: null, emote: [], role_id: '1407'};
  const originalText = JSON.stringify(official);
  const originalBag = [{asset_id: 1004, quantity: 1}];
  record('disabled inventory is original reference', () => assert.equal(controller.inventory(atlas, originalBag), originalBag));
  const oldSocket = new window.WebSocket('wss://api-mc-wuwatappo.kurogames-global.com/socket.io/');
  const ordinarySocket=new window.WebSocket('wss://example.invalid');
  const ordinaryXhr=new window.XMLHttpRequest();ordinaryXhr.open('GET','https://example.invalid');ordinaryXhr.send();
  const oldXhr = new window.XMLHttpRequest(); oldXhr.open('POST', 'https://api-mc-wuwatappo.kurogames-global.com/api/frontend/rooms/join'); oldXhr.send();
  const before = realRemoteCalls;
  await controller.setEnabled(true);
  record('requires verified local policy before enabling', () => assert.equal(firewall && controller.enabled.value, true));
  record('closes existing WebSocket and XHR', () => assert.ok(oldSocket.closed && oldXhr.aborted));
  record('existing ordinary traffic is not interrupted',()=>assert.ok(!ordinarySocket.closed&&!ordinaryXhr.aborted));
  const inventory = controller.inventory(atlas, originalBag);
  record('all 899 entries owned, quantity one', () => assert.ok(inventory.length === 899 && inventory.every(e => e.owned && e.quantity === 1)));
  record('all catalog IDs resolve to real usable IDs', () => assert.ok(inventory.every(e => catalog[e.asset_type][e.asset_id])));
  record('all 899 IDs remain distinct', () => assert.equal(new Set(inventory.map(e => e.asset_id)).size, 899));
  record('fresh profile gets a real cached character', () => assert.ok(catalog.character_skin[controller.viewUser(null).character.id]));
  const role = inventory.find(e => e.asset_type === 'character_skin' && e.asset_id !== 1004);
  controller.select(role, official, 8);
  record('local character selection takes effect', () => assert.equal(controller.viewUser(official).character.id, role.asset_id));
  record('account data stays byte-for-byte unchanged', () => assert.equal(JSON.stringify(official), originalText));
  controller.favorite(role.asset_id, true);
  record('favorite only changes local inventory', () => assert.equal(controller.inventory(atlas, originalBag).find(e => e.asset_id === role.asset_id).is_collect, 1));
  await window.fetch('https://example.invalid');checks.push('ordinary remote fetch remains available');
  await window.fetch('https://api-mc-wuwatappo.kurogames-global.com/api/frontend/user/me');checks.push('account read remains available');
  await window.fetch('https://api-mc-wuwatappo.kurogames-global.com/api/auth/login',{method:'POST'});checks.push('login network remains available');
  await assert.rejects(window.fetch('https://api-mc-wuwatappo.kurogames-global.com/api/frontend/rooms/join',{method:'POST'}), /本地全图鉴/);checks.push('room HTTP blocked');
  await window.fetch('https://api-mc-wuwatappo.kurogames-global.com/api/frontend/chests/open',{method:'POST'});checks.push('real chest request remains available');
  for(const [route,method]of [['assets/synthesis','POST'],['user/me/appearance','PUT'],['presets','POST']]){
    await assert.rejects(window.fetch('https://api-mc-wuwatappo.kurogames-global.com/api/frontend/'+route,{method}),/本地全图鉴/);checks.push('local account write blocked: '+route);
  }
  new window.WebSocket('wss://example.invalid');checks.push('unrelated WebSocket remains available');
  assert.throws(()=>new window.WebSocket('wss://api-mc-wuwatappo.kurogames-global.com/socket.io/'),/本地全图鉴/);checks.push('room WebSocket blocked');
  new window.EventSource('https://example.invalid');checks.push('ordinary EventSource remains available');
  const xhr = new window.XMLHttpRequest();xhr.open('GET','https://example.invalid');xhr.send();checks.push('ordinary XHR remains available');
  const roomXhr=new window.XMLHttpRequest();roomXhr.open('POST','https://api-mc-wuwatappo.kurogames-global.com/api/frontend/rooms');
  assert.throws(()=>roomXhr.send(),/本地全图鉴/);checks.push('room XHR blocked');
  record('ordinary beacon remains available',()=>assert.equal(window.navigator.sendBeacon('https://example.invalid',''),true));
  record('room beacon blocked',()=>assert.equal(window.navigator.sendBeacon('https://api-mc-wuwatappo.kurogames-global.com/api/frontend/rooms',''),false));
  controller.checkInvoke('plugin:http|fetch',{clientConfig:{url:'https://example.invalid',method:'GET'}});checks.push('native public HTTP remains available');
  assert.throws(()=>controller.checkInvoke('plugin:http|fetch',{clientConfig:{url:'https://api-mc-wuwatappo.kurogames-global.com/api/frontend/rooms/join',method:'POST'}}),/本地全图鉴/);checks.push('native room HTTP blocked');
  await window.fetch('http://127.0.0.1:43219/status');checks.push('local cache host remains usable');
  record('public traffic reached original transport',()=>assert.ok(realRemoteCalls>before));
  await controller.setEnabled(false);
  record('disable restores original catalog', () => assert.ok(!firewall && !controller.enabled.value && current === null && restored === 1));
  record('disable restores official appearance', () => assert.equal(controller.viewUser(official), official));
  record('disable restores official bag', () => assert.equal(controller.inventory(atlas, originalBag), originalBag));
  await window.fetch('https://example.invalid'); checks.push('remote fetch resumes after disable');
  rejectMode = true;
  await assert.rejects(controller.setEnabled(true), /policy/); checks.push('failed mode verification cannot enable local mode');
  record('failure leaves mode off and clears busy state', () => assert.ok(!controller.enabled.value && !controller.busy.value));
  record('mode changes are persisted', () => assert.equal(JSON.parse(storage.get('wuwatappo-local-gallery-v1')).enabled, false));
  const result = {passed: checks.length, checks, modeRequests, network_policy: 'rooms-only'};
  fs.writeFileSync(path.join(root, 'controller_test_results.json'), JSON.stringify(result, null, 2));
  console.log(JSON.stringify(result, null, 2));
})().catch(error => { console.error(error); process.exitCode = 1; });
