const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const rooms=[{code:'room-123',host:'owner',favorite:false,visited:1}],requests=[],emits=[];
const window={addEventListener(){},setTimeout(){},clearTimeout(){},document:{},__TAURI_INTERNALS__:{invoke:async(command,body)=>emits.push({command,body})}};
const atlas={ready:Promise.resolve(),enabled:{value:false},request:async(route,body)=>{requests.push({route,body});if(route.endsWith('/favorite'))rooms[0].favorite=body.favorite;if(route.endsWith('/delete-room'))rooms.splice(0);return{rooms,settings:{},required:false};}};
const context=vm.createContext({window,console});vm.runInContext(fs.readFileSync(path.join(__dirname,'../src/desktop_assistant.js'),'utf8')+';globalThis.make=createDesktopAssistant;',context);
const a=context.make({window,atlas,ref:value=>({value})});
(async()=>{
 assert.equal((await a.roomHistory())[0].code,'room-123');assert((await a.favoriteRoom('room-123',true))[0].favorite);
 await a.joinHistoryRoom('room-123');assert.equal(emits.length,1);assert.equal(emits[0].body.event,'local-assistant-join');assert.equal(emits[0].body.payload,'room-123');
 atlas.enabled.value=true;await assert.rejects(a.joinHistoryRoom('room-123'),/关闭本地全图鉴/);assert.equal(emits.length,1);
 atlas.enabled.value=false;await assert.rejects(a.joinHistoryRoom('https://example.invalid'),/无效/);assert.equal(emits.length,1);
 await a.deleteRoom('room-123');assert.equal(rooms.length,0);assert.equal(emits.length,1);assert(requests.some(r=>r.route==='/assistant/delete-room'&&r.body.code==='room-123'));

 console.log('history API passed: shared persisted list/favorite route, native join signal, local-mode guard, invalid-room guard; no actual room joined');
})().catch(e=>{console.error(e);process.exitCode=1;});
