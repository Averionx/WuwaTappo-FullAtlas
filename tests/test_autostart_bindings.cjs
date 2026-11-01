const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict'),acorn=require('../tools/acorn.cjs');
const root=path.join(__dirname,'../build/frontend_v2/assets'),file=fs.readdirSync(root).find(x=>x.startsWith('switchDisplayMonitor-'));
const source=fs.readFileSync(path.join(root,file),'utf8'),nodes=[];
function walk(n){if(!n||typeof n!=='object')return;if(n.type)nodes.push(n);for(const v of Object.values(n)){if(Array.isArray(v))v.forEach(walk);else if(v?.type)walk(v);}}
walk(acorn.parse(source,{ecmaVersion:'latest',sourceType:'module'}));
const calls=[],context=vm.createContext({window:{__WUWA_LOCAL_ATLAS__:{request:async(url,body)=>{calls.push({url,...body});return {enabled:true};}}}});
for(const name of ['fa','_n']){const n=nodes.find(n=>n.type==='FunctionDeclaration'&&n.id.name===name);assert(n);vm.runInContext(source.slice(n.start,n.end),context);}
(async()=>{
 assert.equal(await context.fa(),true);await context._n(true);await context._n(false);
 assert.deepEqual(calls.map(x=>x.action),['status','enable','disable']);assert(calls.every(x=>x.url==='/startup'));
 console.log('actual native startup bindings passed: query/enable/disable all use variant launcher service');
})().catch(e=>{console.error(e);process.exitCode=1;});
