const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
class Element{
 constructor(tag,doc){this.tagName=tag;this.doc=doc;this.children=[];this.style={};this.attrs={};this.ownText='';this.isConnected=true;}
 append(n){this.children.push(n);n.parent=this;}
 set textContent(v){this.ownText=String(v??'');this.children=[];}
 get textContent(){return this.ownText+this.children.map(x=>x.textContent).join('');}
 setAttribute(k,v){this.attrs[k]=v;}
 focus(){this.doc.activeElement=this;}
 remove(){if(this.parent)this.parent.children=this.parent.children.filter(x=>x!==this);this.isConnected=false;}
}
function dom(){const doc={createElement:t=>new Element(t,doc),getElementById:id=>doc.head.children.find(x=>x.id===id),querySelector:()=>null};doc.head=new Element('head',doc);doc.body=new Element('body',doc);return doc;}
function walk(n){return[n,...n.children.flatMap(walk)];}
const source=fs.readFileSync(path.join(__dirname,'../src/assistant_dashboard.js'),'utf8');
const driver=fs.readFileSync(path.join(__dirname,'../src/desktop_assistant.js'),'utf8');
const turns=async()=>{for(let i=0;i<25;i++)await Promise.resolve();};
(async()=>{
 const document=dom(),window={document},context=vm.createContext({window,console});vm.runInContext(source,context);
 let installs=0,exits=0;
 const required={required:true,available:true,current_version:'1.3.5',version:'1.3.6'};
 const gate=context.createAssistantUpdateGate({window,result:required,install:async()=>{installs++;throw Error('network offline');},retry:async()=>required,quit:()=>exits++});
 const button=text=>walk(document.body).find(n=>n.tagName==='button'&&n.textContent===text);
 assert.equal(document.body.children[0].attrs.role,'dialog');
 assert.equal(button('关闭预览'),undefined);assert.equal(button('重新检查'),undefined);assert.equal(walk(document.body).filter(n=>n.tagName==='button').length,2);assert(!button('立即更新').disabled);
 await button('立即更新').onclick();assert.equal(installs,1);assert(document.body.textContent.includes('原程序与数据保留'));assert(!button('重试更新').disabled);
 await button('退出软件').onclick();assert.equal(exits,1);
 gate.update({...required,required:false,preview:true});assert(button('重试更新').disabled);assert.equal(button('关闭预览'),undefined);
 await button('重试更新').onclick();assert.equal(installs,1);
 gate.close();assert.equal(document.body.children.length,0);

 const nativeCalls=[],events={},nativeDoc=dom(),nativeWindow={document:nativeDoc,addEventListener:(type,fn)=>events[type]=fn,removeEventListener:type=>delete events[type]};
 let closeHandler,moveHandler;
 const native={outerPosition:async()=>({type:'Physical',x:100,y:200}),
  onCloseRequested:async fn=>{closeHandler=fn;return()=>{};},onMoved:async fn=>{moveHandler=fn;return()=>{};}};
 for(const name of ['setClosable','setMinimizable','setMaximizable','setAlwaysOnTop','setDecorations','setMaxSize','setMinSize','setSize','setResizable','center','setPosition'])native[name]=async value=>nativeCalls.push([name,value]);
 const fixedGate=context.createAssistantUpdateGate({window:nativeWindow,result:required,nativeWindow:()=>native,install:async()=>{},quit:()=>{}});
 await fixedGate.nativeReady;
 assert(nativeCalls.some(([name,value])=>name==='setAlwaysOnTop'&&value===true));
 for(const method of ['setClosable','setResizable','setMinimizable','setMaximizable'])assert(!nativeCalls.some(([name])=>name===method));
 assert(nativeCalls.some(([name,value])=>name==='setSize'&&value.width===500&&value.height===450));
 let prevented=0;closeHandler({preventDefault:()=>prevented++});events.keydown({key:'Escape',preventDefault:()=>prevented++,stopImmediatePropagation(){}});assert.equal(prevented,2);
 await moveHandler({payload:{x:300,y:400}});assert(nativeCalls.some(([name,value])=>name==='setPosition'&&value.x===100&&value.y===200));
 fixedGate.close();assert.equal(events.keydown,undefined);

 for(const route of ['#/','#/update']){
  const document=dom(),timers=[],window={document,location:{hash:route},addEventListener(){},setTimeout:f=>{timers.push(f);return timers.length;},clearTimeout(){},setInterval(){}};
  const state={settings:{enabled:true,auto_chest:true,auto_emote:true,remember_monitor:false},update_required:true};
  const atlas={enabled:{value:false},ready:Promise.resolve(),request:async url=>url.startsWith('/update/')?required:state};
  const context=vm.createContext({window,console});vm.runInContext(source+'\n'+driver,context);
  const assistant=context.createDesktopAssistant({window,atlas,ref:value=>({value})});await assistant.ready;await turns();
  assert(assistant.updateRequired.value);
  if(route==='#/update')assert.equal(document.body.children[0].className,'wt-gate');
  else{
   assert.equal(document.body.children.length,0);let opened=0;
   await assistant.startMain({showUpdate:async()=>opened++,currentMonitor:async()=>null,listenRoom(){},listenJoin:async()=>{}});
   assert(opened>0);assert.equal(document.body.children.length,0);
  }
 }
 // Execute the original, patched native opener while the force-update guard
 // is active: settings stay blocked, but the update console remains reachable.
 const acorn=require('../tools/acorn.cjs'),build=path.join(__dirname,'../build');
 const manifest=JSON.parse(fs.readFileSync(path.join(build,'build_manifest_v2.json'),'utf8'));
 const main=fs.readFileSync(path.join(build,'frontend_v2/assets',manifest.main),'utf8'),nodes=[];
 function walkAst(n){if(!n||typeof n!=='object')return;if(n.type==='FunctionDeclaration')nodes.push(n);for(const v of Object.values(n)){if(Array.isArray(v))v.forEach(walkAst);else if(v?.type)walkAst(v);}}
 walkAst(acorn.parse(main,{ecmaVersion:'latest',sourceType:'module'}));
 const opener=nodes.find(n=>main.slice(n.start,n.end).includes('[panel] open tab failed'));
 assert(opener);let opens=0,blockedToasts=0;
 const nativeContext=vm.createContext({console,Ie:()=>true,mt:()=>blockedToasts++,$:x=>x,rt:{value:''},$e:{value:false},ge:{value:false},Ru:async()=>opens++,Yn(){},it(){},Me(){}});
 vm.runInContext(main.slice(opener.start,opener.end),nativeContext);
 await nativeContext[opener.id.name]('setting');assert.equal(opens,0);assert.equal(blockedToasts,1);
 await nativeContext[opener.id.name]('console');assert.equal(opens,1);assert.equal(nativeContext.rt.value,'console');
 console.log('mandatory update gate passed: real requirement locks, dedicated update window only, exactly two actions, update retry, exit, explicitly labelled preview');
})().catch(e=>{console.error(e);process.exitCode=1;});
