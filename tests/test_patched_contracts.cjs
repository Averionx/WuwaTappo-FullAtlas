// Exercise the actual generated original handlers and modified store methods.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const acorn=require('../tools/acorn.cjs'),build=path.resolve(__dirname,'../build');
const manifest=JSON.parse(fs.readFileSync(path.join(build,'build_manifest_v2.json'),'utf8'));
const main=fs.readFileSync(path.join(build,'frontend_v2/assets',manifest.main),'utf8');
const shared=fs.readFileSync(path.join(build,'frontend_v2/assets',manifest.shared),'utf8');
function walk(n,visit){if(!n||typeof n!=='object')return;if(n.type)visit(n);for(const [k,v] of Object.entries(n)){if(k==='start'||k==='end')continue;if(Array.isArray(v))v.forEach(x=>walk(x,visit));else if(v?.type)walk(v,visit);}}
function find(text,match){const found=[];walk(acorn.parse(text,{ecmaVersion:'latest',sourceType:'module'}),n=>{if(match(n))found.push(n);});assert(found.length);return found;}
const press=find(main,n=>n.type==='FunctionDeclaration'&&main.slice(n.start,n.end).includes('__assistantVirtual ?'))[0];
const release=find(main,n=>n.type==='FunctionDeclaration'&&n.id.name==='Nc')[0];
let hotkeys=0,animations=0,count=0,localTaps=0,nativeWrites=0;const savedCounts=[];
const atlas={enabled:{value:false},normalCumulative:()=>1008,normalPending:()=>8,assistant:{local:{value:{total:99999,balance:333}},incrementLocal(){localTaps++;}},checkInvoke(){}};
const context=vm.createContext({window:{__WUWA_LOCAL_ATLAS__:atlas,__TAURI_INTERNALS__:{invoke:async(e,t)=>{nativeWrites++;savedCounts.push(t.count);return 7;}}},
 Fs:()=>true,Ls:()=>true,Za:()=>true,Ie:()=>false,ty:()=>true,ry:()=>true,Iv:()=>true,
 dc:()=>hotkeys++,Sh:()=>hotkeys++,Mv:()=>hotkeys++,qr:new Set(),Do:false,Bs:()=>false,
 se:{value:''},Yo:()=>animations++,ma:new Set(),A:{incrementLocalClickCount(){count++;}},ql:()=>animations++,
 isFrozenClickCount:()=>false,clampClickCountSum:n=>n,parseSafeClickCount:n=>n});
