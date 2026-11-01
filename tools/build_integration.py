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
shared = replace(shared, 'showTaskbarIcon: !0', 'showTaskbarIcon: !1')
shared = replace(shared, 'function loadDesktopCatSettings() {', '''function loadDesktopCatSettings() {
 const settings=__originalLoadDesktopCatSettings();
 const marker='wuwatappo-taskbar-default-v1';
 try {
  if(localStorage.getItem(marker)!=='1'){
   settings.showTaskbarIcon=false;
   const saved=JSON.parse(localStorage.getItem(DESKTOP_CAT_SETTINGS_STORAGE_KEY)||'{}');
   localStorage.setItem(DESKTOP_CAT_SETTINGS_STORAGE_KEY,JSON.stringify({...saved,showTaskbarIcon:false}));
   localStorage.setItem(marker,'1');
  }
 }catch{}
 return settings;
}
function __originalLoadDesktopCatSettings() {''')
shared = replace(shared, 'loaderModule.init(kurodataConfig);\nwindow.kurodata = loaderModule;\ninitTrackCommonProps();\ninitFrontendAlertReporting();', '''let localOnlineServicesStarted = false;
function localStartOnlineServices() {
 if (localOnlineServicesStarted) return;
 localOnlineServicesStarted = true;
 loaderModule.init(kurodataConfig); window.kurodata = loaderModule;
 initTrackCommonProps(); initFrontendAlertReporting();
}''')
for name in ['invoke$1', 'invoke']:
    anchor = f'async function {name}(e, t = {{}}, n) {{'
    if name=='invoke$1' and config['client_version']=='1.0.3':
        assert anchor not in shared
        continue
    shared = replace(shared, anchor, anchor + '\n window.__WUWA_LOCAL_ATLAS__?.checkInvoke(e, t);')
for name in ['ensureAppearanceAssetCatalog(e)']:
    anchor = 'async function ' + name + ' {'
    shared = replace(shared, anchor, anchor + '\n if (window.__WUWA_LOCAL_ATLAS__?.enabled.value) return true;')
shared = replace(shared, 'function applyCatalog(e, t, n) {', '''function applyCatalog(e, t, n) {
 if (window.__WUWA_LOCAL_ATLAS__?.enabled.value && t !== window.__WUWA_LOCAL_ATLAS__.assetsHost) return;''')
shared = replace(shared, 'function atlas() {', '''function atlas() {
 if (window.__WUWA_LOCAL_ATLAS__?.enabled.value) return Promise.resolve({code: 0, data: window.__WUWA_LOCAL_ATLAS__.offlineData.value.atlas});''')
shared = replace(shared, 'this.instance.interceptors.request.use(t => {', '''this.instance.interceptors.request.use(t => {
 if (window.__WUWA_LOCAL_ATLAS__?.enabled.value && window.__WUWA_LOCAL_ATLAS__.restricted(t.url,t.method)) throw window.__WUWA_LOCAL_ATLAS__.offlineError();''')
