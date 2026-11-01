"""Wrap original screenshot pixels in a transparent rounded SVG frame."""
from pathlib import Path
import base64,struct

root=Path(__file__).resolve().parents[1]
names=('full-atlas','console-overview','chest-records','daily-stats','collection-progress','console-settings','update-status')
framed=0
for name in names:
    source=root/'docs/images'/f'{name}.png'
    if not source.exists():source=source.with_suffix('.jpg')
    if not source.exists():continue
    data=source.read_bytes()
    width,height=struct.unpack('>II',data[16:24]) if source.suffix=='.png' else (1100,760)
    mime='png' if source.suffix=='.png' else 'jpeg'
    encoded=base64.b64encode(data).decode('ascii')
    svg=f'''<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img">
<title>WuwaTappo screenshot</title>
<defs><clipPath id="rounded-window"><rect width="{width}" height="{height}" rx="56" ry="56"/></clipPath></defs>
<image width="{width}" height="{height}" clip-path="url(#rounded-window)" xlink:href="data:image/{mime};base64,{encoded}"/>
</svg>'''
    (source.with_suffix('.svg')).write_text(svg,encoding='utf-8')
    framed+=1
readme=root/'README.md'
text=readme.read_text(encoding='utf-8-sig')
for name in names:text=text.replace(f'docs/images/{name}.jpg',f'docs/images/{name}.svg')
readme.write_text(text,encoding='utf-8')
print({'transparent_frames':framed,'original_screenshots_preserved':True})
