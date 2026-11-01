const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),source=fs.readFileSync(path.join(root,'src/local_atlas_controller.js'),'utf8');
const catalog=JSON.parse(fs.readFileSync(path.join(root,'build/payload/cache/offline_catalog.json'))),atlas=JSON.parse(fs.readFileSync(path.join(root,'build/payload/cache/atlas.json'))).data;
const context=vm.createContext({URL,AbortController,console});vm.runInContext(source+';globalThis.make=createLocalAtlasController;',context);
const stored=new Map();let enabled=true,remoteWrites=0;
function make(){const listeners={};
 const controller=context.make({ref:value=>({value}),token:'test',origin:'http://127.0.0.1:43219',storage:{getItem:k=>stored.get(k),setItem:(k,v)=>stored.set(k,v)},
 window:{location:{href:'http://tauri.localhost/',origin:'http://tauri.localhost'},addEventListener:(k,v)=>listeners[k]=v,dispatchEvent(){},CustomEvent:class{},
 fetch:async(url,options)=>{let value={};if(String(url).endsWith('/status'))value={ready:true,enabled,mode_verified:true,network_policy:'rooms-only'};
 else if(String(url).endsWith('/offline-data'))value={catalog,atlas};else if(String(url).endsWith('/mode')){enabled=JSON.parse(options.body).enabled;value={enabled,mode_verified:true,network_policy:'rooms-only'};}else remoteWrites++;
 return{ok:true,json:async()=>value};}},snapshotCatalog:()=>({}),restoreCatalog(){},applyOfflineCatalog(){},normalizeAtlasList:x=>x,
 resolvePetAssetIdFromAppearanceId(id){for(const t of ['character_skin_atlas','accessory_atlas','emote_atlas'])if(catalog[t][id])return catalog[t][id].height_light_id;return id;},
 getAppearanceAssetById(id){for(const t of ['character_skin','accessory','emote'])if(catalog[t][id])return{...catalog[t][id],asset_type:t};return null;}});
 return{controller,listeners};
}
(async()=>{
 const{controller:c}=make();await c.ready;
 const official={character:null,accessory:null,emote:[]},original=JSON.stringify(official);
 const inv=c.inventory(atlas,[]),roles=inv.filter(x=>x.asset_type==='character_skin');
 c.select(roles[0],official,5);const wanted=c.viewUser(official).character.id;
 const preset=c.createLocalPreset(official);assert(preset.preset_id<0);assert.equal(c.presetList().length,1);
 c.select(roles[1],official,5);assert.notEqual(c.viewUser(official).character.id,wanted);c.applyLocalPreset(preset.preset_id);assert.equal(c.viewUser(official).character.id,wanted);
 const restarted=make();await restarted.controller.ready;assert.equal(restarted.controller.presetList().length,1);restarted.controller.applyLocalPreset(preset.preset_id);
 assert.equal(restarted.controller.viewUser(official).character.id,wanted);assert.equal(JSON.stringify(official),original);
 for(let i=0;i<4;i++)c.createLocalPreset(official);assert.equal(c.presetList().length,5);assert.throws(()=>c.createLocalPreset(official),/已满/);
 c.deleteLocalPreset(preset.preset_id);assert.equal(c.presetList().length,4);assert.throws(()=>c.applyLocalPreset(preset.preset_id),/不存在/);
 const p=c.createLocalPreset(official);assert.equal(c.presetList().length,5);assert.equal(new Set(c.presetList().map(x=>x.preset_id)).size,5);
 restarted.listeners.storage({key:'wuwatappo-local-presets-v1'});assert.equal(restarted.controller.presetList().length,5);
 await c.setEnabled(false);assert.throws(()=>c.createLocalPreset(official),/尚未开启/);assert.throws(()=>c.deleteLocalPreset(p.preset_id),/尚未开启/);assert.equal(c.viewUser(official),official);assert.equal(remoteWrites,0);
 const rows=n=>Array.from({length:300},(_,i)=>({asset_id:i+1,asset_type:'emote',owned:i<n,quantity:999}));
 const low=c.collectionProgress(rows(50)),high=c.collectionProgress(rows(200));assert.equal(low.collected,50);assert.equal(high.collected,200);assert.equal(low.total,300);assert(Math.abs(low.percent-100/6)<1e-9);assert(Math.abs(high.percent-200/3)<1e-9);assert(high.percent>low.percent*3.9);
 assert.equal(c.collectionProgress([...rows(50),...rows(50)]).total,300);assert.equal(c.collectionProgress([]).percent,0);assert.equal(c.collectionProgress(rows(300)).percent,100);assert.equal(c.collectionProgress(rows(300),true).total,0);
 const changing=rows(50);changing[80].owned=true;assert.equal(c.collectionProgress(changing).collected,51);assert(c.collectionProgress(changing).percent>low.percent);
 console.log('local features passed: preset create/apply/delete/restart/cross-view/capacity/account isolation/no network, and live 50/300 vs 200/300 ratios, dedupe, loading, 0%,100%');
})().catch(e=>{console.error(e);process.exitCode=1;});
