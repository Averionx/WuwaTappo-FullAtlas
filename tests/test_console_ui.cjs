// Exercise the dashboard DOM without opening or automating any desktop window.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
class Element{
 constructor(tag,doc){this.tagName=tag;this.doc=doc;this.children=[];this.style={};this.attrs={};this.ownText='';this.isConnected=true;}
 append(n){this.children.push(n);n.parent=this;}
 set textContent(v){this.ownText=String(v??'');this.children=[];}
 get textContent(){return this.ownText+this.children.map(x=>x.textContent).join('');}
 replaceChildren(){this.children=[];}
 setAttribute(k,v){this.attrs[k]=v;}
 focus(){this.doc.activeElement=this;}
 remove(){if(this.parent)this.parent.children=this.parent.children.filter(x=>x!==this);}
}
const doc={activeElement:null,createElement(t){return new Element(t,this);},getElementById(id){return walk(this.head).find(x=>x.id===id);}};
doc.head=new Element('head',doc);doc.body=new Element('body',doc);const mount=new Element('main',doc);doc.body.append(mount);
function walk(n){return[n,...n.children.flatMap(walk)];}
const timers=new Map();let id=0,projects=0,installs=0,checks=0,waiting=true,same=false;
const window={document:doc,setInterval:f=>{timers.set(++id,f);return id;},clearInterval:id=>timers.delete(id)};
const state={settings:{enabled:true,auto_chest:false,auto_emote:true,threshold:1000,remember_monitor:true,speed:5},runtime:{emote_status:{equipped:5,sent:10}},rooms:[]};
const atlas={enabled:{value:false},busy:{value:false},setEnabled:async v=>atlas.enabled.value=v,request:async route=>{
 if(route==='/update/install'){installs++;return{message:'preparing'};}
 if(route==='/update/check')checks++;
 return{available:!waiting&&!same,required:false,waiting_for_adapter:waiting,official_checked:true,official_version:same?'1.0.3':'1.0.4',official_state:same?'current':'newer',github_version:'1.4',github_checked:true,mod_state:waiting?'waiting':same?'current':'available',client_version:'1.0.3',official_message:same?'官方与当前基底版本一致':'官方已发布新版 1.0.4',mod_message:waiting?'请等待适配':same?'修改版与当前安装版本一致，无需更新':'发现修改版 1.4，可更新',message:waiting?'等待适配':'发现可选更新'};
}};
const context=vm.createContext({window,console});vm.runInContext(fs.readFileSync(path.join(__dirname,'../src/assistant_dashboard.js'),'utf8')+';globalThis.make=createAssistantDashboard;',context);
const dashboard=context.make({window,mount,atlas,version:'test',initialTab:'settings',getState:async()=>state,configure:async v=>{Object.assign(state.settings,v);return state;},openProject:async()=>projects++,deleteRoom:async code=>{state.rooms=state.rooms.filter(r=>r.code!==code);},onClose(){}});
const findButton=text=>walk(mount).find(x=>x.tagName==='button'&&x.textContent===text);
(async()=>{
 for(let i=0;i<8;i++)await Promise.resolve();
 assert.equal(mount.children.length,1);assert(mount.children[0].className.includes('wt-embedded'));assert.equal(doc.body.children.length,1);
 assert(walk(mount).some(x=>x.attrs['aria-label']==='本地全图鉴'));
 assert(mount.textContent.includes('本次触发 10 次'));
 const toggle=walk(mount).find(x=>x.attrs['aria-label']==='本地全图鉴');toggle.checked=true;await toggle.onchange();assert(atlas.enabled.value);
 await findButton('GitHub · 项目与反馈').onclick();assert.equal(projects,1);
 dashboard.showTab('overview');await findButton('关闭本地全图鉴').onclick();assert.equal(atlas.enabled.value,false);assert(state.settings.enabled);assert(walk(mount).some(x=>x.className?.includes('common-scrollbar2')));
 state.rooms=[{code:'abc',host:'owner',favorite:false}];dashboard.showTab('rooms');await findButton('删除记录').onclick();assert.equal(state.rooms.length,0);assert(mount.textContent.includes('还没有房间历史'));

 dashboard.showTab('updates');for(let i=0;i<8;i++)await Promise.resolve();
 assert(findButton('一键升级').disabled);assert(mount.textContent.includes('等待适配'));assert(mount.textContent.includes('官方最新版'));assert(mount.textContent.includes('修改版最新版'));assert(mount.textContent.includes('当前安装版本'));assert(mount.textContent.includes('v1.4（GitHub 已发布 · 等待适配）'));assert(mount.textContent.includes('v1.0.4（有新版）'));

 waiting=false;await findButton('检查官方与适配版').onclick();assert.equal(checks,2);assert(!findButton('一键升级').disabled);
 assert(mount.textContent.includes('GitHub 已发布 · 可更新'));
 same=true;await findButton('检查官方与适配版').onclick();assert(findButton('一键升级').disabled);assert(mount.textContent.includes('v1.0.3（版本一致）'));assert(mount.textContent.includes('GitHub 已发布 · 版本一致'));assert(mount.textContent.includes('无需更新'));
 same=false;await findButton('检查官方与适配版').onclick();assert(!findButton('一键升级').disabled);
 await findButton('一键升级').onclick();assert.equal(installs,1);assert(mount.textContent.includes('preparing'));
 dashboard.close();assert.equal(mount.children.length,0);assert.equal(timers.size,0);assert(state.settings.enabled);
 console.log('embedded console passed: native mount, no body overlay, local toggle, auto-emote status, project entry, optional update/wait/install controls, teardown leaves background setting intact');
})().catch(e=>{console.error(e);process.exitCode=1;});
