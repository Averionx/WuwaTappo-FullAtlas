"""Prepare a browser preview from the production dashboard (demo data only)."""
from pathlib import Path
import shutil

project=Path(__file__).resolve().parents[1]
folder=project/'build/dashboard-preview'
folder.mkdir(parents=True,exist_ok=True)
shutil.copy2(project/'src/assistant_dashboard.js',folder/'assistant_dashboard.js')
(folder/'index.html').write_text('''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>控制台 UI 预览 · 演示数据</title>
<body style="margin:0;background:#e6ded0"><script src="assistant_dashboard.js"></script><script>
const demo={settings:{enabled:true,speed:5,auto_chest:true,threshold:1000,remember_monitor:true},session:1510,confirmed:1510,session_chests:2,
runtime:{total:12910,balance:910,logged_in:true,local_atlas:true,quiet:true,chests:{left:{remaining:720000},right:{remaining:125000},cooldown:1800000}},
rewards:[{id:'preview',time:Date.now()/1000,name:'角色 · 示例奖励',asset_name:'demo',side:'left',source:'automatic',cost:1000,rarity:'Rare'}],rooms:[],weekly:{normal:[90,120,80,310,210,504,1510].map((count,i)=>({date:'2026-10-'+(23+i),count}))}};
const atlas={enabled:{value:true},request:async()=>({available:false,message:'UI 演示：未执行真实更新或开箱'})};
window.preview=createAssistantDashboard({window,version:'1.2 · UI 演示',atlas,getState:async()=>structuredClone(demo),configure:async changes=>{Object.assign(demo.settings,changes);return structuredClone(demo)},reset:async()=>{demo.session=0;demo.session_chests=0},favorite:async()=>{},join:async()=>{},onClose(){document.body.textContent='预览面板已关闭；没有运行真实挂机。'}});
if(new URLSearchParams(location.search).has('forced')){
  preview.close();document.body.textContent='';
  createAssistantUpdateGate({window,result:{required:true,version:'9.9（UI 演示）',message:'演示数据：必须更新才能继续。'},
    install:async()=>{throw Error('演示：模拟下载失败，原程序未改动，可重试。')},
    retry:async()=>({required:true,version:'9.9',message:'演示：更新要求仍然生效，可再次下载。'}),
    quit:async()=>{document.body.textContent='演示已退出；未操作真实桌宠。'}});
}
</script></body></html>''',encoding='utf-8')
print(folder)
