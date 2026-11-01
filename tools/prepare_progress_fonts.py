"""Build a private UI subset of the original OFL font; no system installation."""
from pathlib import Path
from fontTools import subset
from fontTools.ttLib import TTFont

def prepare(project):
    project=Path(project);output=project/'build/ui_fonts';output.mkdir(exist_ok=True)
    characters=set(chr(i) for i in range(32,127))
    for name in ('update_progress.py','desktop_updater.py'):
        characters.update((project/'src'/name).read_text(encoding='utf-8'))
    characters.update('✓·…→更新版本正在下载校验解压备份替换启动完成请稍候保留返回软件关闭窗口退出总进度预览')
    notices=[]
    for style in ('Medium','Bold'):
        source=next((project/'build/frontend_v2/assets').glob('975MaruSC-'+style+'-*.woff2'))
        font=TTFont(source)
        notice=(font['name'].getDebugName(0) or '')+'\n\n'+(font['name'].getDebugName(13) or '')
        assert 'SIL OPEN FONT LICENSE' in notice
        if notice not in notices:notices.append(notice)
        options=subset.Options();options.name_IDs=[0,1,2,3,4,5,6,13,14,16,17];options.name_legacy=True
        worker=subset.Subsetter(options=options);worker.populate(unicodes=[ord(c) for c in characters]);worker.subset(font)
        replacements={1:'WT Tappo UI',2:style,3:'WT-Tappo-Progress-'+style,4:'WT Tappo UI '+style,6:'WTTappoUI-'+style,16:'WT Tappo UI',17:style}
        for record in font['name'].names:
            if record.nameID in replacements:record.string=replacements[record.nameID].encode(record.getEncoding(),errors='replace')
        font.flavor=None;font.save(output/('WT-Tappo-UI-'+style+'.ttf'))
    license_file=project/'licenses/975MARU_SC_OFL.txt'
    license_file.write_text('\n\n'.join(notices),encoding='utf-8')
    print('Original progress UI font prepared under private family WT Tappo UI; OFL retained',flush=True)
    return output

if __name__=='__main__':prepare(Path(__file__).resolve().parents[1])
