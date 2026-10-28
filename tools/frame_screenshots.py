"""Wrap original screenshot pixels in a transparent rounded SVG frame."""
from pathlib import Path
import base64

root=Path(__file__).resolve().parents[1]
names=('full-atlas','console-overview','chest-records','daily-stats')
for name in names:
    source=root/'docs/images'/f'{name}.jpg'
    encoded=base64.b64encode(source.read_bytes()).decode('ascii')
    svg=f'''<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="1100" height="760" viewBox="0 0 1100 760" role="img">
<title>WuwaTappo screenshot</title>
<defs><clipPath id="rounded-window"><rect width="1100" height="760" rx="56" ry="56"/></clipPath></defs>
<image width="1100" height="760" clip-path="url(#rounded-window)" xlink:href="data:image/jpeg;base64,{encoded}"/>
</svg>'''
    (source.with_suffix('.svg')).write_text(svg,encoding='utf-8')
readme=root/'README.md'
text=readme.read_text(encoding='utf-8-sig')
for name in names:text=text.replace(f'docs/images/{name}.jpg',f'docs/images/{name}.svg')
readme.write_text(text,encoding='utf-8')
print({'transparent_frames':len(names),'original_screenshots_preserved':True})
