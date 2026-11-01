const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),acorn=require('../tools/acorn.cjs');
const build=path.resolve(__dirname,'../build'),manifest=JSON.parse(fs.readFileSync(path.join(build,'build_manifest_v2.json'),'utf8')),text=fs.readFileSync(path.join(build,'frontend_v2/assets',manifest.panel),'utf8').replace(/\r\n/g,'\n');
const nodes=[];function walk(n){if(!n||typeof n!=='object')return;if(n.type)nodes.push(n);for(const[k,v]of Object.entries(n)){if(k==='start'||k==='end')continue;if(Array.isArray(v))v.forEach(walk);else if(v?.type)walk(v);}}walk(acorn.parse(text,{ecmaVersion:'latest',sourceType:'module'}));
const vnode=(tag,props,children,patchFlag)=>({tag,props:props||{},children,patchFlag});
const context=vm.createContext({console,e:vnode,m:vnode,i:()=>{},te:()=>null,E:fn=>({get value(){return fn();}}),p:x=>x,
 __lg:{enabled:{value:false},assistant:{openPanel:async tab=>{context.openedTab=tab;}}},__atlasProgress:{value:{collected:50,total:300,percent:50/3}},__atlasProgressTitle:{value:'全图鉴收集进度'},M:{value:false},ae:{isLoggedIn:true},ko:[]});
