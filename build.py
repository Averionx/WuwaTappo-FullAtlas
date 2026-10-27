"""Build the public package from a separately supplied official executable."""
from pathlib import Path
import argparse, hashlib, json, os, shutil, subprocess, sys

PROJECT=Path(__file__).resolve().parent
EXPECTED='dd340c92a7320d1ecf3697ba65b4ad23d8f196acb547d2baf3f75ba09d696d97'

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--official',type=Path,required=True)
    ap.add_argument('--cache',type=Path,required=True)
    ap.add_argument('--runtime',type=Path,required=True,help='Extracted official Microsoft Fixed Version x64 runtime')
    ap.add_argument('--node',default='node')
    ap.add_argument('--iscc',type=Path)
    args=ap.parse_args()
    assert hashlib.sha256(args.official.read_bytes()).hexdigest()==EXPECTED,'Only the verified official 1.0.1 binary is supported'
    build=PROJECT/'build';base=build/'base';payload=build/'payload'
    base.mkdir(parents=True,exist_ok=True);payload.mkdir(exist_ok=True)
    shutil.copy2(args.official,base/'WuwaTappo.official.exe')
    env=os.environ.copy();env['WUWA_EXTRACT_ROOT']=str(base);env['WUWA_BUILD_ROOT']=str(build)
    run=lambda cmd:subprocess.run([str(x) for x in cmd],env=env,check=True,cwd=PROJECT)
    if not (base/'js_structure.json').exists():
        run([sys.executable,PROJECT/'tools/extract_static.py',base/'WuwaTappo.official.exe'])
        shared=next(p.name for p in (base/'readable_js/assets').glob('*.js') if 'function applyCatalog(' in p.read_text(encoding='utf-8'))
        run([args.node,PROJECT/'tools/inspect_js.cjs',base,shared])
    (build/'current_base.txt').write_text(str(base),encoding='utf-8')
    manifest=json.loads((args.cache/'asset_manifest.json').read_text(encoding='utf-8'))
    atlas=json.loads((args.cache/'atlas.json').read_text(encoding='utf-8'))['data']
    assert not manifest['errors']
    for record in manifest['records']:
        assert hashlib.sha256((args.cache/'assets'/record['file']).read_bytes()).hexdigest()==record['sha256']
    config={'port':43229,'asset_count':len(manifest['records']),'atlas_count':len(atlas),'client_version':'1.0.1','mod_version':'1.0'}
    (build/'local_config.json').write_text(json.dumps(config),encoding='utf-8')
    run([sys.executable,PROJECT/'tools/build_integration.py'])
    shutil.copy2(build/'WuwaTappo.Local.v2.exe',payload/'WuwaTappo.Local.exe')
    shutil.copytree(args.cache,payload/'cache',dirs_exist_ok=True)
    assert (args.runtime/'msedgewebview2.exe').is_file()
    shutil.copytree(args.runtime,payload/'runtime',dirs_exist_ok=True)
    for name in ['README.md','LICENSE','THIRD_PARTY_NOTICES.md']:
        shutil.copy2(PROJECT/name,payload/name)
    licenses=payload/'licenses';licenses.mkdir(exist_ok=True)
    shutil.copy2(Path(sys.base_prefix)/'LICENSE.txt',licenses/'PYTHON_LICENSE.txt')
    import importlib.metadata
    pyinstaller_license=next(p for p in importlib.metadata.distribution('PyInstaller').files if p.name=='COPYING.txt')
    shutil.copy2(importlib.metadata.distribution('PyInstaller').locate_file(pyinstaller_license),licenses/'PYINSTALLER_COPYING.txt')
    for script in (PROJECT/'installer').glob('*.ps1'):
        # Windows PowerShell 5.1 requires a BOM for Chinese labels.
        (payload/script.name).write_text(script.read_text(encoding='utf-8-sig'),encoding='utf-8-sig')
    shutil.copy2(build/'local_config.json',payload/'package_config.json')
    run([sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onedir','--console',
         '--name','LocalGalleryHost','--distpath',build/'frozen','--workpath',build/'pyinstaller',
         '--specpath',build,'--paths',PROJECT/'src',PROJECT/'src/local_host.py'])
    shutil.copytree(build/'frozen/LocalGalleryHost',payload/'host',dirs_exist_ok=True)
    # Keep the frozen service adjacent to the app; its Python DLLs stay in _internal.
    shutil.copy2(payload/'host/LocalGalleryHost.exe',payload/'LocalGalleryHost.exe')
    shutil.copytree(payload/'host/_internal',payload/'_internal',dirs_exist_ok=True)
    if args.iscc:
        run([args.iscc,PROJECT/'installer/setup.iss'])

if __name__=='__main__':main()
