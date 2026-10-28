// Regression: sustained physical input used to reset the chest delay forever.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../src/desktop_assistant.js'),'utf8');
async function scenario({local=false,enabled=false,autoChest=true,balance=2000,loggedIn=true,blocked=false,disabled=false,hidden=false}={}){
  let now=100000,count=0,quiet=false,id=0;
  const tasks=[],clicks=[],settings={enabled,speed:10,auto_chest:autoChest,threshold:1000,remember_monitor:false};
  const value={settings,session:0,confirmed:0,rooms:[],rewards:[]};
  const buttons={};
  for(const side of ['left','right'])buttons[side]={disabled,isConnected:true,getClientRects:()=>hidden?[]:[{}],click(){clicks.push({side,at:now,quiet});this.disabled=true;}};
  const win={document:{querySelector:selector=>buttons[selector.includes('--left')?'left':'right']},addEventListener(){},
    setTimeout(fn,delay){const task={id:++id,fn,at:now+delay};tasks.push(task);return task.id;},
    clearTimeout(which){const task=tasks.find(t=>t.id===which);if(task)tasks.splice(tasks.indexOf(task),1);},setInterval(){},clearInterval(){}};
  const atlas={enabled:{value:local},ready:Promise.resolve(),request:async(route,body)=>{
    if(route==='/assistant/tick')return {allowed:settings.enabled&&quiet,quiet,settings};
    if(route==='/update/status')return {required:false};
    return value;
  }};
  const context=vm.createContext({window:win,Date:class extends Date{static now(){return now;}},console,Map,Math,Number,Promise});
  vm.runInContext(source+';globalThis.make=createDesktopAssistant;',context);
  const assistant=context.make({window:win,ref:value=>({value}),atlas});
  await assistant.startMain({total:()=>count,balance:()=>balance,account:()=> 'test-account',loggedIn:()=>loggedIn,blocked:()=>blocked,
    press(){assert(quiet,'virtual tapping must pause during input');},release(){count++;},chestCost:1000,
    currentMonitor:async()=>null,listenRoom(){},listenJoin:async()=>{}});
  async function advance(ms){const end=now+ms;for(;;){tasks.sort((a,b)=>a.at-b.at);if(!tasks.length||tasks[0].at>end)break;const task=tasks.shift();now=task.at;await task.fn();}now=end;}
  return {advance,clicks,assistant,get count(){return count;},setQuiet:value=>quiet=value};
}
(async()=>{
  for(const local of [false,true])for(const enabled of [false,true]){
    const test=await scenario({local,enabled});
    await test.advance(2900);assert.equal(test.clicks.length,0,'original two-second ready delay is retained');
    await test.advance(1200);assert.deepEqual(test.clicks.map(x=>x.side),['left','right']);
    assert(test.clicks.every(x=>x.quiet===false),'both chests open during sustained physical input');
    assert.equal(test.count,0,'physical input still prevents virtual tapping');
    await test.advance(30000);assert.equal(test.clicks.length,2,'disabled original buttons prevent repeat opening');
  }
  for(const guard of [{autoChest:false},{loggedIn:false},{balance:999},{blocked:true},{disabled:true},{hidden:true}]){
    const test=await scenario(guard);await test.advance(5000);assert.equal(test.clicks.length,0,JSON.stringify(guard));
  }
  const protect=await scenario({enabled:true,autoChest:false});
  await protect.advance(1000);assert.equal(protect.count,0);
  protect.setQuiet(true);await protect.advance(100);assert(protect.count>0);
  protect.setQuiet(false);const before=protect.count;await protect.advance(1000);assert.equal(protect.count,before);
  console.log('chest input regression passed: both modes, auto-click on/off, sustained input, 2s delay, both chests, original guards, tapping pause/resume');
})().catch(error=>{console.error(error);process.exitCode=1;});
