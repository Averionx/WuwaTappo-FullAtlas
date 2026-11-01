// Execute generated 1.0.3 functions, including the unmodified room emote path.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),acorn=require('../tools/acorn.cjs');
const build=path.resolve(__dirname,'../build'),m=JSON.parse(fs.readFileSync(path.join(build,'build_manifest_v2.json'),'utf8'));
const main=fs.readFileSync(path.join(build,'frontend_v2/assets',m.main),'utf8');
const nodes=[];function walk(n){if(!n||typeof n!=='object')return;if(n.type==='FunctionDeclaration')nodes.push(n);for(const [k,v]of Object.entries(n)){if(k==='start'||k==='end')continue;if(Array.isArray(v))v.forEach(walk);else if(v?.type)walk(v);}}
walk(acorn.parse(main,{ecmaVersion:'latest',sourceType:'module'}));
const fn=name=>{const marker={At:'__lg.createLocalPreset',un:'__lg.deleteLocalPreset',Dt:'__lg.applyLocalPreset'}[name];const n=nodes.find(n=>n.id.name===name&&(!marker||main.slice(n.start,n.end).includes(marker)));assert(n,name);return main.slice(n.start,n.end);};
let count=0,claps=0,bubbles=0,room=0,requests=0,popups=0,spends=0;
const atlas={enabled:{value:false},assistant:{beginChest:side=>({side}),chestSucceeded:()=>{}}};
const R={isLoggedIn:true,userInfo:{},totalClickCount:3000,cumulativeClickCount:9000,incrementLocalClickCount(){count++;},applyChestClickConsume(n){spends+=n;this.totalClickCount-=n;}};
const events=[],local=[];
const ctx=vm.createContext({console,window:{},__lg:atlas,R,qr:new Set(),va:new Set(),Fo:false,Wa:false,Bs:()=>false,py:()=>false,hy(){},Ie:()=>false,se:{value:''},Yo:()=>claps++,Wl:()=>claps++,Xn:async()=>{},
 De:{value:true},We:(event,data)=>events.push({event,data}),ih:null,J:()=>({rarity:'Rare'}),Mm:()=>{},Hf:()=>({offsetX:2,offsetY:3}),_t:{value:local},Pd:0,mn:()=>{},
 Fn:{value:false},kt:{value:false},Ei:{},Oi:{},xi:{},Fi:{},Wn:{value:true},Gn:{value:true},Up:async()=>{},lu(){},q(){},Ns:1000,G:async()=>{},
 Pm:async()=>{requests++;return{asset_id:7,asset_name:'reward.png',asset_type:'emote',rarity_type:'Rare',click_consume:1000};},yt:x=>x,Cp(){},cu:async()=>{},fu:()=>'',L:{value:''},uu:x=>x,go(){},mt(){},gr:()=>'',Tm(){},Tp:async()=>popups++,Iv(){},F:{},ii:()=>[],ot:()=>{},pt:async()=>{},me(){},od:()=>null,an:e=>{throw e;}});
vm.runInContext(fn('Uc')+'\n'+fn('Vc')+'\n'+fn('Ap')+'\n'+fn('Ae')+'\nih=Ae;',ctx);
vm.runInContext('Uc("F24",true);Vc("F24")',ctx);assert.equal(count,1);assert.equal(claps,2);
vm.runInContext('Uc("a");Uc("a");Vc("a")',ctx);assert.equal(count,2);
const item={id:7,src:'selected.png'};ctx.item=item;
vm.runInContext('Ap(item)',ctx);assert.equal(local.length,1);assert.equal(local[0].src,item.src);assert.deepEqual(events.map(x=>x.event),['re']);assert.equal(events[0].data.e,7);
atlas.enabled.value=true;vm.runInContext('Ap(item)',ctx);assert.equal(local.length,2);assert.equal(events.length,1);
// Real chest function still calls original network open, spend and popup in both modes.
vm.runInContext(fn('pc'),ctx);
(async()=>{
 await vm.runInContext('pc("left")',ctx);atlas.enabled.value=false;await vm.runInContext('pc("right")',ctx);
 assert.equal(requests,2);assert.equal(spends,2000);assert.equal(popups,2);assert.equal(R.totalClickCount,1000);
 assert(main.includes('Uc(e.payload); __lg.assistant.physicalKey(e.payload)'));
 assert(main.includes('Vc(e.payload); __lg.assistant.physicalRelease(e.payload)'));
 assert(main.includes('sendEmote:item=>Ap(item)'));
 assert(main.includes('app-shortcuts-changed'));assert(main.includes('app-shortcut'));
 // Execute actual local preset entry points before original login/API guards.
 let saved=0,deleted=0,applied=0,refreshed=0;
 Object.assign(atlas,{createLocalPreset:()=>saved++,deleteLocalPreset:id=>{assert.equal(id,-123);deleted++;},applyLocalPreset:id=>{assert.equal(id,-123);applied++;}});
 Object.assign(ctx,{__localRefresh:()=>refreshed++,it:()=>{},Tu:5});atlas.enabled.value=true;
 vm.runInContext(fn('At')+'\n'+fn('un')+'\n'+fn('Dt'),ctx);
 R.isLoggedIn=false;
 await vm.runInContext('At()',ctx);await vm.runInContext('un(-123)',ctx);await vm.runInContext('Dt({preset_id:-123})',ctx);
 assert.equal(saved,1);assert.equal(deleted,1);assert.equal(applied,1);assert.equal(refreshed,3);
 assert(fn('hc').includes('__lg.presetList().map('));
 console.log('actual 1.0.3 handlers passed: original paired counters, held-key dedupe, original local bubble + room re event, local-only broadcast guard, real chest network/spend/popup, native shortcut listeners retained');
})().catch(e=>{console.error(e);process.exitCode=1;});
