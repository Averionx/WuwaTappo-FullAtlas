const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path'),acorn=require('../tools/acorn.cjs');
const context=vm.createContext({console});vm.runInContext(fs.readFileSync(__dirname+'/../src/desktop_context_menu.js','utf8'),context);
(async()=>{
 const events=[],reports=[];let closeMenu,requestCount=0,body;
 const menu=context.createDesktopContextMenu({settings:()=>({windowPassthrough:true,gameMode:false,petScale:100,windowOpacity:75}),labels:async()=>({dockSettings:'设置'}),visible:()=>true,
  invoke:async(name,args)=>events.push([name,args]),report:async value=>reports.push(value),
  request:async(path,value)=>{assert.equal(path,'/assistant/context-menu');requestCount++;body=value;return new Promise(resolve=>closeMenu=resolve);}});
 const actions={before:async()=>events.push('before'),after:async()=>events.push('after'),openTab:async key=>events.push('open-'+key),openConsole:async()=>events.push('open-console')};
 await menu.initialize(actions);assert.equal(reports.at(-1).backend,'host-win32');
 const pending=menu.popup(20,30,actions);for(let i=0;i<10;i++)await Promise.resolve();
 assert(menu.isOpen());assert.equal(requestCount,1);assert(!events.includes('open-console'));
 const index=body.items.findIndex(item=>item.key==='setting');assert.equal(body.items[index-1].key,'console');assert.equal(body.items.find(item=>item.key==='drag').checked,true);
 await menu.popup(50,60,actions);assert.equal(requestCount,1);
 closeMenu({action:'console'});await pending;assert(!menu.isOpen());assert(events.indexOf('after')<events.indexOf('open-console'));
 const again=menu.popup(20,30,actions);for(let i=0;i<10;i++)await Promise.resolve();closeMenu({action:'setting'});await again;assert(events.includes('open-setting'));
 const cancel=menu.popup(20,30,actions);for(let i=0;i<10;i++)await Promise.resolve();closeMenu({action:null});await cancel;assert(!menu.isOpen());
 const broken=context.createDesktopContextMenu({settings:()=>({}),labels:async()=>({}),visible:()=>true,request:async()=>{throw Error('offline')}});
 let cleaned=false;await assert.rejects(broken.popup(0,0,{after:async()=>cleaned=true}),/offline/);assert(cleaned);assert(!broken.isOpen());
 assert(!events.some(item=>Array.isArray(item)&&item[0].startsWith('plugin:menu|')));
 // Execute the actual generated call-site object. The helper's private cleanup
 // name differs from the binding in the main component's lexical scope.
 const manifest=JSON.parse(fs.readFileSync(path.join(__dirname,'../build/build_manifest_v2.json'),'utf8'));
 const generated=fs.readFileSync(path.join(__dirname,'../build/frontend_v2/assets',manifest.main),'utf8'),nodes=[];
 function walk(n){if(!n||typeof n!=='object')return;if(n.type)nodes.push(n);for(const[k,v]of Object.entries(n)){if(k==='start'||k==='end')continue;if(Array.isArray(v))v.forEach(walk);else if(v?.type)walk(v);}}
 walk(acorn.parse(generated,{ecmaVersion:'latest',sourceType:'module'}));
 const call=nodes.find(n=>n.type==='CallExpression'&&generated.slice(n.callee.start,n.callee.end)==='__lg.contextMenu.popup');assert(call);
 const effects=[],actual=vm.createContext({Xl:()=>effects.push('release-gesture'),Xp:async tab=>effects.push('open-'+tab),Ct:async(name,args)=>{effects.push(name);return true;},__lg:{request:async(path,body)=>effects.push(body)}});
 const bindings=vm.runInContext('('+generated.slice(call.arguments[2].start,call.arguments[2].end)+')',actual);
 await bindings.before();await bindings.after();await bindings.openConsole();
 assert.equal(effects.filter(x=>x==='release-gesture').length,2);assert(effects.includes('open-console'));assert(effects.some(x=>x?.kind==='context_console_open'&&x.visible===true));
 console.log('native menu regression passed: no shared Tauri channel, waits for dismissal, cleanup precedes direct console dispatch, repeated selection/cancel/error recover');
})().catch(error=>{console.error(error);process.exitCode=1;});
