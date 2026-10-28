/* Main-renderer driver. No signal enters the Windows input queue. */
function createDesktopAssistant({ref, window, atlas, displayName=(type,name)=>name}) {
  const VERSION='1.2', updateRequired=ref(false);
  const state=ref({settings:{enabled:false,speed:5,auto_chest:false,threshold:1000,remember_monitor:true}});
  const request=(action,body={})=>atlas.request('/assistant/'+action,body);
  const ready=atlas.ready.then(()=>request('state')).then(v=>{state.value=v;updateRequired.value=!!v.update_required;});
  let started=false,disposed=false,timer=null,mainDependencies=null,sent=0,confirmed=0,lastObserve=0;
  let dashboard=null,updateDialog=null,autoSide=null,autoUntil=0,flushing=null;
  const readyButtons=new Map(),retryAfter=new Map();
  const OUTBOX='wuwatappo-confirmed-rewards-v2';
  let outbox=[];
  try{outbox=JSON.parse(window.localStorage?.getItem(OUTBOX)||'[]');if(!Array.isArray(outbox))outbox=[];}catch{}
  function saveOutbox(){try{window.localStorage?.setItem(OUTBOX,JSON.stringify(outbox));}catch{}}
  async function drainRewards(){
    while(outbox.length){
      try{await request('reward',{reward:outbox[0]});outbox.shift();saveOutbox();}
      catch(error){state.value={...state.value,history_error:'奖励记录待补存：'+error.message};return;}
    }
  }
  function beginChest(side){
    const source=autoSide===side&&Date.now()<autoUntil?'automatic':'manual';autoSide=null;
    return {id:window.crypto?.randomUUID?.()||Date.now()+'-'+Math.random().toString(36).slice(2),side,source};
  }
  function chestSucceeded(attempt,result){
    try{
      if(!result?.asset_name||!result.asset_type||!(Number(result.click_consume)>0))return;
      const reward={...attempt,confirmed:true,asset_id:result.asset_id,asset_type:result.asset_type,
        asset_name:String(result.asset_name),name:displayName(result.asset_type,result.asset_name),
        rarity:String(result.rarity_type||''),cost:Number(result.click_consume)};
      outbox.push(reward);saveOutbox();
    }catch(error){console.warn('[assistant] reward history pending',error);}
  }
  function observation(d){return {total:Number(d.total()),balance:Number(d.balance()),account:d.account(),
    logged_in:!!d.loggedIn(),chests:d.chests?.()||{}};}
  async function flush(){
    if(!mainDependencies)return;
    if(flushing)return flushing;
    flushing=(async()=>{
      await mainDependencies.persistOriginal?.();
      const body={...observation(mainDependencies),flush:true,sent,confirmed};sent=confirmed=0;
      await request('observe',body);await drainRewards();
    })().finally(()=>{flushing=null;});
    return flushing;
  }
  async function flushBeforeSwitch(){
    if(started)return flush();
    const value=await request('flush-request'),generation=value.flush_generation;
    for(let i=0;i<20;i++){
      await new Promise(resolve=>window.setTimeout(resolve,100));
      if((await request('state')).flush_done>=generation)return;
    }
  }
  function autoChest(d){
    const settings=state.value.settings;
    // Physical activity pauses virtual tapping only. This is an in-renderer
    // button click, so it needs no mouse movement, focus or OS input event.
    if(!settings.auto_chest||!d.loggedIn()||updateRequired.value||d.blocked()){readyButtons.clear();return;}
    for(const side of ['left','right']){
      const button=window.document.querySelector('.reward-anchor--'+side+' button.reward-btn'),now=Date.now();
      if(!button||button.disabled||!button.isConnected||button.getClientRects().length===0||
        Number(d.balance())<Math.max(settings.threshold,d.chestCost)){readyButtons.delete(side);continue;}
      if(!readyButtons.has(side))readyButtons.set(side,now);
      if(now-readyButtons.get(side)<2000||now<(retryAfter.get(side)||0))continue;
      retryAfter.set(side,now+30000);readyButtons.delete(side);autoSide=side;autoUntil=now+1000;
      button.click();break;
    }
  }
  function showRequiredUpdate(result){
    updateRequired.value=result.required===true;
    if(!updateRequired.value)return;
    if(updateDialog){updateDialog.update(result);return;}
    updateDialog=createAssistantUpdateGate({window,result,
      retry:async()=>{const r=await atlas.request('/update/check',{});showRequiredUpdate(r);return r;},
      install:async()=>atlas.request('/update/install',{}),
      quit:async()=>{if(started){await flush();await mainDependencies.quit();}else await request('quit');}});
  }
  async function startMain(d){
    if(started)return;started=true;mainDependencies=d;
    await ready;state.value=await request('renderer-start');
    async function loop(){
      if(disposed)return;
      let delay=1000;
      try{
        const now=Date.now(),body={sent,confirmed};sent=confirmed=0;
        if(now-lastObserve>=1000){Object.assign(body,observation(d));lastObserve=now;await drainRewards();}
        const result=await request('tick',body);state.value={...state.value,...result};
        if(result.update_required&&!updateRequired.value)showRequiredUpdate(await atlas.request('/update/status',{}));
        if(result.flush_generation){await flush();await request('flush-ack',{generation:result.flush_generation});}
        if(result.quit){await flush();await d.quit();return;}
        if(typeof result.open_settings==='string')await d.openView?.(result.open_settings);
        else if(result.open_settings)await d.openSettings?.();
        if(result.settings.enabled&&!updateRequired.value)delay=50;
        if(result.allowed&&!updateRequired.value&&!d.blocked()){
          const before=Number(d.total());
          try{d.press('F24');}finally{d.release('F24');}
          sent=1;confirmed=Number(d.total())>before?1:0;
        }
        autoChest(d);
      }catch(error){state.value={...state.value,error:String(error.message||error)};delay=1500;}
      timer=window.setTimeout(loop,delay);
    }
    timer=window.setTimeout(loop,1000);
    const saved=state.value.monitor;
    if(state.value.settings.remember_monitor&&saved?.name){
      try{const monitors=await d.monitors();if(monitors.filter(m=>m.name===saved.name).length===1)await d.restoreMonitor(saved.name);}
      catch(error){state.value={...state.value,error:'屏幕恢复：'+error.message};}
    }
    let monitorName=saved?.name;
    async function rememberMonitor(){
      if(!state.value.settings.remember_monitor)return;
      try{const m=await d.currentMonitor();if(m?.name&&m.name!==monitorName){await request('monitor',{monitor:{name:m.name,position:m.position,size:m.size}});monitorName=m.name;}}catch{}
    }
    await rememberMonitor();window.setInterval(rememberMonitor,30000);
    await atlas.request('/update/healthy',{version:VERSION});
    d.listenRoom(async(code,host)=>{if(!atlas.enabled.value&&code)await request('room',{code,host});});
    await d.listenJoin(async code=>{if(atlas.enabled.value){d.toast('本地全图鉴开启时无法进入联机');return;}if(!updateRequired.value)await d.join(code);});
    window.addEventListener('pagehide',()=>{disposed=true;window.clearTimeout(timer);});
  }
  function closePanel(){dashboard?.close();dashboard=null;}
  async function openPanel(initialTab='overview'){
    if(dashboard){dashboard.showTab(initialTab);dashboard.focus();return;}
    await ready;
    dashboard=createAssistantDashboard({window,version:VERSION,atlas,initialTab,
      getState:async()=>{const v=await request('state');state.value=v;return v;},
      configure:async changes=>{state.value=await request('configure',{settings:changes});return state.value;},
      reset:()=>request('reset'),join:code=>window.__TAURI_INTERNALS__.invoke('plugin:event|emit',{event:'local-assistant-join',payload:code}),
      favorite:(code,favorite)=>request('favorite',{code,favorite}),onClose:()=>{dashboard=null;}});
  }
  async function pollPolicy(){
    if(disposed)return;
    try{const result=await atlas.request('/update/status',{});showRequiredUpdate(result);}catch{}
    if(!disposed)window.setTimeout(pollPolicy,15000);
  }
  ready.then(pollPolicy).catch(()=>{});
  window.addEventListener('pagehide',()=>{disposed=true;closePanel();});
  return {ready,state,updateRequired,startMain,openPanel,closePanel,flush,flushBeforeSwitch,beginChest,chestSucceeded};
}
