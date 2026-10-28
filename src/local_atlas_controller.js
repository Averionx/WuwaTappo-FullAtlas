// This factory is shared by every WebView and exercised independently in tests.
function createLocalAtlasController(d) {
  const KEY = 'wuwatappo-local-gallery-v1';
  const CACHE_KEY='wuwatappo-local-cache-generation';
  const enabled = d.ref(false), busy = d.ref(false), selection = d.ref({}), favorites = d.ref({});
  const offlineData = d.ref(null), revision = d.ref(0);
  const syncStatus = d.ref({status: 'idle', done: 0, total: 0});
  let originalCatalog = null, pending = Promise.resolve();
  let statusTimer=null, disposed=false;
  let offlinePolicyInstalled = false;
  const sockets = new Set(), xhrs = new Set(), fetches = new Set();
  const rawFetch = d.window.fetch.bind(d.window);
  const origin = d.origin;
  const offlineError = () => new Error('本地全图鉴已开启：不能进入联机或把本地图鉴外观写入账号。真实点击和开箱正常。');
  const read = () => { try { return JSON.parse(d.storage.getItem(KEY) || '{}'); } catch { return {}; } };
  const remote = value => {
    try {
      const u = new URL(typeof value === 'string' || value instanceof URL ? String(value) : value.url, d.window.location.href);
      return !(['data:', 'blob:', 'tauri:', 'asset:'].includes(u.protocol) || u.origin === origin || u.origin === d.window.location.origin);
    } catch { return true; }
  };
  function restricted(value, method='GET', socket=false) {
    try {
      const input=typeof value==='string'||value instanceof URL?String(value):value.url;
      const url=new URL(input,d.window.location.href), path=decodeURIComponent(url.pathname).replace(/^\/+/, '');
      if (/^api\/frontend\/rooms(?:\/|$)/i.test(path) || /(?:^|\/)socket\.io(?:\/|$)/i.test(path))return true;
      if(socket && /^(?:ws|wss):$/.test(url.protocol) && url.hostname==='api-mc-wuwatappo.kurogames-global.com')return true;
      if(String(method).toUpperCase()==='GET'||String(method).toUpperCase()==='HEAD')return false;
      return /^api\/frontend\/(?:assets\/(?:synthesis|favorites)|user\/me\/appearance|presets)(?:\/|$)/i.test(path);
    }catch{return false;}
  }
  const save = () => {
    d.storage.setItem(KEY, JSON.stringify({enabled: enabled.value, selection: selection.value, favorites: favorites.value}));
    revision.value++;
  };
  let bootstrapPromise;
  async function ensureLocalToken() {
    if (d.token) return;
    if (!bootstrapPromise) bootstrapPromise=rawFetch(origin+'/bootstrap').then(async response=>{
      if(!response.ok)throw new Error('本地服务身份验证失败');
      d.token=(await response.json()).token;
    }).catch(error=>{bootstrapPromise=null;throw error;});
    await bootstrapPromise;
  }
  async function localRequest(path, body) {
    await ensureLocalToken();
    const response = await rawFetch(origin + path, body === undefined ? {} : {
      method: 'POST', headers: {'Content-Type': 'application/json', 'X-Local-Token': d.token}, body: JSON.stringify(body)
    });
    const value = await response.json();
    if (!response.ok) throw new Error(value.error || '本地离线服务不可用');
    return value;
  }
  function stopConnections() {
    for (const socket of sockets) { try { socket.close(); } catch {} }
    for (const xhr of xhrs) { try { xhr.abort(); } catch {} }
    for (const controller of fetches) controller.abort();
    sockets.clear(); xhrs.clear(); fetches.clear();
    d.window.dispatchEvent(new d.window.CustomEvent('wuwatappo-local-mode', {detail: true}));
  }
  function reportDiagnostic(kind, detail) {
    if (!enabled.value) return;
    rawFetch(origin + '/diagnostic', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Local-Token': d.token},
      body: JSON.stringify({kind, detail, origin: d.window.location.origin, time: Date.now()})}).catch(() => {});
  }
  function installOfflinePolicy() {
    // A local view no longer installs a blanket network CSP. This flag only
    // requests a clean ordinary-account view when the mode is turned off.
    offlinePolicyInstalled = true;
  }
  function installNetworkGuards() {
    d.window.fetch = async (input, options = {}) => {
      const isRemote = restricted(input,options.method||input?.method||'GET');
      if (enabled.value && isRemote) throw offlineError();
      const controller = new AbortController();
      if (options.signal?.aborted) controller.abort();
      const abort = () => controller.abort();
      options.signal?.addEventListener('abort', abort, {once: true});
      if (isRemote) fetches.add(controller);
      try { return await rawFetch(input, {...options, signal: controller.signal}); }
      finally { fetches.delete(controller); options.signal?.removeEventListener('abort', abort); }
    };
    const XHR = d.window.XMLHttpRequest;
    if (XHR) {
      const open = XHR.prototype.open, send = XHR.prototype.send;
      XHR.prototype.open = function(method, url, ...rest) { this.__localRemote = restricted(url,method); return open.call(this, method, url, ...rest); };
      XHR.prototype.send = function(...args) {
        if (enabled.value && this.__localRemote) throw offlineError();
        if (this.__localRemote) { xhrs.add(this); this.addEventListener('loadend', () => xhrs.delete(this), {once: true}); }
        return send.apply(this, args);
      };
    }
    for (const name of ['WebSocket', 'EventSource']) {
      const Original = d.window[name];
      if (!Original) continue;
      const Wrapped = function(url, ...args) {
        const blocked=restricted(url,'GET',name==='WebSocket');
        if (enabled.value && blocked) throw offlineError();
        const instance = new Original(url, ...args);
        if (blocked) { sockets.add(instance); instance.addEventListener?.('close', () => sockets.delete(instance), {once: true}); }
        return instance;
      };
      Object.setPrototypeOf(Wrapped, Original); Wrapped.prototype = Original.prototype;
      d.window[name] = Wrapped;
    }
    if (d.window.navigator?.sendBeacon) {
      const send = d.window.navigator.sendBeacon.bind(d.window.navigator);
      d.window.navigator.sendBeacon = (url, data) => enabled.value && restricted(url,'POST') ? false : send(url, data);
    }
  }
  // Tauri defines its injected invoke property as non-writable. The app's two
  // existing invoke wrapper functions call this guard instead of replacing it.
  function checkInvoke(command, args) {
    if(!enabled.value)return;
    if(!/^plugin:(?:http|websocket)\|/.test(command))return;
    const addresses=[],seen=new WeakSet();let method='GET';
    function visit(value) {
      if(typeof value==='string'){if(/^(?:https?:|wss?:|\/?api\/)/i.test(value))addresses.push(value);return;}
      if(!value||typeof value!=='object'||seen.has(value))return;
      seen.add(value);
      for(const [key,item]of Object.entries(value)){if(key==='method'&&typeof item==='string')method=item;else visit(item);}
    }
    visit(args);
    if(addresses.some(url=>restricted(url,method,/^plugin:websocket\|/.test(command))))throw offlineError();
  }
  async function prepare(refresh = false) {
    if (!offlineData.value || refresh) {
      const data = await localRequest('/offline-data');
      if (!data.catalog || !Array.isArray(data.atlas) || !data.atlas.length || data.atlas.length !== (data.atlas_count ?? d.atlasCount ?? data.atlas.length)) throw new Error('本地图鉴缓存不完整');
      offlineData.value = data;
    }
    return offlineData.value;
  }
  async function applyMode(on) {
    if (on) {
      enabled.value = true;
      installOfflinePolicy();
      stopConnections();
      if(d.catalogConsumer===false){revision.value++;return;}
      const data = await prepare();
      if (!originalCatalog) originalCatalog = d.snapshotCatalog();
      d.applyOfflineCatalog(data.catalog, origin);
    } else {
      enabled.value = false;
      if (originalCatalog) { d.restoreCatalog(originalCatalog); originalCatalog = null; }
      // Restore reactively; reloading would discard a running background driver.
    }
    revision.value++;
  }
  async function setEnabled(on) {
    if (busy.value) return;
    busy.value = true;
    try {
      await d.window.__WUWA_LOCAL_ATLAS__?.assistant?.flushBeforeSwitch(Boolean(on));
      if (on) await prepare(true);
      const response = await localRequest('/mode', {enabled: Boolean(on)});
      if (on && (!response.enabled || !response.mode_verified || response.network_policy!=='rooms-only')) throw new Error('本地模式保护未就绪，未开启本地图鉴');
      await applyMode(Boolean(on));
      save();
    } finally { busy.value = false; }
  }
  function inventory(atlas, bag) {
    revision.value;
    if (!enabled.value) return bag;
    const rows = d.normalizeAtlasList(offlineData.value?.atlas || atlas);
    return rows.map(entry => {
      const type = entry.asset_type.replace(/_atlas$/, '');
      const id = d.resolvePetAssetIdFromAppearanceId(entry.asset_id);
      const meta = d.getAppearanceAssetById(id);
      return {...entry, asset_id: id, asset_type: type,
        role_id: String(meta?.game_role_id || entry.role_id || ''), quantity: 1,
        is_collect: favorites.value[id] ? 1 : 0, owned: true};
    });
  }
  function viewUser(official) {
    if (!enabled.value) return official;
    const s = selection.value;
    let character = s.character || official?.character || null;
    // A clean install has no account appearance yet. Pick a real cached
    // character instead of the official hard-coded online fallback sprite.
    if (!d.getAppearanceAssetById(character?.id)) {
      const first = inventory(offlineData.value?.atlas || [], []).find(item=>item.asset_type==='character_skin');
      if (first) character = {id:first.asset_id,name:first.asset_name};
    }
    return {...official, character,
      accessory: Object.hasOwn(s, 'accessory') ? s.accessory : official?.accessory || null,
      emote: s.emote || official?.emote || [],
      role_id: String(d.getAppearanceAssetById(character?.id)?.game_role_id || official?.role_id || '')};
  }
  function select(item, official, maxEmotes) {
    if (!enabled.value) throw new Error('本地模式尚未开启');
    const user = viewUser(official), s = {...selection.value};
    const asset = {id: item.asset_id, name: item.asset_name};
    const itemRole = String(d.getAppearanceAssetById(item.asset_id)?.game_role_id || '');
    if (item.asset_type !== 'character_skin' && itemRole && itemRole !== '0' && itemRole !== String(user.role_id)) throw new Error('该配件或表情只能用于对应角色');
    if (item.asset_type === 'character_skin') {
      const oldRole = user.role_id;
      s.character = asset;
      const role = String(d.getAppearanceAssetById(asset.id)?.game_role_id || '');
      if (oldRole !== role) {
        s.emote = (user.emote || []).filter(e => !d.getAppearanceAssetById(e.id)?.game_role_id);
        const accessory = user.accessory;
        if (accessory && d.getAppearanceAssetById(accessory.id)?.game_role_id && String(d.getAppearanceAssetById(accessory.id)?.game_role_id) !== role) s.accessory = null;
      }
    } else if (item.asset_type === 'accessory') {
      s.accessory = user.accessory?.id === asset.id ? null : asset;
    } else if (item.asset_type === 'emote') {
      const list = user.emote || [], existing = list.some(e => e.id === asset.id);
      if (!existing && list.length >= maxEmotes) throw new Error('已达到可选表情数量上限');
      s.emote = existing ? list.filter(e => e.id !== asset.id) : [...list, asset];
    }
    selection.value = s; save();
  }
  function favorite(id, value) { favorites.value = {...favorites.value, [id]: Boolean(value)}; save(); }
  function reorder(ids, official) {
    const list = viewUser(official).emote || [], byId = new Map(list.map(e => [e.id, e]));
    if (ids.length !== list.length || new Set(ids).size !== ids.length || ids.some(id => !byId.has(id))) return;
    selection.value = {...selection.value, emote: ids.map(id => byId.get(id))}; save();
  }
  async function syncCache(force = true) {
    syncStatus.value = await localRequest('/sync', {force});
    while (syncStatus.value.status === 'running') {
      await new Promise(resolve => d.window.setTimeout(resolve, 600));
      syncStatus.value = await localRequest('/sync/status');
    }
    if (syncStatus.value.status === 'failed') throw new Error(syncStatus.value.error || '图鉴同步失败，原缓存保留');
    if(enabled.value){const data=await prepare(true);d.applyOfflineCatalog(data.catalog,origin);revision.value++;}
    if(syncStatus.value.result?.changed){
      const generation=String(syncStatus.value.result.assets_json_ts||syncStatus.value.checked_at);
      if(d.storage.getItem(CACHE_KEY)!==generation)d.storage.setItem(CACHE_KEY,generation);
    }
    return syncStatus.value;
  }
  const initial = read();
  enabled.value = initial.enabled === true;
  selection.value = initial.selection || {}; favorites.value = initial.favorites || {};
  installNetworkGuards();
  d.window.addEventListener('securitypolicyviolation', event => reportDiagnostic('policy', {
    directive: event.violatedDirective, blocked: String(event.blockedURI).slice(0, 600)
  }));
  d.window.addEventListener('error', event => {
    if (event.target?.tagName === 'IMG') reportDiagnostic('image_error', {src: String(event.target.currentSrc || event.target.src).slice(0, 600)});
  }, true);
  d.window.addEventListener('storage', event => {
    if(disposed)return;
    if(event.key===CACHE_KEY){
      if(enabled.value&&d.catalogConsumer!==false)prepare(true).then(data=>{d.applyOfflineCatalog(data.catalog,origin);revision.value++;}).catch(d.onError);
      else offlineData.value=null;
      return;
    }
    if (event.key !== KEY) return;
    const state = read();
    selection.value = state.selection || {}; favorites.value = state.favorites || {};
    // Serialize mode changes so a stale async enable cannot overwrite a later disable.
    pending = pending.catch(() => {}).then(() => applyMode(state.enabled === true)).catch(d.onError);
    revision.value++;
  });
  async function waitForHost() {
    let last;
    for(let attempt=0;attempt<40;attempt++) {
      try{return await localRequest('/status');}catch(error){last=error;}
      await new Promise(resolve=>d.window.setTimeout(resolve,500));
    }
    throw last;
  }
  const ready = waitForHost().then(async status => {
    if (!status.ready) throw new Error('离线资源未就绪，请使用本地版启动器');
    await applyMode(status.enabled === true && status.mode_verified === true && status.network_policy==='rooms-only');
    syncStatus.value = status.sync || syncStatus.value;
    save();
    if (d.catalogConsumer!==false&&d.window.setTimeout) d.window.setTimeout(() => syncCache(false).catch(() => {}), 2000);
  });
  if (d.window.setInterval) {
    let checkingStatus = false;
    statusTimer=d.window.setInterval(async () => {
      if (checkingStatus || busy.value) return;
      checkingStatus = true;
      try {
        const status = await localRequest('/status');
        if (status.sync) syncStatus.value = status.sync;
        const on = status.enabled === true && status.mode_verified === true && status.network_policy==='rooms-only';
        if (on !== enabled.value) { await applyMode(on); save(); }
      } catch {}
      finally { checkingStatus = false; }
    }, d.catalogConsumer===false?15000:1500);
  }
  function dispose(){disposed=true;if(statusTimer!==null)d.window.clearInterval?.(statusTimer);}
  return {enabled, busy, selection, favorites, revision, ready, setEnabled, inventory, viewUser, select,
    favorite, reorder, prepare, offlineData, assetsHost: origin, offlineError, checkInvoke, syncStatus, syncCache, request: localRequest, dispose,
    restricted,normalCumulative:()=>d.getAccountCumulative?.()??0,normalPending:()=>d.getAccountPending?.()??0};
}
