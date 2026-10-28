const fs=require('fs'),path=require('path'),acorn=require('./acorn.cjs');
const build=path.resolve(process.argv[2]||path.join(__dirname,'../build'));
const report=JSON.parse(fs.readFileSync(path.join(build,'build_report_v2.json'),'utf8'));
const inventory=report.assets||report.asset_changes;
const cache=new Map();
function moduleInfo(file){
 if(cache.has(file))return cache.get(file);
 const text=fs.readFileSync(file,'utf8'),ast=acorn.parse(text,{ecmaVersion:'latest',sourceType:'module'});
 const exports=new Set();
 for(const node of ast.body){if(node.type==='ExportDefaultDeclaration')exports.add('default');if(node.type==='ExportNamedDeclaration'){for(const item of node.specifiers)exports.add(item.exported.name);if(node.declaration?.id)exports.add(node.declaration.id.name);}}
 const value={ast,exports};cache.set(file,value);return value;
}
if(!inventory)throw Error('Build report has no asset inventory');
for(const item of inventory){
 const file=path.join(build,'frontend_v2',item.path.replace(/^\//,''));
 const {ast}=moduleInfo(file);
 for(const node of ast.body){
  if(node.type!=='ImportDeclaration'||!node.source.value.startsWith('.'))continue;
  const target=path.resolve(path.dirname(file),node.source.value);
  if(!fs.existsSync(target))throw Error('Missing dependency '+node.source.value);
  if(!target.endsWith('.js'))continue;
  const dependency=moduleInfo(target);
  for(const spec of node.specifiers){const key=spec.type==='ImportDefaultSpecifier'?'default':spec.type==='ImportSpecifier'?spec.imported.name:null;if(key&&!dependency.exports.has(key))throw Error('Missing export '+key+' in '+target);}
 }
}
console.log('Parsed '+inventory.length+' patched modules; all direct JavaScript imports resolve.');
