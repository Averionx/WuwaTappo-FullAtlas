"""Apply the local-mode integration to the versioned official snapshot.

Bindings and component locations come from parsed JavaScript, not guessed
minified variable names. Unknown layouts fail before an installed file changes.
"""
from pathlib import Path
import hashlib, json, re, shutil, os

PROJECT = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ['WUWA_BUILD_ROOT'])
BASE = Path((ROOT / 'current_base.txt').read_text(encoding='utf-8'))
structure = json.loads((BASE / 'js_structure.json').read_text(encoding='utf-8'))
config = json.loads((ROOT / 'local_config.json').read_text(encoding='utf-8'))
shared_name = structure['shared']
shared = (BASE / 'readable_js/assets' / shared_name).read_text(encoding='utf-8')
route_region = shared[shared.index('const router = createRouter'):]
routes = dict(re.findall(r'path:\s*"([^"]+)"[\s\S]*?import\("\./([^"]+)"\)', route_region)[:9])
main_name, panel_name = routes['/'], routes['/panel']
main = (BASE / 'readable_js/assets' / main_name).read_text(encoding='utf-8')
panel = (BASE / 'readable_js/assets' / panel_name).read_text(encoding='utf-8')
frontend = ROOT / 'frontend_v2'
shutil.copytree(BASE / 'frontend', frontend, dirs_exist_ok=True)
patch_log = []

def replace(text, old, new, count=1):
    actual = text.count(old)
    assert actual == count, (old[:100], actual, count)
    patch_log.append({'anchor': old[:100], 'matches': actual})
    return text.replace(old, new)

def apply_edits(text, edits):
    last = len(text) + 1
    for start, end, value in sorted(edits, key=lambda e: (e[0], e[1]), reverse=True):
        assert 0 <= start <= end <= last, (start, end, last)
        text = text[:start] + value + text[end:]
        last = start
    return text

def function_for(meta, text, needle):
    found = [f for f in meta['functions'] if needle in text[f['start']:f['end']]]
    assert found, needle
    return min(found, key=lambda f: f['end'] - f['start'])

def named(meta, name):
    found = [f for f in meta['functions'] if f['name'] == name]
    assert len(found) == 1, (name, found)
    return found[0]

# Shared public functions retain readable names between these releases.
shared = replace(shared, 'loaderModule.init(kurodataConfig);\nwindow.kurodata = loaderModule;\ninitTrackCommonProps();\ninitFrontendAlertReporting();', '''let localOnlineServicesStarted = false;
function localStartOnlineServices() {
 if (localOnlineServicesStarted || window.__WUWA_LOCAL_ATLAS__?.enabled.value) return;
 localOnlineServicesStarted = true;
 loaderModule.init(kurodataConfig); window.kurodata = loaderModule;
 initTrackCommonProps(); initFrontendAlertReporting();
}''')
for name in ['invoke$1', 'invoke']:
    anchor = f'async function {name}(e, t = {{}}, n) {{'
    shared = replace(shared, anchor, anchor + '\n window.__WUWA_LOCAL_ATLAS__?.checkInvoke(e, t);')
for name in ['loadRemoteDictionary(e, t)', 'ensureAppearanceAssetCatalog(e)']:
    anchor = 'async function ' + name + ' {'
    shared = replace(shared, anchor, anchor + '\n if (window.__WUWA_LOCAL_ATLAS__?.enabled.value) return true;')
shared = replace(shared, 'function applyCatalog(e, t, n) {', '''function applyCatalog(e, t, n) {
 if (window.__WUWA_LOCAL_ATLAS__?.enabled.value && t !== window.__WUWA_LOCAL_ATLAS__.assetsHost) return;''')
shared = replace(shared, 'function atlas() {', '''function atlas() {
 if (window.__WUWA_LOCAL_ATLAS__?.enabled.value) return Promise.resolve({code: 0, data: window.__WUWA_LOCAL_ATLAS__.offlineData.value.atlas});''')
shared = replace(shared, 'function track(e, t, n) {', 'function track(e, t, n) {\n if (window.__WUWA_LOCAL_ATLAS__?.enabled.value) return;')
for name in ['isAppUpdaterEnabled()', 'isForceUpdateLocked()']:
    shared = replace(shared, 'function ' + name + ' {', 'function ' + name + ' {\n if (window.__WUWA_LOCAL_ATLAS__?.enabled.value) return false;')
shared = replace(shared, 'this.instance.interceptors.request.use(t => {', '''this.instance.interceptors.request.use(t => {
 if (window.__WUWA_LOCAL_ATLAS__?.enabled.value) throw window.__WUWA_LOCAL_ATLAS__.offlineError();''')
