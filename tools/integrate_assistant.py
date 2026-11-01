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
    # Only the original native input listener reaches this hook. Virtual F24
    # signals call the handler directly and can never trigger emotes.
    native_call=handlers[0]+'(e.payload)'
    main=once(main,native_call,native_call+'; __lg.assistant.physicalKey(e.payload)')
    native_release=handlers[1]+'(e.payload)'
    main=once(main,native_release,native_release+'; __lg.assistant.physicalRelease(e.payload)')
    chest = min((fn for fn in structure['files'][main_name]['functions'] if 'openChest failed' in source[fn['start']:fn['end']]), key=lambda fn:fn['end']-fn['start'])
    chest_text = source[chest['start']:chest['end']]
    cost = re.search(re.escape(store)+r'\.totalClickCount < ([\w$]+)', chest_text)[1]
    animation = re.search(r'const \w+ = ([\w$]+)\(e\);', chest_text)[1]
    busy=re.search(r'if \(([\w$]+)\.value \|\| ([\w$]+)\.value\) return;',chest_text)
    assert busy,'chest busy contract'
    remaining=[]
    for ready_name in ('Wn','Gn'):
        remaining.append(re.search(ready_name+r' = '+re.escape(mi['computed'])+r'\(\(\) =>[^\n]+: ([\w$]+)\.value <= 0\)',source)[1])
    emote_fn=min((fn for fn in structure['files'][main_name]['functions'] if mi['reportSendSticker']+'({' in source[fn['start']:fn['end']]),key=lambda fn:fn['end']-fn['start'])
    emote_text=source[emote_fn['start']:emote_fn['end']]
    assert 'e.src' in emote_text and '.push({' in emote_text,'manual emote rendering contract'
    emote_items=re.search(r'"emote-items": ([\w$]+)\.value,\s*onSelect: '+re.escape(emote_fn['name']),source)[1]
    emote_url=re.search(r'"asset-url": ([\w$]+),\s*"emote-items": '+re.escape(emote_items),source)[1]
    sync_call=re.search(re.escape(store)+r'\.isLoggedIn && ([\w$]+)\(e.id\);',emote_text)
    assert sync_call,'original room emote send contract'
    # Local-only selections must never be sent as account-owned room items.
    main=once(main,sync_call[0],store+'.isLoggedIn && !__lg.enabled.value && '+sync_call[1]+'(e.id);')
    native_invoke=mi.get('invoke$1',mi.get('invoke'))
    assert 'Wn = pe(() =>' in source and 'Gn = pe(() =>' in source, 'chest readiness contract'
    # Counters, native persistence and logout remain byte-for-byte original.
    # The official installer would replace this executable and lose integrations.
    shared = once(shared, 'function isAppUpdaterEnabled() {', 'function isAppUpdaterEnabled() {\n return false;')
    shared = once(shared, 'function isForceUpdateLocked() {', 'function isForceUpdateLocked() {\n return window.__WUWA_LOCAL_ATLAS__?.assistant?.updateRequired.value === true;')
    shared = once(shared, 'function schedulePreloadAppUiImages() {', '''function schedulePreloadAppUiImages() {
 const route=(window.location.hash||'#/').slice(1).split('?')[0];
 if(!['/','/panel'].includes(route))return;''')
    factory = (project / 'src/assistant_dashboard.js').read_text(encoding='utf-8')+'\n'+(project / 'src/desktop_assistant.js').read_text(encoding='utf-8')+'\n'+(project/'src/desktop_context_menu.js').read_text(encoding='utf-8')
    shared = once(shared, 'window.__WUWA_LOCAL_ATLAS__ = localAtlasController;', factory + '''
window.__WUWA_LOCAL_ATLAS__ = localAtlasController;
localAtlasController.assistant=createDesktopAssistant({ref,window,atlas:localAtlasController,nativeWindow:()=>getCurrentWindow(),displayName:resolveAssetDisplayName});
localAtlasController.contextMenu=createDesktopContextMenu({invoke,request:(path,body)=>localAtlasController.request(path,body),settings:loadDesktopCatSettings,visible:()=>petDockVisibleForMenu,labels:async()=>getNativeMenuLabels(formatShortcut((await getAppShortcuts()).togglePet)),report:details=>localAtlasController.request('/diagnostic',details)});''')
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
    popup=re.search(r'await ([\w$]+)\("popup_main_dock_context_menu", \{\s*x: ([\w$]+),\s*y: ([\w$]+)\s*\}\)',main)
    assert popup,'native dock menu anchor changed'
    popup_function=min((fn for fn in structure['files'][main_name]['functions'] if '"popup_main_dock_context_menu"' in source[fn['start']:fn['end']]),key=lambda fn:fn['end']-fn['start'])
    popup_source=source[popup_function['start']:popup_function['end']]
    cancel_gesture=re.search(r'finally\s*\{[\s\S]*?,\s*([\w$]+)\(\),\s*[\w$]+ && window\.setTimeout',popup_source)[1]
    assert cancel_gesture in re.findall(r'cancelDockPointerGesture:\s*([\w$]+)',source),'dock cleanup binding changed'
    context_actions=f"{{openTab:{open_tab},openConsole:async()=>{{await {open_tab}('console');const visible=await {native_invoke}('plugin:window|is_visible',{{label:'panel'}});await __lg.request('/diagnostic',{{kind:'context_console_open',visible}});}},before:async()=>{{await {cancel_gesture}();await {native_invoke}('set_main_swallow_mouse',{{enabled:false}});}},after:async()=>{{await {native_invoke}('set_main_swallow_mouse',{{enabled:false}});await {cancel_gesture}();}}}}"
    main=once(main,popup[0],f'''try{{await __lg.contextMenu.popup({popup[2]},{popup[3]},{context_actions});}}
            catch(error){{console.warn('[context-menu] native extension unavailable',error);{popup[0]};}}''')
    quit_fn = re.search(r'"tray-quit", \(\) => \{\s*([\w$]+)\(\)', source)[1]
    persist_original = re.search(re.escape(mi['listenPersistClicksBeforeExit'])+r'\(async \(\) => \{\s*([\s\S]+?)\n\s*\}\)',source)[1]
    main = once(main, 'async function '+quit_fn+'() {', 'async function '+quit_fn+'() {\n try{await __lg.assistant.flush();}catch{}')
    tab_source=next(fn for fn in structure['files'][main_name]['functions'] if fn['name']==open_tab)
    tab_text=source[tab_source['start']:tab_source['end']]
    lock_guard=re.search(r'if \(([\w$]+)\(\)\) \{',tab_text)
    assert lock_guard,'panel update-lock guard'
    main=once(main,tab_text[:tab_text.index('rt.value')],tab_text[:tab_text.index('rt.value')].replace(lock_guard[0], 'if (e !== "console" && '+lock_guard[1]+'()) {'))
    panel_visible=re.search(r'([\w$]+)\.value = !0;',tab_text)[1]
    close_panel=min((fn for fn in structure['files'][main_name]['functions'] if '[panel] close failed' in source[fn['start']:fn['end']]),key=lambda fn:fn['end']-fn['start'])['name']
    code = f'''
{mi['onMounted']}(()=>{{window.setTimeout(()=>__lg.contextMenu.initialize({context_actions}).catch(error=>console.warn('[context-menu] initialize',error)),1500);}});
{mi['onMounted']}(()=>{{window.setTimeout(()=>__lg.assistant.startMain({{
 total:()=>{store}.cumulativeClickCount,balance:()=>{store}.totalClickCount,
 account:()=>String({store}.userInfo?.cuid||{store}.userInfo?.user_id||{store}.userInfo?.uid||'guest'),
 loggedIn:()=>{store}.isLoggedIn,blocked:()=>__lg.assistant.updateRequired.value||__lg.contextMenu.isOpen(),
 press:key=>{handlers[0]}(key,true),release:{handlers[1]},chestCost:{cost},
 chests:()=>({{left:{{remaining:Math.max(0,{remaining[0]}.value),ready:Wn.value}},right:{{remaining:Math.max(0,{remaining[1]}.value),ready:Gn.value}},cooldown:1800000,busy:{busy[1]}.value||{busy[2]}.value}}),
 emotes:()=>{emote_items}.value.map(item=>({{...item,src:{emote_url}('emote/'+item.name)}})),
 sendEmote:item=>{emote_fn['name']}(item),
 monitors:__assistantMonitors,restoreMonitor:__assistantRestoreMonitor,
 currentMonitor:{mi['currentMonitor']},toast:{mi['showToast']},
 showUpdate:async result=>{{
   if({panel_visible}.value)await {close_panel}();
   let visible=false;
   try{{visible=await {native_invoke}('plugin:window|is_visible',{{label:'update'}});}}catch{{}}
   if(!visible)await {native_invoke}('open_update_window',{{detail:{{currentVersion:result.current_version,newVersion:result.version||result.current_version,notes:'WuwaTappo全图鉴版更新',requiresManualDownload:false}}}});
 }},
 openSettings:{open_settings},
 openView:async view=>{{
   if(__lg.assistant.updateRequired.value)return;
   await {open_tab}(view==='atlas'?'atlas':'setting');
   const send=()=>{native_invoke}('plugin:event|emit',{{event:'local-assistant-view',payload:view}}).catch(()=>{{}});
   send();window.setTimeout(send,800);window.setTimeout(send,2200);
 }},
 quit:{quit_fn},
 persistOriginal:async()=>{{{persist_original}}},
 listenRoom:callback=>{mi['watch']}([()=>{room},()=>{members}.map(x=>[x.id,x.nickname,x.isOwner]).join('|')],()=>{{
   const owner={members}.find(x=>x.isOwner);callback(String({room}||''),owner?.nickname||'').catch(()=>{{}});
 }},{{immediate:true}}),
 listenJoin:callback=>{mi['listen']}('local-assistant-join',event=>callback(String(event.payload))),
 join:async code=>{{{input_room}=code;await {join_fn}();}}
}}).catch(error=>console.error('[assistant]',error)),3000);}});
'''
    main = once(main, 'let __localSaved=null;',code+'\nlet __localSaved=null;')
    monitor_name = next(p.name for p in (base/'readable_js/assets').glob('switchDisplayMonitor-*.js'))
    monitor = (base/'readable_js/assets'/monitor_name).read_text(encoding='utf-8')
    tab_guard='return e === "bag" || e === "atlas" || e === "exchange" || e === "room" || e === "setting"'
    monitor=once(monitor,tab_guard,tab_guard+' || e === "console"')
    monitor=once(monitor,'return Fe() ? await u("is_elevated_autostart_enabled") : await X()',
                 'return (await window.__WUWA_LOCAL_ATLAS__.request("/startup",{action:"status"})).enabled')
    monitor=once(monitor,'async function _n(e) {','async function _n(e) {\n return window.__WUWA_LOCAL_ATLAS__.request("/startup",{action:e?"enable":"disable"});')
    switch_match=re.search(r'const ([\w$]+) = \(([\w$]+) \+ 1\) % ([\w$]+)\.length,',monitor)
    assert switch_match,'monitor cycle contract'
    idx,old_idx,monitors=switch_match.groups()
    switch_fn=list(re.finditer(r'async function ([\w$]+)\(\) \{',monitor[:switch_match.start()]))[-1][1]
    prefix=monitor[monitor.rfind('async function ',0,switch_match.start()):switch_match.start()]
    current_match=re.search(r'([\w$]+)\?\.name',prefix) or re.search(r'const ([\w$]+) = await [\w$]+\([^\n]+\);\s*let '+re.escape(old_idx),prefix)
    assert current_match,'current monitor contract'
    current=current_match[1]
    monitor=once(monitor,'async function '+switch_fn+'() {','async function '+switch_fn+'(targetName=null) {')
    monitor=once(monitor,f'if ({monitors}.length <= 1)',f'if (!targetName && {monitors}.length <= 1)')
    monitor=once(monitor,switch_match[0],f'if(targetName && (!{monitors}.some(x=>x.name===targetName)||{current}?.name===targetName))return false;\n const {idx} = targetName ? {monitors}.findIndex(x=>x.name===targetName) : ({old_idx} + 1) % {monitors}.length,')
    call=re.search(r'([\w$]+) = '+re.escape(switch_fn)+r'\(\);',monitor)
    wrapper=list(re.finditer(r'async function ([\w$]+)\(\) \{',monitor[:call.start()]))[-1][1]
    monitor=once(monitor,'async function '+wrapper+'() {','async function '+wrapper+'(targetName=null) {')
    monitor=once(monitor,call[0],call[1]+' = '+switch_fn+'(targetName);')
    (frontend/'assets'/monitor_name).write_text(monitor, encoding='utf-8')
    export_text=monitor[monitor.rfind('export {'):]
    exported=dict(re.findall(r'([\w$]+) as ([\w$]+)',export_text))
    if structure['shared']=='index-CuzHFfJW.js':
        available=re.search(r'async function ([\w$]+)\(\) \{\s*const ([\w$]+) = await [\w$]+\(\),\s*([\w$]+) = await [\w$]+\(\);\s*return [\w$]+\(\2, \3\)',monitor)[1]
        available_export=exported[available]
    else:
        available_export='a'
    main = 'import {'+available_export+' as __assistantMonitors,'+exported[wrapper]+' as __assistantRestoreMonitor} from "./'+monitor_name+'";\n'+main
    h=pi['createBaseVNode']
    row=f'''{h}('div',{{class:'setting-item','data-desktop-assistant':'true'}},[{h}('div',{{class:'setting-label'}},[{h}('div',{{class:'setting-title'}},'挂机与统计'),{h}('div',{{class:'setting-sub'}},'后台点击、自动开箱、每日统计、房间历史与版本更新')]),{h}('button',{{class:'setting-btn',type:'button',onClick:()=>__lg.assistant.openPanel()}},'打开')]),'''
    assert len(re.findall(r'await [\w$]+\(\), await [\w$]+\(\)',panel))>=2, 'panel close lifecycle changed'
    panel = once(panel,'let __panelDisposed=false;',f'''let __assistantViewUnlisten=null;
{pi['onMounted']}(async()=>{{__assistantViewUnlisten=await {pi['listen']}('local-assistant-view',event=>{{
 const view=event.payload;
 if(['overview','rewards','daily'].includes(view))__lg.assistant.openPanel(view).catch(error=>console.error('[assistant-view]',error));
 else if(['atlas','settings'].includes(view))__lg.assistant.closePanel();
}});}});
{pi['onUnmounted']}(()=>{{__assistantViewUnlisten?.();}});
let __panelDisposed=false;''')
    return shared,main,panel
