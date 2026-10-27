"""Extract Tauri embedded assets and PE resources without executing the input."""
from pathlib import Path, PurePosixPath
import argparse
import collections
import hashlib
import json
import re
import struct
import sys

import os
ROOT = Path(os.environ['WUWA_EXTRACT_ROOT'])
sys.path.insert(0, str(Path(__file__).parent / 'python_libs'))
import brotli
import pefile
import jsbeautifier


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('exe', type=Path)
    args = ap.parse_args()
    data = args.exe.read_bytes()
    pe = pefile.PE(data=data)
    base = pe.OPTIONAL_HEADER.ImageBase
    analysis = ROOT / 'analysis'
    analysis.mkdir(exist_ok=True)

    def offset(va, size=1):
        rva = va - base
        for sec in pe.sections:
            if sec.VirtualAddress <= rva and rva + size <= sec.VirtualAddress + sec.SizeOfRawData:
                return sec.PointerToRawData + rva - sec.VirtualAddress
        raise ValueError('Pointer outside file-backed sections')

    def row(pos):
        kp, kl, dp, dl = struct.unpack_from('<QQQQ', data, pos)
        if not (1 <= kl <= 512 and 1 <= dl <= len(data)):
            raise ValueError('Invalid lengths')
        ko, do = offset(kp, kl), offset(dp, dl)
        name = data[ko:ko + kl].decode('utf-8')
        pp = PurePosixPath(name)
        if not name.startswith('/') or '..' in pp.parts or '\\' in name or ':' in name or '\0' in name:
            raise ValueError('Unsafe or invalid asset path')
        return name, do, dl

    # Locate the (&str, &[u8]) table through references to the entry HTML path.
    candidates = []
    for match in re.finditer(re.escape(b'/index.html'), data):
        va = base + pe.get_rva_from_offset(match.start())
        for ref in re.finditer(re.escape(struct.pack('<Q', va)), data):
            try:
                first = ref.start()
                row(first)
                while first >= 32:
                    try:
                        row(first - 32)
                        first -= 32
                    except (ValueError, UnicodeError, struct.error):
                        break
                rows = []
                pos = first
                while pos + 32 <= len(data):
                    try:
                        rows.append(row(pos))
                        pos += 32
                    except (ValueError, UnicodeError, struct.error):
                        break
                if len(rows) > 5:
                    candidates.append((first, rows))
            except (ValueError, UnicodeError, struct.error):
                pass
    if not candidates:
        raise RuntimeError('No Tauri asset table found')
    table_start, rows = max(candidates, key=lambda x: len(x[1]))
    inventory, errors = [], []
    opts = jsbeautifier.default_options()
    opts.indent_size = 2
    for name, pos, length in rows:
        relative = PurePosixPath(name.lstrip('/'))
        target = ROOT / 'frontend' / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        packed = data[pos:pos + length]
        try:
            plain = brotli.decompress(packed)
        except brotli.error as exc:
            errors.append({'path': name, 'error': str(exc)})
            (analysis / ('failed_' + str(pos) + '.bin')).write_bytes(packed)
            continue
        target.write_bytes(plain)
        inventory.append({'path': name, 'table_offset': table_start + rows.index((name, pos, length)) * 32,
                          'file_offset': pos, 'compressed_size': length, 'size': len(plain),
                          'sha256': hashlib.sha256(plain).hexdigest()})
        if name.endswith('.js'):
            readable = ROOT / 'readable_js' / relative
            readable.parent.mkdir(parents=True, exist_ok=True)
            readable.write_text(jsbeautifier.beautify(plain.decode('utf-8'), opts), encoding='utf-8')
        print(f'{name}: {length:,} -> {len(plain):,}')

    resource_inventory = []
    if hasattr(pe, 'DIRECTORY_ENTRY_RESOURCE'):
        for typ in pe.DIRECTORY_ENTRY_RESOURCE.entries:
            for ident in typ.directory.entries:
                for lang in ident.directory.entries:
                    info = lang.data.struct
                    raw = pe.get_data(info.OffsetToData, info.Size)
                    type_name = str(typ.name) if typ.name else pefile.RESOURCE_TYPE.get(typ.id, str(typ.id))
                    resource_id = str(ident.name) if ident.name else str(ident.id)
                    safe_name = re.sub(r'[^A-Za-z0-9_.-]', '_', resource_id)
                    ext = '.manifest' if typ.id == 24 else '.bin'
                    dest = ROOT / 'pe_resources' / type_name / f'{safe_name}_{lang.id}{ext}'
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(raw)
                    resource_inventory.append({'type': type_name, 'id': resource_id,
                                               'language': lang.id, 'size': len(raw),
                                               'rva': info.OffsetToData})
        # Turn each RT_GROUP_ICON and its RT_ICON images into a usable ICO file.
        groups = next((x for x in pe.DIRECTORY_ENTRY_RESOURCE.entries if x.id == 14), None)
        icons = next((x for x in pe.DIRECTORY_ENTRY_RESOURCE.entries if x.id == 3), None)
        if groups and icons:
            for group in groups.directory.entries:
                info = group.directory.entries[0].data.struct
                raw = pe.get_data(info.OffsetToData, info.Size)
                count = struct.unpack_from('<H', raw, 4)[0]
                header, images, cursor = bytearray(raw[:6]), bytearray(), 6 + count * 16
                for i in range(count):
                    entry = raw[6 + i * 14:20 + i * 14]
                    icon_id = struct.unpack_from('<H', entry, 12)[0]
                    icon = next(x for x in icons.directory.entries if x.id == icon_id)
                    ii = icon.directory.entries[0].data.struct
                    blob = pe.get_data(ii.OffsetToData, ii.Size)
                    header += entry[:8] + struct.pack('<II', len(blob), cursor)
                    images += blob
                    cursor += len(blob)
                (ROOT / 'pe_resources' / f'icon_{group.id}.ico').write_bytes(header + images)

    imports = {}
    for dll in getattr(pe, 'DIRECTORY_ENTRY_IMPORT', []):
        imports[dll.dll.decode(errors='replace')] = [
            imp.name.decode(errors='replace') if imp.name else f'ordinal:{imp.ordinal}' for imp in dll.imports]
    sections = [{'name': s.Name.rstrip(b'\0').decode(), 'rva': s.VirtualAddress,
                 'raw_offset': s.PointerToRawData, 'raw_size': s.SizeOfRawData,
                 'virtual_size': s.Misc_VirtualSize, 'entropy': round(s.get_entropy(), 3)} for s in pe.sections]
    # Printable ASCII and UTF-8 strings with binary offsets; these are evidence, not source code.
    string_count = 0
    with (analysis / 'strings_utf8.txt').open('w', encoding='utf-8') as stream:
        for match in re.finditer(rb'(?:[\x20-\x7e\t]|[\xc2-\xdf][\x80-\xbf]|[\xe0-\xef][\x80-\xbf]{2}|[\xf0-\xf4][\x80-\xbf]{3}){6,}', data):
            text = match.group().decode('utf-8', errors='replace')
            stream.write(f'0x{match.start():08x}\t{text}\n')
            string_count += 1
    wide = [(m.start(), m.group().decode('utf-16le')) for m in re.finditer(rb'(?:[\x20-\x7e]\x00){6,}', data)]
    (analysis / 'strings_utf16.txt').write_text('\n'.join(f'0x{o:08x}\t{s}' for o, s in wide), encoding='utf-8')
    metadata = {'input': str(args.exe.resolve()), 'input_size': len(data),
                'sha256': hashlib.sha256(data).hexdigest(), 'machine': hex(pe.FILE_HEADER.Machine),
                'image_base': hex(base), 'entry_rva': hex(pe.OPTIONAL_HEADER.AddressOfEntryPoint),
                'asset_table_offset': table_start, 'asset_count': len(inventory),
                'compressed_size': sum(x['compressed_size'] for x in inventory),
                'uncompressed_size': sum(x['size'] for x in inventory),
                'extensions': dict(collections.Counter(Path(x['path']).suffix for x in inventory)),
                'errors': errors, 'sections': sections, 'string_count': string_count,
                'native_function_entries': len(getattr(pe, 'DIRECTORY_ENTRY_EXCEPTION', [])),
                'overlay_offset': pe.get_overlay_data_start_offset()}
    for filename, obj in [('metadata.json', metadata), ('assets.json', inventory),
                          ('imports.json', imports), ('resources.json', resource_inventory)]:
        (analysis / filename).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(metadata, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit('Some assets failed to decompress; see metadata.json')


if __name__ == '__main__':
    main()