controller = (PROJECT / 'src/local_atlas_controller.js').read_text(encoding='utf-8')
init = controller + '\nconst localAtlasController = createLocalAtlasController({\n' + \
    'ref, window, storage: localStorage, origin: ' + json.dumps(f'http://127.0.0.1:{config["port"]}') + ',\n' + \
    'token: null' + ''', normalizeAtlasList, resolvePetAssetIdFromAppearanceId, getAppearanceAssetById,
snapshotCatalog: () => ({assets: appearanceAssetCatalog.value, atlases: appearanceAtlasCatalog.value, host: loadedAssetsHost, ts: loadedAssetsJsonTs}),
applyOfflineCatalog: (payload, host) => applyCatalog(buildCatalogMaps(payload), host, Date.now()),
restoreCatalog: saved => applyCatalog({assets: saved.assets, atlases: saved.atlases}, saved.host, saved.ts),
onError: error => console.error('[local-gallery]', error)
});
window.__WUWA_LOCAL_ATLAS__ = localAtlasController;
localAtlasController.ready.then(() => { localStartOnlineServices(); return bootstrap(); }).catch(error => {
 console.error('[local-gallery] startup failed', error);
 document.getElementById('app').textContent = '请通过本地版启动器运行。' + error.message;
});
watch(localAtlasController.enabled, on => { if (!on) localStartOnlineServices(); });
'''
shared = replace(shared, 'bootstrap();\nexport {', init + '\nexport { localAtlasController as zzLocalAtlas,\n')

# Main renderer: derive names from imports and the existing snapshot contract.
m = structure['files'][main_name]
mi = m['imports']
component = next(c for c in m['components'] if c['name'] == 'index')
m = {**m, 'functions': [fn for fn in m['functions'] if component['body'] < fn['start'] < component['bodyEnd']]}
assert len(m['snapshots']) == 1
snapshot = m['snapshots'][0]
f = snapshot['fields']
store, watch, mounted = mi['globalStore'], mi['watch'], mi['onMounted']
role, accessory, host, bag, atlas = [f[k] for k in ['selectedRoleId', 'selectedPartId', 'assetsCdnHost', 'bagList', 'atlasList']]
getchar, getaccess, getemotes = [mi[k] for k in ['getUserCharacterAssetName', 'getUserAccessoryAssetName', 'getUserEmoteAssets']]
emote_pattern = re.escape(mi['computed']) + r'\(\(\) => ' + re.escape(store) + r'\.isLoggedIn \? ' + re.escape(getemotes) + r'\(' + re.escape(store) + r'\.userInfo\)[\s\S]{0,250}?\}\)\) : ([\w$]+)\.value\)'
emotes = re.search(emote_pattern, main)
assert emotes, 'Emote selection computed layout changed'
emotes = emotes.group(1) + '.value'
edits = [(0, 0, f'import {{zzLocalAtlas as __lg}} from "./{shared_name}";\n')]
def insert_function(name, code):
    pos = named(m, name)['body'] + 1
    edits.append((pos, pos, '\n' + code + '\n'))
bag_loader = function_for(m, main, 'await ' + mi['getBagList'] + '()')
atlas_loader = function_for(m, main, 'await ' + mi['atlas'] + '()')
activity_loader = function_for(m, main, 'await ' + mi['activityInfo'] + '()')
insert_function(bag_loader['name'], f'if(__lg.enabled.value){{{f["bagListLoading"]}=false;return;}}')
insert_function(atlas_loader['name'], f'if(__lg.enabled.value){{{atlas}=__lg.offlineData.value.atlas;{f["atlasListLoading"]}=false;return;}}')
insert_function(activity_loader['name'], 'if(__lg.enabled.value){__localRefresh();return;}')
for action in ['create-room', 'join-room']:
    insert_function(m['cases'][action], f"if(__lg.enabled.value){{{mi['showToast']}('本地全图鉴已开启，无法进入联机。请先关闭开关。');return;}}")
