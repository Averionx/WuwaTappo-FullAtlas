"""Download an initial public asset cache without account credentials."""
from pathlib import Path
import argparse,json,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from sync_cache import sync

ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('root',type=Path,help='Dedicated data root; creates root/cache')
args=ap.parse_args()
cache=args.root.resolve()/'cache'
if not cache.exists():
    (cache/'assets').mkdir(parents=True)
    for name,value in [('atlas.json',{'code':0,'data':[]}),
       ('activity-config.json',{'code':0,'data':{'assets_json_ts':0}}),
       ('asset_manifest.json',{'records':[],'errors':[]})]:
        (cache/name).write_text(json.dumps(value),encoding='utf-8')
print(json.dumps(sync(args.root,lambda done,total:print(f'{done}/{total}',flush=True)),ensure_ascii=False))