controller = (PROJECT / 'src/local_atlas_controller.js').read_text(encoding='utf-8')
init = controller + '\nconst localAtlasController = createLocalAtlasController({\n' + \
    'ref, window, storage: localStorage, origin: ' + json.dumps(f'http://127.0.0.1:{config["port"]}') + ',\n' + \
    'token: null' + ''', normalizeAtlasList, resolvePetAssetIdFromAppearanceId, getAppearanceAssetById,
snapshotCatalog: () => ({assets: appearanceAssetCatalog.value, atlases: appearanceAtlasCatalog.value, host: loadedAssetsHost, ts: loadedAssetsJsonTs}),
getAccountCumulative: () => globalStore.userInfo ? isFrozenClickCount(globalStore.serverClickTotal) ? globalStore.serverClickTotal : clampClickCountSum(globalStore.serverClickTotal+globalStore.localClickCount) : parseSafeClickCount(globalStore.localClickCount),
getAccountPending: () => parseSafeClickCount(globalStore.localClickCount),
catalogConsumer: ['/', '/panel'].includes((window.location.hash || '#/').slice(1).split('?')[0]),
applyOfflineCatalog: (payload, host) => applyCatalog(buildCatalogMaps(payload), host, Date.now()),
restoreCatalog: saved => applyCatalog({assets: saved.assets, atlases: saved.atlases}, saved.host, saved.ts),
onError: error => console.error('[local-gallery]', error)
});
window.__WUWA_LOCAL_ATLAS__ = localAtlasController;
localAtlasController.ready.then(() => { localStartOnlineServices(); return bootstrap(); }).catch(error => {
 console.error('[local-gallery] startup failed', error);
 const app=document.getElementById('app');
 app.textContent='本地服务未能启动，请退出后使用“WuwaTappo全图鉴版”快捷方式或绿色版启动。';
 app.style.cssText='margin:20px;padding:18px;border-radius:16px;background:#fff3db;color:#976238;font:15px/1.8 sans-serif;max-width:460px';
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
preset_loader = function_for(m, main, 'await ' + mi['getPresetList'] + '()')
preset_source=main[preset_loader['start']:preset_loader['end']]
preset_normalize=re.search(re.escape(f['presetList'])+r' = [^\n]+\.map\(([\w$]+)\)',preset_source)[1]
snapshot_fn=next(fn['name'] for fn in m['functions'] if fn['start']<snapshot['start']<fn['end'])
dispatch_fn=function_for(m,main,snapshot_fn+'())')['name']
preset_limit=re.search(re.escape(f['presetList'])+r'\.length >= ([\w$]+)',main[named(m,m['cases']['create-preset'])['start']:named(m,m['cases']['create-preset'])['end']])[1]
for action,operation in [('create-preset',f'__lg.createLocalPreset({store}.userInfo,{preset_limit})'),('delete-preset','__lg.deleteLocalPreset(e)'),('apply-preset','__lg.applyLocalPreset(e.preset_id)')]:
    insert_function(m['cases'][action],f'''if(__lg.enabled.value){{
 if({mi['isForceUpdateLocked']}())return;
 try{{{operation};__localRefresh();{dispatch_fn}();}}catch(error){{{mi['showToast']}(error.message);}}return;
}}''')
insert_function(preset_loader['name'],f'if(__lg.enabled.value){{{f["presetListLoading"]}=false;return;}}')
insert_function(atlas_loader['name'], f'if(__lg.enabled.value){{{atlas}=__lg.offlineData.value.atlas;{f["atlasListLoading"]}=false;return;}}')
insert_function(activity_loader['name'], 'try {')
edits.append((activity_loader['bodyEnd']-1,activity_loader['bodyEnd']-1,'}finally{if(__lg.enabled.value)__localRefresh();}'))
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
snap_text=snap_text.replace('presetList: '+f['presetList'],'presetList: __lg.enabled.value ? __lg.presetList().map('+preset_normalize+') : '+f['presetList'])
snap_text=snap_text.replace('presetListLoading: '+f['presetListLoading'],'presetListLoading: !__lg.enabled.value && '+f['presetListLoading'])
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
{watch}(__lg.revision,()=>{{if(__lg.enabled.value){dispatch_fn}();}});
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
 {h}('div',{{class:'setting-label'}},[{h}('div',{{class:'setting-title'}},'本地全图鉴'),{h}('div',{{class:'setting-sub'}},__localBusy.value?'正在切换本地显示模式…':__localEnabled.value?'已开启 · 联机不可用，其他网络功能正常':'开启全部本地图鉴；关闭后恢复账号背包',1)]),
 {h}('div',{{class:'setting-content'}},[{h}('label',{{class:'setting-switch'}},[{h}('input',{{type:'checkbox',role:'switch','aria-label':'本地全图鉴',style:'display:block;position:absolute;width:1px;height:1px;opacity:0',checked:__localEnabled.value,disabled:__localBusy.value||__localSync.value.status==='running',onChange:__toggleLocal,onMousedown:{with_modifiers}(()=>{{}},['stop'])}},null,40,['checked','disabled']),{h}('span',{{class:'setting-slider'}})])])]),
 {h}('div',{{class:'setting-item','data-local-gallery-sync':'true'}},[{h}('div',{{class:'setting-label'}},[{h}('div',{{class:'setting-title'}},'更新本地图鉴'),{h}('div',{{class:'setting-sub'}},__localSync.value.status==='running'?'正在同步 '+__localSync.value.done+'/'+__localSync.value.total:'联网检查新增图鉴，本地全图鉴开启时也可同步',1)]),{h}('button',{{class:'setting-btn',type:'button',disabled:__localSync.value.status==='running',onClick:__syncLocal}},'检查并同步',8,['disabled'])]),
'''
edits = [(0, 0, f'import {{zzLocalAtlas as __lg}} from "./{shared_name}";\n')]
settings_text=panel[settings['start']:settings['end']]
check_handler=re.search(r'class: "setting-btn btn-check-update",[\s\S]{0,250}?onClick: '+re.escape(with_modifiers)+r'\(([\w$]+),',settings_text)[1]
check_fn=next(fn for fn in p['functions'] if fn['name']==check_handler and settings['start']<fn['start']<settings['end'])
edits.append((check_fn['body']+1,check_fn['body']+1,"\n await __lg.assistant.openPanel('updates');return;\n"))
disabled=re.search(r'class: "setting-btn btn-check-update",\s*disabled: ([^,]+),',settings_text)
disabled_start=settings['start']+disabled.start(1)
edits.append((disabled_start,settings['start']+disabled.end(1),'false'))
assert panel[container['start']:container['end']].endswith('], 32)')
project_footer=f''',{h}('div',{{style:{{padding:'18px 4px',textAlign:'center',color:'#9c7856'}}}},[{h}('button',{{type:'button',class:'setting-btn',onClick:()=>__lg.assistant.openProject()}},'WuwaTappo全图鉴版 · GitHub 项目与反馈')])'''
footer_pos=container['end']-len('], 32)')
edits.append((footer_pos,footer_pos,project_footer))

