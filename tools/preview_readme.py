"""Render the README locally and verify every documentation image exists."""
from pathlib import Path
import re,shutil,sys

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'build/doc-preview-libs'))
import markdown2

source=(root/'README.md').read_text(encoding='utf-8-sig')
images=re.findall(r'!\[[^\]]*\]\((docs/images/[^)]+)\)|<img\b[^>]*src="(docs/images/[^"]+)"',source)
paths=[first or second for first,second in images]
for name in paths:
    if not (root/name).is_file():raise ValueError('Missing documentation image: '+name)
folder=root/'build/readme-preview'
folder.mkdir(parents=True,exist_ok=True)
shutil.copytree(root/'docs',folder/'docs',dirs_exist_ok=True)
for name in ('LICENSE','THIRD_PARTY_NOTICES.md'):
    shutil.copy2(root/name,folder/name)
body=markdown2.markdown(source,extras=['tables','fenced-code-blocks','header-ids','strike'])
style='''body{margin:0;background:#0d1117;color:#e6edf3;font:16px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif}article{max-width:980px;margin:24px auto;padding:32px 42px;border:1px solid #30363d;border-radius:8px}h1,h2{border-bottom:1px solid #30363d;padding-bottom:.3em;line-height:1.4}h1{font-size:32px}h2{font-size:24px;margin-top:32px}h3{font-size:19px;margin-top:28px}a{color:#58a6ff;text-decoration:none}a:hover{text-decoration:underline}img{max-width:100%;height:auto}p[align=center] img[width="128"]{width:128px;height:128px}p[align=center]{text-align:center}h1[align=center]{text-align:center}p[align=center] img:not([width]){height:20px}table{border-collapse:collapse;display:block;overflow:auto}th,td{padding:8px 13px;border:1px solid #30363d}tr:nth-child(even){background:#161b22}blockquote{margin-left:0;padding-left:16px;color:#8b949e;border-left:4px solid #30363d}hr{border:0;height:2px;background:#30363d;margin:28px 0}code{background:#21262d;border-radius:4px;padding:.15em .3em}pre{overflow:auto}li{margin:6px 0}@media(max-width:700px){article{margin:0;padding:22px 18px;border:0}}'''
(folder/'index.html').write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>WuwaTappo全图鉴版 · README 预览</title><style>'+style+'</style><article>'+body+'</article></html>',encoding='utf-8')
print({'preview':str(folder/'index.html'),'local_images':len(paths),'all_images_present':True})
