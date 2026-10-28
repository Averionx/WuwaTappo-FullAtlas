"""Create a data-preserving update ZIP from the built public payload."""
from pathlib import Path
import hashlib
import json
import sys
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from desktop_updater import TOP_LEVEL, validate_manifest


def make(payload, destination):
    payload, destination = Path(payload), Path(destination)
    config=json.loads((payload/'package_config.json').read_text(encoding='utf-8-sig'))
    files=[]
    for path in sorted(payload.rglob('*')):
        if not path.is_file():continue
        name=path.relative_to(payload).as_posix()
        if name not in TOP_LEVEL and name.split('/')[0] not in ('_internal','licenses','docs'):continue
        files.append({'path':name,'size':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    manifest=validate_manifest({'schema':1,'version':config['mod_version'],'client_version':config['client_version'],'files':files})
    destination.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(destination,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        archive.writestr('update_manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2))
        for item in files:archive.write(payload/item['path'],item['path'])
    return manifest


if __name__=='__main__':
    project=Path(__file__).resolve().parents[1]
    version=json.loads((project/'build/payload/package_config.json').read_text(encoding='utf-8-sig'))['mod_version']
    make(project/'build/payload',project/('dist/WuwaTappo-FullAtlas-'+version+'-x64-update.zip'))
