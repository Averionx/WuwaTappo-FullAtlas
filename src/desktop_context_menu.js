/* Native Tauri menu, using the application's existing SDK and action events. */
function createDesktopContextMenu(d){
  let previous=null,channels=[];
  async function build(actions){
    const invoke=d.invoke,settings=d.settings(),labels=await d.labels();
    if(previous!==null){await invoke('plugin:resources|close',{rid:previous});previous=null;channels=[];}
    const channel=new d.Channel(id=>{
      const action=handlers.get(id);
      Promise.resolve(action?.()).catch(error=>console.warn('[context-menu] action',error));
    });channels.push(channel);
    const handlers=new Map();
    function item(key,text,action,checked){
      const id='fullatlas-'+key;handlers.set(id,action);
      return {id,text,enabled:true,handler:channel,...(typeof checked==='boolean'?{checked}: {})};
    }
    const emit=(event,payload=null)=>invoke('plugin:event|emit',{event,payload});
    const items=[
      ...[['bag',labels.openBag||'背包'],['atlas',labels.openAtlas||'图鉴'],['exchange',labels.openExchange||'合成'],['room',labels.openRoom||'联机']].map(([key,text])=>item(key,text,()=>actions.openTab(key))),
      {item:'Separator'},
      item('console','控制台',actions.openConsole),
      item('setting',labels.dockSettings||'设置',()=>actions.openTab('setting')),
      item('drag',labels.windowPassthrough||'禁用拖动',()=>emit('tray-toggle-window-passthrough'),!!settings.windowPassthrough),
      item('game',labels.gameMode||'游戏模式',()=>emit('tray-toggle-game-mode'),!!settings.gameMode),
      {text:labels.windowOpacity||'桌宠不透明度',items:[25,50,75,100].map(value=>item('opacity-'+value,value+'%',()=>emit('tray-set-window-opacity',value),settings.windowOpacity===value))},
      {text:labels.windowSize||'桌宠大小',items:[50,75,100,125,150,175,200].map(value=>item('scale-'+value,value+'%',()=>emit('tray-set-pet-scale',value),settings.petScale===value))},
      item('hide',d.visible()?labels.hidePet||'隐藏桌宠':labels.showPet||'显示桌宠',()=>emit('tray-toggle-pet-visibility')),
      {item:'Separator'},item('restart',labels.restart||'重启应用',()=>emit('tray-restart')),
      item('quit',labels.quit||'退出应用',()=>emit('tray-quit'))
    ];
    const noAction=new d.Channel();channels.push(noAction);
    const [rid]=await invoke('plugin:menu|new',{kind:'Menu',options:{items},handler:noAction});previous=rid;
    return rid;
  }
  return {
    async initialize(actions){
      try{
        const rid=await build(actions),entries=await d.invoke('plugin:menu|items',{rid,kind:'Menu'});
        const ids=entries.map(entry=>entry[1]);
        const index=ids.indexOf('fullatlas-console');
        if(index<0||ids[index+1]!=='fullatlas-setting')throw Error('Native console menu order mismatch');
        await d.report?.({kind:'context_menu_setup',ok:true,console_before_settings:true});
      }catch(error){await d.report?.({kind:'context_menu_setup',ok:false,error:String(error)});throw error;}
    },
    async popup(x,y,actions){
      const rid=await build(actions);
      await d.invoke('plugin:menu|popup',{rid,kind:'Menu',window:null,at:{Logical:{x,y}}});
    }
  };
}
