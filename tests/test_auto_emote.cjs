const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../src/desktop_assistant.js'),'utf8');
let now=100000,editable=true,emissions=0,checks=0,blocked=false,items=[{id:7,src:'emote.png'}],deferContext=null;
const settings={enabled:false,auto_chest:false,auto_emote:true,remember_monitor:false};
const state={settings,monitor:null},queue=[];
const atlas={enabled:{value:false},ready:Promise.resolve(),request:async(route)=>{
 if(route.endsWith('typing-context')){checks++;if(deferContext)await deferContext;return{editable};}return state;
}};
const window={document:{querySelector:()=>null},addEventListener(){},setInterval(){},clearInterval(){},
 setTimeout:(f)=>{queue.push(f);return queue.length;},clearTimeout(){}};
const context=vm.createContext({window,Date:class extends Date{static now(){return now;}},console});
vm.runInContext(source+';globalThis.make=createDesktopAssistant;',context);
const a=context.make({window,ref:value=>({value}),atlas});
async function key(k){await a.physicalKey(k);a.physicalRelease(k);now+=100;}
async function burst(){for(const k of ['a','b'])await key(k);}
(async()=>{
 await a.startMain({total:()=>0,balance:()=>0,account:()=>'',loggedIn:()=>true,blocked:()=>blocked,
 currentMonitor:async()=>null,listenRoom(){},listenJoin:async()=>{},emotes:()=>items,
 sendEmote:item=>{assert.equal(item.id,7);emissions++;},press(){},release(){}});
 // No timer or virtual F24 handler can send an emote; there is no idle emitter.
 await burst();assert.equal(emissions,1);await burst();assert.equal(emissions,1);
 now+=16000;await key('Shift');await key('F24');await key('ArrowLeft');await key('MouseLeft');assert.equal(emissions,1);
 await a.physicalKey('ControlLeft');await burst();a.physicalRelease('ControlLeft');assert.equal(emissions,1);
 editable=false;now+=3000;await burst();assert.equal(emissions,1);
 editable=true;now+=3000;await burst();assert.equal(emissions,2);
 now+=16000;for(let i=0;i<10;i++)await a.physicalKey('a');a.physicalRelease('a');assert.equal(emissions,2);
 settings.auto_emote=false;now+=16000;await burst();assert.equal(emissions,2);
 settings.auto_emote=true;blocked=true;await burst();assert.equal(emissions,2);blocked=false;
 items=[];now+=3000;await burst();assert.equal(emissions,2);items=[{id:7,src:'emote.png'}];
 // The same feature works without automatic clicking, and in both atlas modes.
 atlas.enabled.value=true;now+=16000;await burst();assert.equal(emissions,3);
 atlas.enabled.value=false;now+=16000;await burst();assert.equal(emissions,4);
 // A slow focus reply must not produce an idle bubble after typing stopped.
 now+=16000;let resolve;deferContext=new Promise(r=>resolve=r);
 const pending=burst();for(let i=0;i<20;i++)await Promise.resolve();
 now+=1000;resolve();await pending;deferContext=null;assert.equal(emissions,4);
 assert(checks>=4);console.log('auto emote: editable physical typing only, modifiers/mouse/F24/idle/held keys excluded, disabled/update/no-selection guarded, throttle and both modes passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
