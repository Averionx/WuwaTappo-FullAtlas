"""Build the self-contained 1.0 -> 1.1 in-place upgrade tool."""
from pathlib import Path
import json, os, shutil, subprocess, sys
import ssl
from make_update import make

project=Path(__file__).resolve().parents[1]
build=Path(os.environ.get('WUWA_BUILD_ROOT',project/'build'))
payload=build/'payload'
dist=Path(os.environ.get('WUWA_DIST_ROOT',project/'dist'))
config=json.loads((payload/'package_config.json').read_text(encoding='utf-8-sig'))
version=config['mod_version']
archive=dist/('WuwaTappo-FullAtlas-'+version+'-x64-update.zip')
make(payload,archive)
embedded=build/'upgrade-input/upgrade-payload.zip'
embedded.parent.mkdir(exist_ok=True)
shutil.copy2(archive,embedded)
ssl_policy=Path(ssl.__file__).with_name('codex-rejected-cas.pem')
ssl_data=['--add-data',str(ssl_policy)+os.pathsep+'.'] if ssl_policy.is_file() else []
font_data=['--add-data',str(build/'ui_fonts')+os.pathsep+'ui_fonts'] if (build/'ui_fonts').is_dir() else []
subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onefile','--windowed','--uac-admin','--exclude-module','numpy',*ssl_data,*font_data,
               '--name','WuwaTappo全图鉴版-'+version+'-原地升级',
               '--distpath',str(dist),'--workpath',str(build/'bootstrap-pyinstaller'),
               '--specpath',str(build),'--paths',str(project/'src'),
               '--add-data',str(embedded)+os.pathsep+'.',
               '--icon',str(payload/'WuwaTappo.Local.exe'),str(project/'src/upgrade_bootstrap.py')],
               cwd=project,check=True)