vm.runInContext(main.slice(press.start,press.end)+'\n'+main.slice(release.start,release.end),context);
vm.runInContext(`${press.id.name}('F24',true);Nc('F24');`,context);
assert.equal(count,1);assert.equal(hotkeys,0);assert.equal(animations,2);
vm.runInContext(`${press.id.name}('F24');Nc('F24');`,context);
assert.equal(count,2);assert.equal(hotkeys,3);
const methods={};
for(const name of ['totalClickCount','cumulativeClickCount','incrementLocalClickCount']){
 const prop=find(shared,n=>n.type==='Property'&&n.key?.name===name&&shared.slice(n.start,n.end).includes('localClickCount'))[0];
 methods[name]=vm.runInContext('({'+shared.slice(prop.start,prop.end)+'})',context)[name];
}
const store={serverClickTotal:1000,serverClickConsume:100,serverClickSpend:20,localClickCount:7,userInfo:{}};
assert.equal(methods.totalClickCount.call(store),887);assert.equal(methods.cumulativeClickCount.call(store),1007);
methods.incrementLocalClickCount.call(store);assert.equal(store.localClickCount,8);
atlas.enabled.value=true;
assert.equal(methods.totalClickCount.call(store),888);assert.equal(methods.cumulativeClickCount.call(store),1008);
methods.incrementLocalClickCount.call(store);assert.equal(localTaps,0);assert.equal(store.localClickCount,9);
atlas.enabled.value=false;assert.equal(methods.cumulativeClickCount.call(store),1009);
const invoke=find(shared,n=>n.type==='FunctionDeclaration'&&n.id.name==='invoke$1')[0];
vm.runInContext(shared.slice(invoke.start,invoke.end),context);
(async()=>{
 atlas.enabled.value=true;
 await vm.runInContext('invoke$1("save_key_press_count",{count:9})',context);
 await vm.runInContext('invoke$1("save_cumulative_click_count",{count:1009})',context);
 assert.equal(nativeWrites,2);assert.deepEqual(savedCounts,[9,1009]);
 atlas.enabled.value=false;
 assert.equal(await vm.runInContext('invoke$1("save_key_press_count",{count:8})',context),7);
 assert.equal(nativeWrites,3);
 const logout=find(shared,n=>n.type==='FunctionDeclaration'&&n.id.name==='userLogout')[0];
 let logoutCount=null;context.jsonpClient={post:async(route,body)=>{logoutCount=body.click_num;}};
 vm.runInContext(shared.slice(logout.start,logout.end),context);atlas.enabled.value=true;
 await vm.runInContext('userLogout(1009)',context);assert.equal(logoutCount,1009);
 let roomCalls=0,roomBlocked=0;context.__lg=atlas;context.yt=()=>roomBlocked++;
 context.A.isLoggedIn=true;context.Sm=()=>{};context.Am=()=>{};
 context.Jp=async()=>roomCalls++;context.Qp=async()=>roomCalls++;
 for(const name of ['fh','dh']){const fn=find(main,n=>n.type==='FunctionDeclaration'&&n.id.name===name)[0];vm.runInContext(main.slice(fn.start,fn.end),context);}
 atlas.enabled.value=true;await vm.runInContext('Promise.all([fh(),dh()])',context);
 assert.equal(roomCalls,0);assert.equal(roomBlocked,2);
 atlas.enabled.value=false;await vm.runInContext('Promise.all([fh(),dh()])',context);assert.equal(roomCalls,2);
 // Execute the actual generated chest function in both display modes.
 const chest=find(main,n=>n.type==='FunctionDeclaration'&&n.id.name==='uc')[0];
 const rewardEvents=[];let requests=0,popups=0,spends=0;
 atlas.assistant.beginChest=side=>({id:'e'+requests,side});
 atlas.assistant.chestSucceeded=(attempt,reward)=>rewardEvents.push({attempt,reward});
 Object.assign(context,{Ie:()=>false,Dn:{value:false},kt:{value:false},xi:{},Di:{},Oi:{},Fi:{},Wn:{value:true},Gn:{value:true},ru(){},q(){},Bp:async()=>{},Ns:1000,G:async()=>{},
 km:async body=>{requests++;return{asset_id:3,asset_name:'reward.png',asset_type:'emote',rarity_type:'Rare',click_consume:1000};},gt:x=>x,wp(){},Rn:async()=>{},iu:async()=>{},su:()=>'',L:{value:''},au:x=>x,Cm(){},Rp:async()=>{popups++;},pv(){},D:{},ii:()=>[],ot:()=>{},ft:async()=>{},go(){},gr:()=>'',on:e=>{throw e;},console});
 context.A.totalClickCount=3000;context.A.cumulativeClickCount=9000;context.A.applyChestClickConsume=n=>{spends+=n;context.A.totalClickCount-=n;};
 vm.runInContext(main.slice(chest.start,chest.end),context);
 atlas.enabled.value=true;await vm.runInContext('uc("left")',context);
 atlas.enabled.value=false;await vm.runInContext('uc("right")',context);
 assert.equal(requests,2);assert.equal(popups,2);assert.equal(spends,2000);assert.equal(rewardEvents.length,2);assert.equal(context.A.totalClickCount,1000);
 assert(!main.includes('assistant.localChest'));assert(!main.includes('releasePanel'));assert(!shared.includes('incrementLocal()'));
 console.log('actual 1.0.2 contracts passed: original counters/save/logout, paired animation signals, room guards, real server chest/spend/reward path in BOTH modes');
})().catch(error=>{console.error(error);process.exitCode=1;});