const progress=nodes.find(n=>n.type==='ConditionalExpression'&&text.slice(n.test.start,n.test.end)==='!__lg.enabled.value'&&text.slice(n.consequent.start,n.consequent.end).includes('data-atlas-progress'));
assert(progress);const render=()=>vm.runInContext(text.slice(progress.start,progress.end),context);
function find(n,p){if(!n||typeof n!=='object')return null;if(p(n))return n;for(const c of Array.isArray(n.children)?n.children:[]){const v=find(c,p);if(v)return v;}return null;}
let row=render(),bar=find(row,n=>n.props?.role==='progressbar');assert.equal(row.patchFlag,-2);assert.equal(bar.children[0].props.style.width,(50/3)+'%');assert.equal(bar.props['aria-valuenow'],50);
context.__atlasProgress.value={collected:200,total:300,percent:200/3};row=render();bar=find(row,n=>n.props?.role==='progressbar');assert.equal(bar.children[0].props.style.width,(200/3)+'%');assert.equal(bar.props['aria-valuenow'],200);
context.__lg.enabled.value=true;assert.equal(render(),null);context.__lg.enabled.value=false;
// Consume the actual upstream navigation array, including its singular setting key.
const assetRoot=path.join(manifest.base,'readable_js/assets'),utilityName=fs.readdirSync(assetRoot).find(n=>n.startsWith('switchDisplayMonitor-'));
const upstream=fs.readFileSync(path.join(assetRoot,utilityName),'utf8');const upstreamNodes=[];
function collect(n){if(!n||typeof n!=='object')return;if(n.type)upstreamNodes.push(n);for(const[k,v]of Object.entries(n)){if(k==='start'||k==='end')continue;if(Array.isArray(v))v.forEach(collect);else if(v?.type)collect(v);}}collect(acorn.parse(upstream,{ecmaVersion:'latest',sourceType:'module'}));
const navArray=upstreamNodes.find(n=>n.type==='ArrayExpression'&&n.elements.some(e=>e?.type==='ObjectExpression'&&e.properties.some(p=>p.key?.name==='labelKey'&&p.value.value==='nav_setting')));
assert(navArray);context.ko=vm.runInContext(upstream.slice(navArray.start,navArray.end),context);
const patchedUtility=fs.readFileSync(path.join(build,'frontend_v2/assets',utilityName),'utf8');
assert(patchedUtility.includes('e === "setting" || e === "console"'));
const tabs=nodes.find(n=>n.type==='VariableDeclarator'&&n.id.name==='__consoleTabs');assert(tabs);const menu=vm.runInContext(text.slice(tabs.init.start,tabs.init.end),context).value;assert.equal(menu.map(x=>x.key).join(','),'bag,atlas,exchange,room,console,setting,toggle');
const icon=nodes.find(n=>n.type==='ConditionalExpression'&&/^l\.key\s*===\s*['"]console['"]$/.test(text.slice(n.test.start,n.test.end))&&text.slice(n.consequent.start,n.consequent.end).includes("'data-console-icon':'sliders'"));assert(icon);context.l={key:'console'};context.s={activeTab:'console'};const svg=vm.runInContext(text.slice(icon.start,icon.end),context);assert.equal(svg.tag,'svg');assert.equal(svg.patchFlag,4);assert.equal(svg.props.style.color,'#9c6541');context.s.activeTab='setting';assert.equal(vm.runInContext(text.slice(icon.start,icon.end),context).props.style.color,'#f4d5a5');assert.equal(svg.children.filter(n=>n.tag==='circle').length,3);assert(svg.children.some(n=>n.props.stroke==='currentColor'));
// Execute the original category filter and our generated reactive bindings together.
const normalize=upstreamNodes.find(n=>n.type==='FunctionDeclaration'&&n.id.name==='Zt');assert(normalize);vm.runInContext(upstream.slice(normalize.start,normalize.end)+';globalThis.Ke=Zt;',context);
const controller=fs.readFileSync(path.join(__dirname,'../src/local_atlas_controller.js'),'utf8');vm.runInContext(controller.slice(controller.indexOf('function collectionProgress('),controller.indexOf('function viewUser('))+';__lg.collectionProgress=collectionProgress;',context);
const category=nodes.find(n=>n.type==='VariableDeclarator'&&n.id.name==='F'&&n.init&&text.slice(n.init.start,n.init.end).includes('xs[v.value]'));assert(category);
const types=nodes.find(n=>n.type==='VariableDeclarator'&&n.id.name==='xs'&&n.init?.type==='ObjectExpression');assert(types);context.xs=vm.runInContext('('+text.slice(types.init.start,types.init.end)+')',context);context.v={value:0};
context.b={value:[...Array.from({length:4},(_,i)=>({asset_id:i+1,asset_type:'character_skin',owned:i<1})),...Array.from({length:2},(_,i)=>({asset_id:i+1,asset_type:'accessory',owned:i<1})),...Array.from({length:4},(_,i)=>({asset_id:i+1,asset_type:'emote',owned:i<3}))]};
context.F=vm.runInContext(text.slice(category.init.start,category.init.end),context);
for(const name of ['__atlasProgress','__atlasProgressTitle']){const binding=nodes.find(n=>n.type==='VariableDeclarator'&&n.id.name===name);context[name]=vm.runInContext(text.slice(binding.init.start,binding.init.end),context);}
for(const[index,title,collected,total]of [[0,'全图鉴收集进度',5,10],[1,'全角色收集进度',1,4],[2,'全配件收集进度',1,2],[3,'全表情收集进度',3,4]]){context.v.value=index;row=render();bar=find(row,n=>n.props?.role==='progressbar');assert.equal(row.children[0].children[0].children,title);assert.equal(bar.props['aria-valuenow'],collected);assert.equal(bar.props['aria-valuemax'],total);assert.equal(bar.children[0].props.style.width,collected/total*100+'%');assert.equal(bar.props['aria-label'],'真实账号'+title);}
context.v.value=1;context.b.value[1].owned=true;bar=find(render(),n=>n.props?.role==='progressbar');assert.equal(bar.props['aria-valuenow'],2);assert.equal(bar.children[0].props.style.width,'50%');
const check=nodes.find(n=>n.type==='FunctionDeclaration'&&text.slice(n.start,n.end).includes("await __lg.assistant.openPanel('updates');return;"));assert(check);vm.runInContext(text.slice(check.start,check.end),context);
(async()=>{await vm.runInContext(check.id.name+'()',context);assert.equal(context.openedTab,'updates');assert(text.includes('class: "setting-btn btn-check-update",\n        disabled: false'));
 assert(text.includes('module-content__bg'));assert(text.includes("__name:'WuwaNativeConsole'"));assert(text.includes('mountConsole(target.value)'));assert(text.includes("'data-room-history':'true'"));assert(text.includes('joinHistoryRoom(room.code)'));
 assert(!text.includes('data-local-gallery-setting'));assert(!text.includes('data-desktop-assistant'));
 console.log('actual native panel passed: dynamic all/character/accessory/emote counts and fill, original category filtering, local-mode hidden, console before settings with custom SVG icon, native updates/background/history retained');
})().catch(e=>{console.error(e);process.exitCode=1;});