module_component=next(c for c in p['components'] if c['name']=='MainModulePanel')
module_text=panel[module_component['start']:module_component['end']]
console_component=f'''
const __ConsolePage={pi['defineComponent']}({{
 __name:'WuwaNativeConsole',setup(){{
  const target={pi['ref']}(null);
  {pi['onMounted']}(()=>__lg.assistant.mountConsole(target.value));
  {pi['onUnmounted']}(()=>__lg.assistant.closePanel());
  return ()=>{h}('div',{{class:'module-block',style:{{height:'100%',minHeight:0,position:'relative',overflow:'hidden',paddingTop:'48px'}}}},[{h}('div',{{ref:target,style:{{height:'100%',minHeight:0}}}})]);
 }}
}});
const __consoleTabs={pi['computed']}(()=>{pi['unref']}(ko).flatMap(item=>item.key==='setting'?[{{key:'console',labelKey:'console'}},item]:[item]));
'''
edits.append((module_component['body']+1,module_component['body']+1,console_component))
icon_match=re.search(re.escape(h)+r'\("span", \{\s*class: [\w$]+\(\["tab-btn__icon", `tab-btn__icon--\$\{l.key\}`\]\)\s*\}, null, 2\)',module_text)
assert icon_match,'native navigation icon layout changed'
console_icon=f'''l.key==='console'?({pi['openBlock']}(),{pi['createElementBlock']}('svg',{{key:'console-icon',class:'tab-btn__icon tab-btn__icon--console',viewBox:'0 0 40 54','aria-hidden':'true','data-console-icon':'sliders',style:{{color:s.activeTab==='console'?'#9c6541':'#f4d5a5'}}}},[
 {h}('rect',{{x:7,y:15,width:26,height:25,rx:5,fill:'none',stroke:'currentColor','stroke-width':2.5}}),
 {h}('path',{{d:'M14 21v13M20 21v13M26 21v13',fill:'none',stroke:'currentColor','stroke-width':2.2,'stroke-linecap':'round'}}),
 {h}('circle',{{cx:14,cy:25,r:2.6,fill:'currentColor'}}),{h}('circle',{{cx:20,cy:30,r:2.6,fill:'currentColor'}}),{h}('circle',{{cx:26,cy:24,r:2.6,fill:'currentColor'}})
],4)):{icon_match[0]}'''
pos=module_component['start']+icon_match.start()
edits.append((pos,module_component['start']+icon_match.end(),console_icon))
for old,new in [
 ('return T.key === "toggle"','return T.key === "console" ? "控制台" : T.key === "toggle"'),
 ('Se(p(ko),','Se(__consoleTabs.value,'),
 ('s.activeTab === "bag" ?',f's.activeTab === "console" ? ({pi["openBlock"]}(),{pi["createBlock"]}(__ConsolePage,{{key:"console"}})) : s.activeTab === "bag" ?')]:
    assert module_text.count(old)==1,('native console anchor',old)
    pos=module_component['start']+module_text.index(old)
    edits.append((pos,pos+len(old),new))