select_name = m['cases']['select-appearance']
param = re.search(r'function\s+' + re.escape(select_name) + r'\((\w+)', main).group(1)
select_function = named(m, select_name)
select_source = main[select_function['start']:select_function['end']]
max_emotes = re.search(r'\.length >= ([\w$]+) \|\|', select_source)
assert max_emotes, 'Emote capacity guard changed'
insert_function(select_name, f'''if(__lg.enabled.value){{try{{__lg.select({param},{store}.userInfo,{max_emotes[1]});__localRefresh();}}catch(error){{{mi['showToast']}(error.message);}}return;}}''')
reorder_name = m['cases']['reorder-emotes']
param = re.search(r'function\s+' + re.escape(reorder_name) + r'\((\w+)', main).group(1)
insert_function(reorder_name, f'if(__lg.enabled.value){{__lg.reorder({param},{store}.userInfo);__localRefresh();return;}}')
favorite_name = m['cases']['collect-change']
param = re.search(r'function\s+' + re.escape(favorite_name) + r'\((\w+)', main).group(1)
insert_function(favorite_name, f'if(__lg.enabled.value){{__lg.favorite({param}.assetId,{param}.is_collect===1);return;}}')
snap_text = main[snapshot['start']:snapshot['end']]
snap_text = snap_text.replace('bagList: ' + bag, 'bagList: __lg.inventory(' + atlas + ',' + bag + ')')
snap_text = snap_text.replace('atlasList: ' + atlas, 'atlasList: __lg.enabled.value ? __lg.offlineData.value.atlas : ' + atlas)
snap_text = snap_text.replace(f['userInfo'], f['userInfo'].replace(store + '.userInfo', '__lg.viewUser(' + store + '.userInfo)'))
snap_text = snap_text.replace('selectedEmoteAssetIds: ' + f['selectedEmoteAssetIds'], 'selectedEmoteAssetIds: ' + getemotes + '(__lg.viewUser(' + store + '.userInfo)).map(item=>item.id)')
edits.append((snapshot['start'], snapshot['end'], snap_text))
for meaning in ['getUserCharacterAssetId', 'getUserCharacterAssetName', 'getUserAccessoryAssetId', 'getUserAccessoryAssetName', 'getUserEmoteAssets', 'getUserAccessoryOffset', 'getUserCharacterMyOffset']:
    alias = mi[meaning]
    for match in re.finditer(re.escape(alias) + r'\(' + re.escape(store) + r'\.userInfo\)', main):
        if not (snapshot['start'] <= match.start() < snapshot['end']):
            edits.append((match.start(), match.end(), alias + '(__lg.viewUser(' + store + '.userInfo))'))
local_code = f'''
let __localSaved=null;
function __localRefresh(){{
 if(!__lg.enabled.value)return;
 const user=__lg.viewUser({store}.userInfo);
 {host}=__lg.assetsHost;
 const name={getchar}(user);if(name){role}=name.replace(/\\.png$/i,'');
 {accessory}={getaccess}(user)||null;
 {emotes}={getemotes}(user).map(item=>({{id:item.id,name:item.name}}));
 {atlas}=__lg.offlineData.value.atlas;
}}
{watch}(__lg.enabled,on=>{{
 if(on){{__localSaved={{role:{role},accessory:{accessory},emotes:[...{emotes}],host:{host},atlas:{atlas}}};__localRefresh();}}
 else if(__localSaved){{{role}=__localSaved.role;{accessory}=__localSaved.accessory;{emotes}=__localSaved.emotes;{host}=__localSaved.host;{atlas}=__localSaved.atlas;__localSaved=null;{activity_loader['name']}({{force:true}}).then(()=>{bag_loader['name']}()).catch(()=>{{}});}}
}},{{immediate:true}});
{watch}([__lg.selection,__lg.revision,{mi['appearanceAssetCatalog']}],()=>{{if(__lg.enabled.value)__localRefresh();}});
{watch}([()=>{role},()=>{accessory},()=>{host}],()=>{{if(__lg.enabled.value)__localRefresh();}});
'''
edits.append((component['returnStart'], component['returnStart'], local_code))
main = apply_edits(main, edits)
for key in ['canCreateRoom', 'canJoinRoom']:
    main = main.replace(key + ': ' + f[key], key + ': !__lg.enabled.value && ' + f[key])

