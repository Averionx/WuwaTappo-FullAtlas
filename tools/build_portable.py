"""Create a single portable EXE from the public payload, with no user data."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from portable_bootstrap import ROOT_FILES,ROOT_DIRS,safe_path,read_manifest

project=Path(__file__).resolve().parents[1]
build=Path(os.environ.get('WUWA_BUILD_ROOT',project/'build'))
payload=build/'payload'
dist=Path(os.environ.get('WUWA_DIST_ROOT',project/'dist'))
config=json.loads((payload/'package_config.json').read_text(encoding='utf-8-sig'))
version=config['mod_version']
folder=build/'portable-input';folder.mkdir(parents=True,exist_ok=True)
archive=folder/'portable-payload.zip'
records=[]
for source in sorted(payload.rglob('*')):
    if not source.is_file():continue
    name=source.relative_to(payload).as_posix()
    if name not in ROOT_FILES and name.split('/')[0] not in ROOT_DIRS:continue
    safe_path(name)
    with source.open('rb') as stream:checksum=hashlib.file_digest(stream,'sha256').hexdigest()
    records.append({'path':name,'size':source.stat().st_size,'sha256':checksum})
manifest={'schema':1,'version':version,'files':records}
with zipfile.ZipFile(archive,'w',zipfile.ZIP_LZMA) as output:
    output.writestr('portable_manifest.json',json.dumps(manifest,ensure_ascii=False))
    for item in records:output.write(payload/item['path'],item['path'])
with zipfile.ZipFile(archive) as check:read_manifest(check)
subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onefile','--windowed','--uac-admin',
    '--name','WuwaTappo全图鉴版-'+version+'-绿色版','--distpath',str(dist),
    '--workpath',str(build/'portable-pyinstaller'),'--specpath',str(build),
    '--paths',str(project/'src'),'--add-data',str(archive)+os.pathsep+'.',
    '--icon',str(payload/'WuwaTappo.Local.exe'),str(project/'src/portable_bootstrap.py')],cwd=project,check=True)
print(json.dumps({'version':version,'files':len(records),'public_payload_only':True,'portable_archive_bytes':archive.stat().st_size}))
