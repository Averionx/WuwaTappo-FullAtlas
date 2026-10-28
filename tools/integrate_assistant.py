"""Extend a structurally verified 1.0.2 frontend; fail on contract changes."""
import re


def integrate(project, base, frontend, structure, shared, main, panel, main_name, panel_name):
    def once(text, old, new):
        assert text.count(old) == 1, ('assistant anchor', old[:100], text.count(old))
        return text.replace(old, new)

    mi = structure['files'][main_name]['imports']
    pi = structure['files'][panel_name]['imports']
    fields = structure['files'][main_name]['snapshots'][0]['fields']
    source = (base / 'readable_js/assets' / main_name).read_text(encoding='utf-8')
    store = mi['globalStore']
    handlers = []
    for event in ('key-press', 'key-release'):
        match = re.search(re.escape(mi['listen']) + r'\("'+event+r'", (\w+) => \{\s*([\w$]+)\(\1.payload\)', source)
        assert match, event
        handlers.append(match[2])
    press_source = next(fn for fn in structure['files'][main_name]['functions'] if fn['name']==handlers[0])
    press_text = source[press_source['start']:press_source['end']]
    first_guard = re.search(r'if \(([^\n]+)\) return;', press_text)
    held_guard = re.findall(r'[\w$]+\.has\(e\)', first_guard[1])[-1]
    main = once(main, 'function '+handlers[0]+'(e) {', 'function '+handlers[0]+'(e,__assistantVirtual=false) {')
    main = once(main, first_guard[0], 'if (__assistantVirtual ? '+held_guard+' : ('+first_guard[1]+')) return;')
    chest = min((fn for fn in structure['files'][main_name]['functions'] if 'openChest failed' in source[fn['start']:fn['end']]), key=lambda fn:fn['end']-fn['start'])
    chest_text = source[chest['start']:chest['end']]
    cost = re.search(re.escape(store)+r'\.totalClickCount < ([\w$]+)', chest_text)[1]
    animation = re.search(r'const \w+ = ([\w$]+)\(e\);', chest_text)[1]
    assert 'Wn = pe(() =>' in source and 'Gn = pe(() =>' in source, 'chest readiness contract'
    # Counters, native persistence and logout remain byte-for-byte original.
    # The official installer would replace this executable and lose integrations.
    shared = once(shared, 'function isAppUpdaterEnabled() {', 'function isAppUpdaterEnabled() {\n return false;')
    shared = once(shared, 'function isForceUpdateLocked() {', 'function isForceUpdateLocked() {\n return window.__WUWA_LOCAL_ATLAS__?.assistant?.updateRequired.value === true;')
    shared = once(shared, 'function schedulePreloadAppUiImages() {', '''function schedulePreloadAppUiImages() {
 const route=(window.location.hash||'#/').slice(1).split('?')[0];
 if(!['/','/panel'].includes(route))return;''')
    factory = (project / 'src/assistant_dashboard.js').read_text(encoding='utf-8')+'\n'+(project / 'src/desktop_assistant.js').read_text(encoding='utf-8')
    shared = once(shared, 'window.__WUWA_LOCAL_ATLAS__ = localAtlasController;', factory + '''
window.__WUWA_LOCAL_ATLAS__ = localAtlasController;
localAtlasController.assistant=createDesktopAssistant({ref,window,atlas:localAtlasController,displayName:resolveAssetDisplayName});''')
    shared = once(shared, 'localAtlasController.ready.then(() => { localStartOnlineServices(); return bootstrap(); })',
                  'Promise.all([localAtlasController.ready,localAtlasController.assistant.ready]).then(() => { localStartOnlineServices(); return bootstrap(); })')
    # Record only the original successful server result, before its popup. The
    # recorder catches its own errors and never retries a chest transaction.
    main = once(main, 'const f = '+animation+'(e);', 'const __assistantAttempt=__lg.assistant.beginChest(e);\n        const f = '+animation+'(e);')
    main = once(main, '          '+mi['reportRewardClaimSucc']+'({\n            itemId: M.data.asset_id,',
        '          __lg.assistant.chestSucceeded(__assistantAttempt,M.data);\n          '+mi['reportRewardClaimSucc']+'({\n            itemId: M.data.asset_id,')
    room = fields['currentRoomId']
    members = re.search(r'^([\w$]+)\.value', fields['roomMembers'])[1]+'.value'
    input_room = fields['roomIdInput']
    join_fn = structure['files'][main_name]['cases']['join-room']
    open_settings = re.search(r'class: "settings-btn"[\s\S]{0,300}?onClick: '+re.escape(mi['withModifiers'])+r'\(([\w$]+),',source)[1]
    open_tab = min((fn for fn in structure['files'][main_name]['functions'] if '[panel] open tab failed' in source[fn['start']:fn['end']]), key=lambda fn:fn['end']-fn['start'])['name']
    quit_fn = re.search(r'"tray-quit", \(\) => \{\s*([\w$]+)\(\)', source)[1]
    persist_original = re.search(re.escape(mi['listenPersistClicksBeforeExit'])+r'\(async \(\) => \{\s*([\s\S]+?)\n\s*\}\)',source)[1]
    main = once(main, 'async function '+quit_fn+'() {', 'async function '+quit_fn+'() {\n try{await __lg.assistant.flush();}catch{}')
    code = f'''
{mi['onMounted']}(()=>{{window.setTimeout(()=>__lg.assistant.startMain({{
 total:()=>{store}.cumulativeClickCount,balance:()=>{store}.totalClickCount,
 account:()=>String({store}.userInfo?.cuid||{store}.userInfo?.user_id||{store}.userInfo?.uid||'guest'),
 loggedIn:()=>{store}.isLoggedIn,blocked:()=>__lg.assistant.updateRequired.value,
 press:key=>{handlers[0]}(key,true),release:{handlers[1]},chestCost:{cost},
 chests:()=>({{left:{{remaining:Math.max(0,Bt.value),ready:Wn.value}},right:{{remaining:Math.max(0,Nt.value),ready:Gn.value}},cooldown:1800000,busy:Dn.value||kt.value}}),
 monitors:__assistantMonitors,restoreMonitor:__assistantRestoreMonitor,
 currentMonitor:{mi['currentMonitor']},toast:{mi['showToast']},
 openSettings:{open_settings},
 openView:async view=>{{
   if(__lg.assistant.updateRequired.value)return;
   await {open_tab}(view==='atlas'?'atlas':'settings');
   const send=()=>{mi['invoke$1']}('plugin:event|emit',{{event:'local-assistant-view',payload:view}}).catch(()=>{{}});
   send();window.setTimeout(send,800);window.setTimeout(send,2200);
 }},
 quit:{quit_fn},
 persistOriginal:async()=>{{{persist_original}}},
 listenRoom:callback=>{mi['watch']}([()=>{room},()=>{members}.map(x=>[x.id,x.nickname,x.isOwner]).join('|')],()=>{{
   const owner={members}.find(x=>x.isOwner);if({room})callback(String({room}),owner?.nickname||'').catch(()=>{{}});
 }},{{immediate:true}}),
 listenJoin:callback=>{mi['listen']}('local-assistant-join',event=>callback(String(event.payload))),
 join:async code=>{{{input_room}=code;await {join_fn}();}}
}}).catch(error=>console.error('[assistant]',error)),3000);}});
'''
    main = once(main, 'let __localSaved=null;',code+'\nlet __localSaved=null;')
    monitor_name = next(p.name for p in (base/'readable_js/assets').glob('switchDisplayMonitor-*.js'))
    monitor = (base/'readable_js/assets'/monitor_name).read_text(encoding='utf-8')
    monitor = once(monitor, 'async function Nt() {', 'async function Nt(targetName=null) {')
    monitor = once(monitor, 'if (u.length <= 1)', 'if (!targetName && u.length <= 1)')
    monitor = once(monitor, 'const m = (M + 1) % u.length,', 'if(targetName && (!u.some(x=>x.name===targetName)||w?.name===targetName))return false;\n    const m = targetName ? u.findIndex(x=>x.name===targetName) : (M + 1) % u.length,')
    monitor = once(monitor, 'async function Ht() {', 'async function Ht(targetName=null) {')
    monitor = once(monitor, 'y = Nt();', 'y = Nt(targetName);')
    (frontend/'assets'/monitor_name).write_text(monitor, encoding='utf-8')
    main = 'import {a as __assistantMonitors,n as __assistantRestoreMonitor} from "./'+monitor_name+'";\n'+main
    h=pi['createBaseVNode']
    row=f'''{h}('div',{{class:'setting-item','data-desktop-assistant':'true'}},[{h}('div',{{class:'setting-label'}},[{h}('div',{{class:'setting-title'}},'挂机与统计'),{h}('div',{{class:'setting-sub'}},'后台点击、自动开箱、每日统计、房间历史与版本更新')]),{h}('button',{{class:'setting-btn',type:'button',onClick:()=>__lg.assistant.openPanel()}},'打开')]),'''
    panel = once(panel, h+"('div',{class:'setting-item','data-local-gallery-setting':'true'},[",row+'\n'+h+"('div',{class:'setting-item','data-local-gallery-setting':'true'},[")
    assert panel.count('await ds(), await xt()') == 2, 'panel close lifecycle changed'
    panel = once(panel,'let __panelDisposed=false;',f'''let __assistantViewUnlisten=null;
{pi['onMounted']}(async()=>{{__assistantViewUnlisten=await {pi['listen']}('local-assistant-view',event=>{{
 const view=event.payload;
 if(['overview','rewards','daily'].includes(view))__lg.assistant.openPanel(view).catch(error=>console.error('[assistant-view]',error));
 else if(['atlas','settings'].includes(view))__lg.assistant.closePanel();
}});}});
{pi['onUnmounted']}(()=>{{__assistantViewUnlisten?.();}});
let __panelDisposed=false;''')
    return shared,main,panel
