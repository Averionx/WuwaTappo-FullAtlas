"""Write the exact checksum attachment consumed by the release updater."""
from pathlib import Path
import hashlib,json

root=Path(__file__).resolve().parents[1]
version=json.loads((root/'build/payload/package_config.json').read_text(encoding='utf-8-sig'))['mod_version']
names=[f'WuwaTappo-FullAtlas-{version}-x64-update.zip',
       f'WuwaTappo全图鉴版-{version}-原地升级.exe',f'WuwaTappo全图鉴版-{version}-Setup.exe']
lines=[]
for name in names:
    with (root/'dist'/name).open('rb') as stream:
        checksum=hashlib.file_digest(stream,'sha256').hexdigest()
    lines.append(checksum+'  '+name+'\n')
for name in ('SHA256SUMS.txt',f'SHA256SUMS-{version}.txt'):
    (root/'dist'/name).write_text(''.join(lines),encoding='utf-8')
print(json.dumps({'version':version,'verified_release_files':len(lines),'checksum_asset':'SHA256SUMS.txt'}))