bag_component=next(c for c in p['components'] if c['name']=='MainPanelBagTab')
bag_text=panel[bag_component['start']:bag_component['end']]
login_guard='if (!'+pi['globalStore']+'.isLoggedIn)'
assert bag_text.count(login_guard)==2,'preset login guard layout changed'
for match in re.finditer(re.escape(login_guard),bag_text):
    edits.append((bag_component['start']+match.start(),bag_component['start']+match.end(),'if (!'+pi['globalStore']+'.isLoggedIn && !__lg.enabled.value)'))
delete_guard='if (r.stopPropagation(), !'+pi['globalStore']+'.isLoggedIn)'
assert bag_text.count(delete_guard)==1,'preset delete login guard changed'
pos=bag_component['start']+bag_text.index(delete_guard)
edits.append((pos,pos+len(delete_guard),'if (r.stopPropagation(), !'+pi['globalStore']+'.isLoggedIn && !__lg.enabled.value)'))

# Reuse the original atlas+bag merge so collection ownership is identical to
# the per-rarity counts. Use the category list before its search/subfilters.
atlas_text=panel[atlas_component['start']:atlas_component['end']]
all_rows=re.search(r'([\w$]+) = '+re.escape(pi['computed'])+r'\(\(\) => [\w$]+\([\w$]+\([\w$]+\.atlasList, [\w$]+\.bagList\)\)\)',atlas_text)[1]
category_match=re.search(r'([\w$]+) = '+re.escape(pi['computed'])+r'\(\(\) => \{\s*const [\w$]+ = [\w$]+\[([\w$]+)\.value\];',atlas_text)
assert category_match,'atlas category computed layout changed'
category_rows,category_index=category_match.groups()
loading=re.search(r'([\w$]+) = '+re.escape(pi['computed'])+r'\(\(\) => [\w$]+\.bagListLoading \|\| [\w$]+\.atlasListLoading\)',atlas_text)[1]
edits.append((atlas_component['returnStart'],atlas_component['returnStart'],f"const __atlasProgress={pi['computed']}(()=>__lg.collectionProgress({category_rows}.value,{loading}.value)),__atlasProgressTitle={pi['computed']}(()=>['全图鉴收集进度','全角色收集进度','全配件收集进度','全表情收集进度'][{category_index}.value]||'全图鉴收集进度');\n"))
tab_anchor='null, 8, ["modelValue", "tabs"]),'
assert atlas_text.count(tab_anchor)==1,'atlas tab header changed'
progress=f''' !__lg.enabled.value ? ({pi['openBlock']}(true),{pi['createElementBlock']}('section',{{key:'account-atlas-progress','data-atlas-progress':'online',style:{{padding:'12px 4px 14px',width:'100%',boxSizing:'border-box'}}}},[
 {h}('div',{{style:{{display:'flex',justifyContent:'space-between',alignItems:'center',gap:'12px',fontSize:'14px',color:'#927b65',marginBottom:'8px'}}}},[
 {h}('span',null,__atlasProgressTitle.value),{h}('strong',{{style:{{fontVariantNumeric:'tabular-nums',color:'#996644'}}}},
 !{pi['globalStore']}.isLoggedIn?'登录后查看':{loading}.value?'正在读取…':__atlasProgress.value.collected+'/'+__atlasProgress.value.total+' · '+__atlasProgress.value.percent.toFixed(1)+'%')]),
 {h}('div',{{role:'progressbar','aria-label':'真实账号'+__atlasProgressTitle.value,'aria-valuemin':0,'aria-valuemax':__atlasProgress.value.total,'aria-valuenow':__atlasProgress.value.collected,'aria-busy':{loading}.value,style:{{height:'9px',width:'100%',background:'#ecddc4',borderRadius:'20px',overflow:'hidden'}}}},[
 {h}('span',{{style:{{display:'block',height:'100%',width:({pi['globalStore']}.isLoggedIn?__atlasProgress.value.percent:0)+'%',background:'linear-gradient(90deg,#e4b56f,#c58b51)',borderRadius:'inherit',transition:'width .25s ease'}}}})])],-2)) : {pi['createCommentVNode']}('local-atlas-progress-hidden',true),'''
