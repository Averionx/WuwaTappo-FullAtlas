const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict'),acorn=require('../tools/acorn.cjs');
const root=path.resolve(__dirname,'../build');
const manifest=JSON.parse(fs.readFileSync(path.join(root,'build_manifest_v2.json'),'utf8'));
const source=fs.readFileSync(path.join(root,'frontend_v2/assets',manifest.shared),'utf8');
const ast=acorn.parse(source,{ecmaVersion:'latest',sourceType:'module'});
const request=ast.body.find(n=>n.type==='ClassDeclaration'&&n.id.name==='Request');
const handler=ast.body.find(n=>n.type==='FunctionDeclaration'&&n.id.name==='handleApiCode');
assert(request&&handler);
let onFailure,cleared=0,loggedOut=0;
class BusinessError extends Error{constructor(code){super(String(code));this.code=code;}}
const context=vm.createContext({console,Promise,Map,Error,Number,
 axios:{create:()=>({interceptors:{request:{use(){}},response:{use(ok,fail){onFailure=fail;}}}})},
 isApiSuccess:code=>code===0,clearAuthTokens:()=>cleared++,
 __vitePreload:async()=>({logoutAccount:()=>loggedOut++}),
 parseApiEnvelope:data=>data&&Number.isFinite(data.code)?data:null,
 parseApiErrorCode:e=>e.code,MAINTENANCE_HTTP_STATUS:503,
 globalStore:{},useLoading:()=>({hideLoading(){}}),ApiBusinessError:BusinessError,
 reportApiBusinessFailure(){},logApiBusinessError(){},logApiNetworkError(){},showApiErrorToast(){},reportAlert(){},
 isNetworkApiError:()=>false,reportNetworkTransportFailure(){},
});
vm.runInContext((source.slice(handler.start,handler.end)+'\n'+source.slice(request.start,request.end)+'\nnew Request({});').replaceAll('import.meta.url','"https://test.invalid/"'),context);
(async()=>{
 for(const [status,data,expected] of [[403,null,0],[403,{code:20001,message:'update required'},0],[429,null,0],[401,null,1],[403,{code:10003},1],[200,{code:10002},1]]){
  const before=cleared;
  await assert.rejects(onFailure({config:{url:'/api/user/info',method:'GET'},response:{status,data,headers:{}}}));
  await Promise.resolve();
  assert.equal(cleared-before,expected,`HTTP ${status}, code ${data?.code}`);
 }
 assert.equal(loggedOut,3);
 for(const name of [manifest.main,manifest.panel])acorn.parse(fs.readFileSync(path.join(root,'frontend_v2/assets',name),'utf8'),{ecmaVersion:'latest',sourceType:'module'});
 const main=fs.readFileSync(path.join(root,'frontend_v2/assets',manifest.main),'utf8');
 assert(main.includes('__lg.contextMenu.popup('));assert(main.includes("openConsole:async()=>"));
 assert(main.includes('__lg.contextMenu?.isOpen()'));
 assert(main.includes('chestSucceeded(__assistantAttempt,M.data)'));
 assert(main.includes('__lg.assistant.physicalKey(e.payload)'));
 console.log('Generated frontend passed: 403/version denial retains auth; 401 and explicit invalid-token codes clear auth; main/panel syntax and integration contracts valid.');
})().catch(e=>{console.error(e);process.exitCode=1;});
