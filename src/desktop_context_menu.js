/* Keep menu tracking off Tauri's UI thread and dispatch only after dismissal. */
function createDesktopContextMenu(d){
  let busy=false;
  async function model(actions){
    const settings=d.settings(),labels=await d.labels(),handlers=new Map();
    const item=(key,text,action,checked)=>{handlers.set(key,action);return{key,text,...(typeof checked==='boolean'?{checked}:{})};};
    const emit=(event,payload=null)=>d.invoke('plugin:event|emit',{event,payload});
    const items=[
      ...[['bag',labels.openBag||'背包'],['atlas',labels.openAtlas||'图鉴'],['exchange',labels.openExchange||'合成'],['room',labels.openRoom||'联机']].map(([key,text])=>item(key,text,()=>actions.openTab(key))),
      {separator:true},item('console','控制台',actions.openConsole),item('setting',labels.dockSettings||'设置',()=>actions.openTab('setting')),
      item('drag',labels.windowPassthrough||'禁用拖动',()=>emit('tray-toggle-window-passthrough'),!!settings.windowPassthrough),
      item('game',labels.gameMode||'游戏模式',()=>emit('tray-toggle-game-mode'),!!settings.gameMode),
      {text:labels.windowOpacity||'桌宠不透明度',items:[25,50,75,100].map(value=>item('opacity-'+value,value+'%',()=>emit('tray-set-window-opacity',value),settings.windowOpacity===value))},
      {text:labels.windowSize||'桌宠大小',items:[50,75,100,125,150,175,200].map(value=>item('scale-'+value,value+'%',()=>emit('tray-set-pet-scale',value),settings.petScale===value))},
      item('hide',d.visible()?labels.hidePet||'隐藏桌宠':labels.showPet||'显示桌宠',()=>emit('tray-toggle-pet-visibility')),
      {separator:true},item('restart',labels.restart||'重启应用',()=>emit('tray-restart')),item('quit',labels.quit||'退出应用',()=>emit('tray-quit'))
    ];
    return{items,handlers};
  }
  return{
    isOpen:()=>busy,
    async initialize(actions){
      const{items}=await model(actions),index=items.findIndex(item=>item.key==='console');
      if(index<0||items[index+1]?.key!=='setting')throw Error('Console menu order mismatch');
      await d.report?.({kind:'context_menu_setup',ok:true,backend:'host-win32',console_before_settings:true});
    },
    async popup(x,y,actions){
      if(busy)return;busy=true;
      let selected,handlers,cleaned=false;
      try{
        await actions.before?.();
        const view=await model(actions);handlers=view.handlers;
        selected=(await d.request('/assistant/context-menu',{items:view.items})).action;
      }finally{
        try{await actions.after?.();cleaned=true;}finally{busy=false;}
      }
      if(cleaned&&selected&&handlers.has(selected)){
        await handlers.get(selected)();
        await d.report?.({kind:'context_menu_dispatch',action:selected,completed:true});
      }
    }
  };
}
