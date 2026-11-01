const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const context=vm.createContext({console});vm.runInContext(fs.readFileSync(__dirname+'/../src/desktop_context_menu.js','utf8'),context);
(async()=>{
 const calls=[],actions=[],reports=[];class Channel{constructor(fn=()=>{}){this.onmessage=fn;}}
 const menu=context.createDesktopContextMenu({Channel,settings:()=>({windowPassthrough:true,gameMode:false,petScale:100,windowOpacity:75}),labels:async()=>({dockSettings:'设置'}),visible:()=>true,
  report:async value=>reports.push(value),invoke:async(command,args)=>{calls.push([command,args]);if(command==='plugin:menu|new')return[42,'menu'];if(command==='plugin:menu|items')return calls.filter(([name])=>name==='plugin:menu|new').at(-1)[1].options.items.map((entry,i)=>[i,entry.id||'separator','MenuItem']);}});
 const callbacks={openTab:tab=>actions.push(tab),openConsole:()=>actions.push('console')};
 await menu.popup(20,30,callbacks);
 const entries=calls.find(([name])=>name==='plugin:menu|new')[1].options.items;
 const index=entries.findIndex(x=>x.text==='设置');assert(index>0);assert.equal(entries[index-1].text,'控制台');
 assert.equal(entries.find(x=>x.id==='fullatlas-drag').checked,true);
 assert.equal(entries.filter(x=>x.items).length,2);
 entries[index-1].handler.onmessage('fullatlas-console');entries[index].handler.onmessage('fullatlas-setting');
 entries.find(x=>x.id==='fullatlas-game').handler.onmessage('fullatlas-game');await Promise.resolve();
 assert.deepEqual(actions,['console','setting']);assert(calls.some(([name,args])=>name==='plugin:event|emit'&&args.event==='tray-toggle-game-mode'));
 await menu.popup(10,15,callbacks);assert(calls.some(([name,args])=>name==='plugin:resources|close'&&args.rid===42));
 await menu.initialize(callbacks);assert.equal(reports.at(-1).ok,true);assert.equal(reports.at(-1).console_before_settings,true);
 console.log('native context menu passed: console directly above settings; original view/toggle actions retained; old resource released');
})().catch(error=>{console.error(error);process.exitCode=1;});
