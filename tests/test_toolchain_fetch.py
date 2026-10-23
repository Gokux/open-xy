"""Toolchain fetch: archive hash, safe extraction and atomic install, with synthetic archives."""
import functools
import hashlib
import http.server
import json
from pathlib import Path
import tempfile
import threading
import unittest
import zipfile

from tooling import toolchain

ROOT = Path(__file__).resolve().parents[1]
FOLDER = 'open-xy-toolchain-test'


def archive(path, names):
    with zipfile.ZipFile(path, 'w') as files:
        for name in names:
            info = zipfile.ZipInfo(name)
            info.external_attr = (0o100755 if '/bin/' in name else 0o100644) << 16
            files.writestr(info, name.encode())
    return {'url': 'unused', 'folder': FOLDER, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def accept(directory):
    pass


class ToolchainFetchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    def test_installs_once_and_keeps_an_installed_copy(self):
        record = archive(self.root / 'a.zip', [f'{FOLDER}/bin/bfin-elf-as', f'{FOLDER}/lib/libgcc.a'])
        target = self.root / 'toolchain'
        self.assertTrue(toolchain.fetch(record, target, self.root / 'a.zip', check=accept))
        self.assertEqual((target / 'lib/libgcc.a').read_bytes(), f'{FOLDER}/lib/libgcc.a'.encode())
        self.assertFalse(toolchain.fetch(record, target, self.root / 'a.zip', check=accept))

        def reject(directory):
            raise ValueError('Tool hash mismatch')
        with self.assertRaisesRegex(ValueError, 'remove it and fetch again'):
            toolchain.fetch(record, target, self.root / 'a.zip', check=reject)

    def test_rejects_wrong_hash_and_unsafe_entries_without_installing(self):
        target = self.root / 'toolchain'
        record = archive(self.root / 'a.zip', [f'{FOLDER}/bin/x'])
        with self.assertRaisesRegex(ValueError, 'Archive hash mismatch'):
            toolchain.fetch(dict(record, sha256='0' * 64), target, self.root / 'a.zip', check=accept)
        for name in (f'{FOLDER}/../escape', 'other/bin/x', f'/{FOLDER}/x', f'{FOLDER}\\..\\x'):
            record = archive(self.root / 'b.zip', [name])
            with self.assertRaisesRegex(ValueError, 'Unexpected archive entry'):
                toolchain.fetch(record, target, self.root / 'b.zip', check=accept)
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ['a.zip', 'b.zip'])

    def test_downloads_the_recorded_url(self):
        served = self.root / 'served'
        served.mkdir()
        record = archive(served / 'tools.zip', [f'{FOLDER}/bin/x'])
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(served))
        handler.log_message = lambda *args: None
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        record['url'] = f'http://127.0.0.1:{server.server_address[1]}/tools.zip'
        self.assertTrue(toolchain.fetch(record, self.root / 'toolchain', check=accept))
        self.assertTrue((self.root / 'toolchain/bin/x').is_file())
        self.assertFalse((self.root / 'toolchain/archive.zip').exists())

    def test_download_records_name_their_host_folder(self):
        pins = json.loads((ROOT / 'profiles/toolchains.json').read_text('utf-8'))
        for host, entry in pins['hosts'].items():
            if 'download' in entry:
                record = entry['download']
                self.assertEqual(record['folder'], 'open-xy-toolchain-' + host)
                self.assertTrue(record['url'].startswith('https://') and record['url'].endswith(record['folder'] + '.zip'))
                self.assertRegex(record['sha256'], '^[0-9a-f]{64}$')


if __name__ == '__main__':
    unittest.main()