# Settings/atlas UI retains this release's own bindings and components.
p = structure['files'][panel_name]
pi = p['imports']
settings = next(c for c in p['components'] if c['name'] == 'SettingsModule')
atlas_component = next(c for c in p['components'] if c['name'] == 'MainPanelAtlasTab')
container = next(c for c in p['containers'] if settings['body'] < c['start'] < settings['bodyEnd'])
h = pi['createBaseVNode']
with_modifiers = pi['withModifiers']
setup = f'''
const __localEnabled=__lg.enabled,__localBusy=__lg.busy,__localSync=__lg.syncStatus;
async function __toggleLocal(event){{try{{await __lg.setEnabled(event.target.checked);}}catch(error){{{pi['showToast']}(error.message);}}event.target.checked=__localEnabled.value;}}
async function __syncLocal(){{try{{const status=await __lg.syncCache(true);{pi['showToast']}('本地图鉴已同步：'+(status.result?.atlas_count||'')+'项');}}catch(error){{{pi['showToast']}(error.message);}}}}
'''
row = f'''{h}('div',{{class:'setting-item','data-local-gallery-setting':'true'}},[
 {h}('div',{{class:'setting-label'}},[{h}('div',{{class:'setting-title'}},'本地全图鉴（离线）'),{h}('div',{{class:'setting-sub'}},__localBusy.value?'正在切换系统断网状态…':__localEnabled.value?'已开启 · 已断开服务器，联机不可用':'开启全部本地图鉴；关闭后恢复正常联网',1)]),
 {h}('div',{{class:'setting-content'}},[{h}('label',{{class:'setting-switch'}},[{h}('input',{{type:'checkbox',role:'switch','aria-label':'本地全图鉴（离线）',style:'display:block;position:absolute;width:1px;height:1px;opacity:0',checked:__localEnabled.value,disabled:__localBusy.value||__localSync.value.status==='running',onChange:__toggleLocal,onMousedown:{with_modifiers}(()=>{{}},['stop'])}},null,40,['checked','disabled']),{h}('span',{{class:'setting-slider'}})])])]),
 {h}('div',{{class:'setting-item','data-local-gallery-sync':'true'}},[{h}('div',{{class:'setting-label'}},[{h}('div',{{class:'setting-title'}},'更新本地图鉴'),{h}('div',{{class:'setting-sub'}},__localSync.value.status==='running'?'正在同步 '+__localSync.value.done+'/'+__localSync.value.total:'普通联网模式下检查新增图鉴，缓存完整后供离线使用',1)]),{h}('button',{{class:'setting-btn',type:'button',disabled:__localEnabled.value||__localSync.value.status==='running',onClick:__syncLocal}},'检查并同步',8,['disabled'])]),
'''
edits = [(0, 0, f'import {{zzLocalAtlas as __lg}} from "./{shared_name}";\n'),
         (settings['body'] + 1, settings['body'] + 1, setup),
         (container['array'] + 1, container['array'] + 1, row)]
panel_root = next(c for c in p['components'] if c['name'] == 'index')
root_source = panel[panel_root['body']:panel_root['bodyEnd']]
state_ref = re.search(r'const ([\w$]+) = ' + re.escape(pi['ref']) + r'\(null\)', root_source)
assert state_ref, 'Panel snapshot state declaration changed'
ready_retry = f'''
let __panelDisposed=false;
{pi['onUnmounted']}(()=>{{__panelDisposed=true;}});
{pi['onMounted']}(()=>{{
 for(const delay of [500,1500,3000,6000,10000])window.setTimeout(()=>{{
  if(!__panelDisposed&&!{state_ref[1]}.value)window.__TAURI_INTERNALS__.invoke('plugin:event|emit',{{event:'cat-panel-action',payload:{{type:'ready'}}}}).catch(()=>{{}});
 }},delay);
}});
'''
edits.append((panel_root['returnStart'], panel_root['returnStart'], ready_retry))
for condition in p['roomConditions']:
    text = condition['test']
    if 'activeTab' in text:
        message = pi['openBlock'] + '(), ' + pi['createElementBlock'] + "('div',{class:'module-block',style:'padding:24px'},'本地全图鉴已开启，无法进入联机。请先关闭开关。')"
        edits.append((condition['start'], condition['start'], '__lg.enabled.value && ' + text + ' ? (' + message + ') : '))
panel = apply_edits(panel, edits)
pattern = r'([\w$]+)\.value \? await ([\w$]+)\(await ' + re.escape(pi['unfavoriteAsset']) + r'\(([\w$]+)\.item.asset_id\)\) : await \2\(await ' + re.escape(pi['favoriteAsset']) + r'\(\3\.item.asset_id\)\)'
match = re.search(pattern, panel)
assert match, 'Favorite toggle layout changed'
panel = panel[:match.start()] + f'__lg.enabled.value ? __lg.favorite({match[3]}.item.asset_id,!{match[1]}.value) : ' + panel[match.start():]

for name, text in [(shared_name, shared), (main_name, main), (panel_name, panel)]:
    (frontend / 'assets' / name).write_text(text, encoding='utf-8')
manifest = {'shared': shared_name, 'main': main_name, 'panel': panel_name,
            'settingsSymbol': settings['variable'], 'atlasSymbol': atlas_component['variable'],
            'base': str(BASE), 'version': '1.0.1'}
(ROOT / 'build_manifest_v2.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
# Reuse the independently checked PE resource packer and private-runtime stub.
packer = (PROJECT / 'tools/pe_packer.py').read_text(encoding='utf-8').split('# Add a read-only PE section', 1)[1]
packer = '# Add a read-only PE section' + packer
packer = packer.replace("source = Path(r'D:\\WuwaTappo\\WuwaTappo.exe')", "source = BASE / 'WuwaTappo.official.exe'")
packer = packer.replace("ROOT / 'WuwaTappo.Local.exe'", "ROOT / 'WuwaTappo.Local.v2.exe'")
packer = packer.replace("ROOT / 'build_report.json'", "ROOT / 'build_report_v2.json'")
ORIGINAL = BASE
import sys

import brotli, pefile, base64, struct
exec(compile(packer, 'checked_pe_packer', 'exec'))
