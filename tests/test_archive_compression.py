from pathlib import Path
import json
import sys
import tempfile
import unittest
import zipfile

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'tools'))
sys.path.insert(0, str(PROJECT / 'src'))
from make_update import make
from desktop_updater import unpack


class ArchiveCompressionTests(unittest.TestCase):
    def test_lzma_update_uses_existing_reader_and_preserves_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = root / 'payload'
            payload.mkdir()
            contents = {
                'WuwaTappo.Local.exe': b'pet-data' * 100,
                'LocalGalleryHost.exe': b'host-data' * 100,
                'package_config.json': json.dumps({
                    'mod_version': '1.3.7', 'client_version': '1.0.4'
                }).encode(),
            }
            for name, data in contents.items():
                (payload / name).write_bytes(data)
            archive = root / 'update.zip'
            make(payload, archive)
            with zipfile.ZipFile(archive) as reader:
                self.assertTrue(all(info.compress_type == zipfile.ZIP_LZMA
                                    for info in reader.infolist()))
            stage = root / 'stage'
            unpack(archive, stage)
            for name, data in contents.items():
                self.assertEqual((stage / name).read_bytes(), data)


if __name__ == '__main__':
    unittest.main()