pos=atlas_component['start']+atlas_text.index(tab_anchor)+len(tab_anchor)
edits.append((pos,pos,progress))
room_component=next(c for c in p['components'] if c['name']=='MainPanelRoomTab')
room_text=panel[room_component['start']:room_component['end']]
room_container=next(c for c in p['containers'] if room_component['body']<c['start']<room_component['bodyEnd'])
history_code=f'''
const __history={pi['ref']}([]),__historyBusy={pi['ref']}(false),__historyError={pi['ref']}('');
let __historyDisposed=false,__historyTimer=null,__historyGeneration=0;
async function __refreshHistory(){{
 if(__historyDisposed||__historyBusy.value)return;
 const generation=++__historyGeneration;
 try{{const rows=await __lg.assistant.roomHistory();if(!__historyDisposed&&generation===__historyGeneration)__history.value=rows;}}
 catch(error){{if(!__historyDisposed)__historyError.value=error.message;}}
}}
async function __favoriteHistory(room){{
 if(__historyBusy.value)return;
 __historyBusy.value=true;__historyGeneration++;
 try{{const rows=await __lg.assistant.favoriteRoom(room.code,!room.favorite);if(!__historyDisposed)__history.value=rows;}}
 catch(error){{__historyError.value=error.message;}}finally{{__historyBusy.value=false;}}
}}
async function __joinHistory(room){{
 if(__historyBusy.value)return;
 __historyBusy.value=true;
 try{{await __lg.assistant.joinHistoryRoom(room.code);__historyError.value='已请求加入房间 '+room.code;}}
 catch(error){{__historyError.value=error.message;}}finally{{__historyBusy.value=false;}}
}}
async function __deleteHistory(room){{
 if(__historyBusy.value)return;
 __historyBusy.value=true;__historyGeneration++;
 try{{const rows=await __lg.assistant.deleteRoom(room.code);if(!__historyDisposed)__history.value=rows;}}
 catch(error){{__historyError.value=error.message;}}finally{{__historyBusy.value=false;}}
}}
{pi['onMounted']}(()=>{{__refreshHistory();__historyTimer=window.setInterval(__refreshHistory,2500);}});
{pi['onUnmounted']}(()=>{{__historyDisposed=true;window.clearInterval(__historyTimer);}});
function __renderRoomHistory(){{
 return ({pi['openBlock']}(true),{pi['createElementBlock']}('section',{{key:'native-room-history','data-room-history':'true',style:{{marginTop:'24px',padding:'18px',borderRadius:'18px',border:'1px solid #e8cda7',background:'#fff9ec',maxWidth:'100%',boxSizing:'border-box'}}}},[
 {h}('div',{{style:{{fontSize:'17px',fontWeight:700,color:'#946746',marginBottom:'6px'}}}},'联机历史'),
 {h}('p',{{style:{{fontSize:'12px',color:'#aa9278',margin:'0 0 12px'}}}},'成功进入后自动记录，收藏置顶；房间仍存在时可再次加入。'),
 __historyError.value?{h}('p',{{style:{{fontSize:'12px',color:'#a36343'}}}},__historyError.value):null,
 {h}('div',{{class:'common-scrollbar2',style:{{maxHeight:'240px',overflowY:'auto'}}}},__history.value.length?__history.value.map(room=>{h}('div',{{key:room.code,style:{{display:'flex',alignItems:'center',gap:'12px',padding:'10px 0',borderBottom:'1px solid #ecdcc5'}}}},[
 {h}('button',{{type:'button','aria-label':room.favorite?'取消收藏':'收藏房间','aria-pressed':room.favorite,disabled:__historyBusy.value,onClick:()=>__favoriteHistory(room),style:{{border:0,background:'transparent',fontSize:'22px',color:'#c6974e',cursor:'pointer'}}}},room.favorite?'★':'☆'),
 {h}('div',{{style:{{flex:1,minWidth:0}}}},[{h}('div',{{style:{{fontSize:'15px',fontWeight:600,color:'#946746',overflow:'hidden',textOverflow:'ellipsis'}}}},room.code+' · '+(room.host||'未知房主')),{h}('div',{{style:{{fontSize:'11px',color:'#aa9278'}}}},'最近进入 '+new Date(room.visited*1000).toLocaleString('zh-CN',{{hour12:false}}))]),
 {h}('button',{{type:'button',class:'common-btn',disabled:__historyBusy.value||__lg.enabled.value||__lg.assistant.updateRequired.value||!{pi['globalStore']}.isLoggedIn||s.roomMode!=='idle',onClick:()=>__joinHistory(room)}},'加入'),
 {h}('button',{{type:'button',class:'common-btn',disabled:__historyBusy.value,onClick:()=>__deleteHistory(room)}},'删除记录')])):[{h}('p',{{style:{{fontSize:'13px',color:'#aa9278',margin:'14px 0'}}}},'暂无联机历史，成功进入房间后会自动记录。')])],-2));
}}
'''
edits.append((room_component['returnStart'],room_component['returnStart'],history_code))
# Put history after both the idle join controls and the active-room members.
assert panel[room_container['start']:room_container['end']].endswith('], 32)'), 'room container closing layout changed'
history_position=room_container['end']-len('], 32)')
edits.append((history_position,history_position,',__renderRoomHistory()'))
panel_root = next(c for c in p['components'] if c['name'] == 'index')
root_source = panel[panel_root['body']:panel_root['bodyEnd']]
state_ref = re.search(r'\b([\w$]+) = ' + re.escape(pi['ref']) + r'\(null\)', root_source)
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

from integrate_assistant import integrate
assert config['client_version'] in ('1.0.2','1.0.3'), 'Desktop assistant requires a verified adapter'
shared, main, panel = integrate(PROJECT, BASE, frontend, structure, shared, main, panel, main_name, panel_name)
# The original native update window supplies a compact separate surface. Its
# official installer UI must never run alongside the variant's own updater.
update_name=routes['/update']
(frontend/'assets'/update_name).write_text('export default {name:"FullAtlasUpdateWindow",render:()=>null};\n',encoding='utf-8')
extra_patched_assets = [p.name for p in (BASE/'frontend/assets').glob('*.js')
                        if (frontend/'assets'/p.name).read_bytes() != p.read_bytes()]
for name, text in [(shared_name, shared), (main_name, main), (panel_name, panel)]:
    (frontend / 'assets' / name).write_text(text, encoding='utf-8')
manifest = {'shared': shared_name, 'main': main_name, 'panel': panel_name,
            'settingsSymbol': settings['variable'], 'atlasSymbol': atlas_component['variable'],
            'base': str(BASE), 'version': config['client_version']}
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
