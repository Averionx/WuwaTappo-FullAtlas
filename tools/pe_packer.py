# Add a read-only PE section and redirect the existing relocated asset-slice pointers.
source = BASE / 'WuwaTappo.official.exe'
data = bytearray(source.read_bytes())
pe = pefile.PE(data=bytes(data))
cert = pe.OPTIONAL_HEADER.DATA_DIRECTORY[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_SECURITY']]
struct.pack_into('<II', data, cert.get_file_offset(), 0, 0)
last = max(pe.sections, key=lambda s: s.PointerToRawData + s.SizeOfRawData)
end_raw = max(s.PointerToRawData + s.SizeOfRawData for s in pe.sections)
# The trailing bytes are the original Authenticode certificate, not application payload.
assert pe.get_overlay_data_start_offset() == end_raw
data = data[:end_raw]
align = lambda n, a: (n + a - 1) // a * a
raw_start = align(len(data), pe.OPTIONAL_HEADER.FileAlignment)
new_rva = align(max(s.VirtualAddress + max(s.Misc_VirtualSize, s.SizeOfRawData) for s in pe.sections), pe.OPTIONAL_HEADER.SectionAlignment)
payload = bytearray(); asset_changes = []
inventory = json.loads((ORIGINAL / 'analysis/assets.json').read_text(encoding='utf-8'))
for name in [shared_name, main_name, panel_name]:
    row = next(x for x in inventory if x['path'] == '/assets/' + name)
    plain = (frontend / 'assets' / name).read_bytes()
    packed = brotli.compress(plain, quality=11)
    while len(payload) % 8: payload.append(0)
    asset_rva = new_rva + len(payload)
    payload += packed
    struct.pack_into('<QQ', data, row['table_offset'] + 16, pe.OPTIONAL_HEADER.ImageBase + asset_rva, len(packed))
    old_hash = base64.b64encode(hashlib.sha256((ORIGINAL / 'frontend/assets' / name).read_bytes()).digest())
    new_hash = base64.b64encode(hashlib.sha256(plain).digest())
    assert data.count(old_hash) == 1
    data = bytearray(data.replace(old_hash, new_hash))
    asset_changes.append({'path': row['path'], 'rva': hex(asset_rva), 'compressed_size': len(packed), 'size': len(plain), 'sha256': hashlib.sha256(plain).hexdigest()})
# A separate application identifier keeps the original process and profile intact.
for old, new in [(b'com.kuro.wuwatappo.cn', b'com.kuro.wuwatappo.lc'), (b'wuwatappo.global', b'wuwatappo.localx')]:
    assert len(old) == len(new)
    assert data.count(old) > 0
    data = bytearray(data.replace(old, new))
# Keep the variant's single-instance mutex and message window separate too.
# Change only the exact Rust formatting literals, not menu permission strings
# containing the word "simple".
for suffix in [b'-sic', b'-siw', b'-sim']:
    old = b'\xc0\x04' + suffix + b'\0'
    new = b'\xc0\x04-f' + suffix[2:] + b'\0'
    assert len(old) == len(new) and data.count(old) == 1
    data = bytearray(data.replace(old, new))
section_header = pe.sections[-1].get_file_offset() + 40
assert section_header + 40 <= min(s.PointerToRawData for s in pe.sections)
assert not any(data[section_header:section_header + 40])
raw_size = align(len(payload), pe.OPTIONAL_HEADER.FileAlignment)
struct.pack_into('<8sIIIIIIHHI', data, section_header, b'.local\0\0', len(payload), new_rva, raw_size, raw_start, 0, 0, 0, 0, 0x40000040)
struct.pack_into('<H', data, pe.FILE_HEADER.get_field_absolute_offset('NumberOfSections'), len(pe.sections) + 1)
struct.pack_into('<I', data, pe.OPTIONAL_HEADER.get_field_absolute_offset('SizeOfImage'), align(new_rva + len(payload), pe.OPTIONAL_HEADER.SectionAlignment))
struct.pack_into('<I', data, pe.OPTIONAL_HEADER.get_field_absolute_offset('SizeOfInitializedData'), pe.OPTIONAL_HEADER.SizeOfInitializedData + raw_size)
data += b'\0' * (raw_start - len(data)) + payload + b'\0' * (raw_size - len(payload))
# Force a private WebView runtime even when the EXE is launched directly. The
# firewall can then block that runtime without blocking other apps' WebViews.
boot_rva = align(new_rva + len(payload), pe.OPTIONAL_HEADER.SectionAlignment)
boot_raw = align(len(data), pe.OPTIONAL_HEADER.FileAlignment)
iat = {imp.name.decode(): imp.address - pe.OPTIONAL_HEADER.ImageBase
       for dll in pe.DIRECTORY_ENTRY_IMPORT for imp in dll.imports if imp.name}
code, labels, fixups = bytearray(), {}, []
def emit(blob):
    code.extend(blob)
def rel(prefix, target):
    emit(prefix); fixups.append((len(code), target)); emit(b'\0' * 4)
# Derive the private runtime and profile from this executable, including
# direct launches. The stack buffer stays below one guard page (MAX_PATH 520).
emit(bytes.fromhex('9c50515241504151415241535356574881ec50040000fc'))
emit(bytes.fromhex('31c9488d54242041b808020000'))
rel(bytes.fromhex('ff15'), iat['GetModuleFileNameW'])
emit(bytes.fromhex('85c0')); rel(bytes.fromhex('0f84'), 'failure')
emit(bytes.fromhex('3df0010000')); rel(bytes.fromhex('0f83'), 'failure')
emit(bytes.fromhex('89c3488d7c2420'))
labels['find_separator']=len(code)
emit(bytes.fromhex('ffcb')); rel(bytes.fromhex('0f88'), 'failure')
emit(bytes.fromhex('66833c5f5c')); rel(bytes.fromhex('0f85'), 'find_separator')
emit(bytes.fromhex('ffc3'))
for name_label, suffix_label in [('runtime_name','runtime_suffix'),('profile_name','profile_suffix')]:
    emit(bytes.fromhex('488d7c2420488d3c5f'))
    rel(bytes.fromhex('488d35'), suffix_label)
    loop=name_label+'_copy';labels[loop]=len(code)
    emit(bytes.fromhex('66ad66ab6685c0')); rel(bytes.fromhex('0f85'),loop)
    rel(bytes.fromhex('488d0d'),name_label)
    emit(bytes.fromhex('488d542420'))
    rel(bytes.fromhex('ff15'),iat['SetEnvironmentVariableW'])
    emit(bytes.fromhex('85c0')); rel(bytes.fromhex('0f84'),'failure')
emit(bytes.fromhex('4881c4500400005f5e5b415b415a415941585a59589d'))
rel(bytes.fromhex('e9'), pe.OPTIONAL_HEADER.AddressOfEntryPoint)
labels['failure']=len(code)
emit(bytes.fromhex('b901000000'));rel(bytes.fromhex('ff15'),iat['ExitProcess']);emit(bytes.fromhex('0f0b'))
for label,value in [('runtime_name','WEBVIEW2_BROWSER_EXECUTABLE_FOLDER'),('runtime_suffix','runtime'),
                    ('profile_name','WEBVIEW2_USER_DATA_FOLDER'),('profile_suffix','profile')]:
    labels[label]=len(code);emit((value+'\0').encode('utf-16le'))
for pos, target in fixups:
    destination = boot_rva + labels[target] if isinstance(target, str) else target
    struct.pack_into('<i', code, pos, destination - (boot_rva + pos + 4))
boot_size = align(len(code), pe.OPTIONAL_HEADER.FileAlignment)
assert not any(data[section_header + 40:section_header + 80])
struct.pack_into('<8sIIIIIIHHI', data, section_header + 40, b'.lboot\0\0', len(code), boot_rva,
                 boot_size, boot_raw, 0, 0, 0, 0, 0x60000020)
struct.pack_into('<H', data, pe.FILE_HEADER.get_field_absolute_offset('NumberOfSections'), len(pe.sections) + 2)
struct.pack_into('<I', data, pe.OPTIONAL_HEADER.get_field_absolute_offset('AddressOfEntryPoint'), boot_rva)
struct.pack_into('<I', data, pe.OPTIONAL_HEADER.get_field_absolute_offset('SizeOfCode'), pe.OPTIONAL_HEADER.SizeOfCode + boot_size)
struct.pack_into('<I', data, pe.OPTIONAL_HEADER.get_field_absolute_offset('SizeOfImage'), align(boot_rva + len(code), pe.OPTIONAL_HEADER.SectionAlignment))
data += b'\0' * (boot_raw - len(data)) + code + b'\0' * (boot_size - len(code))
out = ROOT / 'WuwaTappo.Local.exe'
patched = pefile.PE(data=bytes(data))
struct.pack_into('<I', data, patched.OPTIONAL_HEADER.get_field_absolute_offset('CheckSum'), patched.generate_checksum())
out.write_bytes(data)

# Verify every redirect is still covered by an existing DIR64 ASLR relocation.
patched = pefile.PE(str(out))
relocs = {e.rva for block in patched.DIRECTORY_ENTRY_BASERELOC for e in block.entries if e.type == 10}
for change in asset_changes:
    row = next(x for x in inventory if x['path'] == change['path'])
    pointer_rva = patched.get_rva_from_offset(row['table_offset'] + 16)
    assert pointer_rva in relocs
    va, length = struct.unpack_from('<QQ', data, row['table_offset'] + 16)
    plain = brotli.decompress(patched.get_data(va - patched.OPTIONAL_HEADER.ImageBase, length))
    assert hashlib.sha256(plain).hexdigest() == change['sha256']
assert hashlib.sha256(source.read_bytes()).hexdigest() == hashlib.sha256((BASE / "WuwaTappo.official.exe").read_bytes()).hexdigest()
report = {'input_sha256': hashlib.sha256(source.read_bytes()).hexdigest(), 'output_sha256': hashlib.sha256(data).hexdigest(),
          'output_size': len(data), 'assets': asset_changes, 'patches': patch_log,
          'certificate_removed': True, 'aslr_relocations_verified': True, 'original_modified': False,
          'private_webview_entry_stub': {'rva': hex(boot_rva), 'size': len(code), 'original_entry_rva': hex(pe.OPTIONAL_HEADER.AddressOfEntryPoint)}}
(ROOT / 'build_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({k: v for k, v in report.items() if k != 'patches'}, indent=2))
