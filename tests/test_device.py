"""Device transfer: backups, readback, rollback and refusals, on an in-memory device."""
import contextlib
import io
import json
from pathlib import Path, PurePosixPath
import shutil
import tempfile
import unittest

from tooling import device as transfer
from tooling.wpd import Entry


class FakeDevice:
    """A tree of folders and files with WPD-like ids; fail_on and corrupt break one write of that name."""

    def __init__(self, files=(), folders=()):
        self.nodes = {'root': ('DEVICE', 'OP-XY', None)}  # id: (parent, name, bytes or None for a folder)
        self.next = 0
        self.fail_on = None
        self.corrupt = None
        self.writes = []
        self.likes = {}
        self.interrupt = None
        for path in folders:
            self.folder(path)
        for path, data in dict(files).items():
            self.put(path, data)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def _id(self):
        self.next += 1
        return f'o{self.next}'

    def folder(self, path):
        parent = 'root'
        for name in PurePosixPath(path).parts[1:]:
            found = [i for i, n in self.nodes.items() if n and n[0] == parent and n[1] == name]
            if found:
                parent = found[0]
            else:
                new = self._id()
                self.nodes[new] = (parent, name, None)
                parent = new
        return parent

    def put(self, path, data):
        path = PurePosixPath(path)
        parent = self.folder(path.parent)
        parts = path.parts
        self.nodes[self._id()] = (parent, parts[-1], bytes(data))

    def get(self, path):
        path = PurePosixPath(path)
        parent = self.folder(path.parent)
        parts = path.parts
        found = [n[2] for n in self.nodes.values() if n and n[0] == parent and n[1] == parts[-1]]
        return found[0] if found else None

    def root(self):
        return 'root'

    def list(self, parent):
        return [Entry(i, n[1], 0 if n[2] is None else len(n[2]), n[2] is None)
                for i, n in self.nodes.items() if n and n[0] == parent]

    def read(self, entry):
        return self.nodes[entry.id][2]

    def delete(self, entry):
        if entry.folder:
            raise ValueError('folders are never deleted')
        del self.nodes[entry.id]

    def create_file(self, parent, name, data, like=None):
        self.writes.append(name)
        self.likes[name] = like
        if name == self.interrupt:
            self.interrupt = None
            raise KeyboardInterrupt
        if name == self.fail_on:
            self.fail_on = None  # Fails once; the rollback's rewrite succeeds.
            raise OSError('write failed')
        corrupt, self.corrupt = name == self.corrupt, None if name == self.corrupt else self.corrupt
        self.nodes[self._id()] = (parent, name, bytes(data[:-1] if corrupt else data))

    def create_folder(self, parent, name, like=None):
        self.nodes[self._id()] = (parent, name, None)


def candidate(folder, files):
    for path, data in files.items():
        target = Path(folder, path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    return Path(folder)


class DeviceTransferTests(unittest.TestCase):
    def setUp(self):
        self.temp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.temp, ignore_errors=True)
        self.source = candidate(self.temp / 'candidate', {'os.ldr': b'new os', 'content/op1_factory.json': b'{}',
                                                          'content/display/mine.svg': b'<svg/>'})

    def files(self):
        return transfer.source_files(self.source)[0]

    def record(self):
        return json.loads((self.temp / 'record/transfer.json').read_text(encoding='utf-8'))

    def test_push_replaces_backs_up_creates_folders_and_verifies(self):
        device = FakeDevice({'/os.ldr': b'old os', '/content/op1_factory.json': b'{}', '/content/keep.txt': b'k'})
        report = transfer.push(device, self.files(), self.temp / 'record')
        self.assertTrue(report['complete'])
        self.assertEqual(device.get('/os.ldr'), b'new os')
        self.assertEqual(device.get('/content/display/mine.svg'), b'<svg/>')
        self.assertEqual(device.get('/content/keep.txt'), b'k')
        self.assertEqual(report['created_folders'], ['/content/display'])
        self.assertEqual((self.temp / 'record/before/os.ldr').read_bytes(), b'old os')
        self.assertNotIn('op1_factory.json', device.writes, 'An unchanged file is not rewritten')
        self.assertTrue(all(x['verified'] for x in self.record()['files']))

    def test_failed_write_restores_replaced_files(self):
        device = FakeDevice({'/os.ldr': b'old os', '/content/op1_factory.json': b'old'})
        device.fail_on = 'os.ldr'  # Written last, after the other two succeeded.
        with self.assertRaisesRegex(OSError, 'write failed'):
            transfer.push(device, self.files(), self.temp / 'record')
        self.assertEqual(device.get('/os.ldr'), b'old os')
        self.assertEqual(device.get('/content/op1_factory.json'), b'old')
        self.assertIsNone(device.get('/content/display/mine.svg'))
        record = self.record()
        self.assertFalse(record['complete'])
        written = [x['path'] for x in record['files'] if x.get('written')]
        self.assertEqual(written, ['/content/display/mine.svg', '/content/op1_factory.json', '/os.ldr'])
        self.assertTrue(all(x.get('rolled_back') for x in record['files'] if x.get('written')))

    def test_readback_mismatch_fails_and_rolls_back(self):
        device = FakeDevice({'/os.ldr': b'old os'})
        device.corrupt = 'os.ldr'
        with self.assertRaisesRegex(ValueError, 'Readback of os.ldr'):
            transfer.push(device, self.files(), self.temp / 'record')
        self.assertEqual(device.get('/os.ldr'), b'old os')

    def test_refuses_pending_firmware_update_before_writing(self):
        device = FakeDevice({'/update.tfw': b'x', '/os.ldr': b'old os'})
        with self.assertRaisesRegex(ValueError, 'firmware update'):
            transfer.push(device, self.files(), self.temp / 'record')
        self.assertEqual(device.writes, [])

    def test_refuses_folder_in_place_of_file_and_file_in_place_of_folder(self):
        with self.assertRaisesRegex(ValueError, 'is a folder'):
            transfer.push(FakeDevice(folders=['/os.ldr']), self.files(), self.temp / 'record')
        with self.assertRaisesRegex(ValueError, 'where a folder is needed'):
            transfer.push(FakeDevice({'/content': b'file'}), self.files(), self.temp / 'record2')

    def test_record_folder_must_be_new(self):
        (self.temp / 'record').mkdir()
        with self.assertRaises(FileExistsError):
            transfer.push(FakeDevice(), self.files(), self.temp / 'record')

    def test_interrupt_mid_write_restores_and_records(self):
        device = FakeDevice({'/os.ldr': b'old os', '/content/op1_factory.json': b'old'})
        device.interrupt = 'os.ldr'
        with self.assertRaises(KeyboardInterrupt):
            transfer.push(device, self.files(), self.temp / 'record')
        self.assertEqual(device.get('/os.ldr'), b'old os')
        self.assertEqual(device.get('/content/op1_factory.json'), b'old')
        self.assertEqual(self.record()['error'], 'KeyboardInterrupt')

    def test_record_must_be_outside_every_checkout(self):
        checkout = self.temp / 'checkout'
        (checkout / '.git').mkdir(parents=True)
        device = FakeDevice({'/os.ldr': b'old os'})
        with self.assertRaisesRegex(ValueError, 'outside every checkout'):
            transfer.push(device, self.files(), checkout / 'local/record')
        self.assertFalse((checkout / 'local').exists())
        self.assertEqual(device.writes, [])

    def test_source_skips_junk_and_refuses_a_whole_build_folder(self):
        candidate(self.source, {'Thumbs.db': b'x', 'content/._mine.svg': b'x', 'content/desktop.ini': b'x'})
        files, skipped = transfer.source_files(self.source)
        self.assertEqual(sorted(files), [('content', 'display', 'mine.svg'), ('content', 'op1_factory.json'), ('os.ldr',)])
        self.assertEqual(sorted(skipped), ['Thumbs.db', 'content/._mine.svg', 'content/desktop.ini'])
        with self.assertRaisesRegex(ValueError, 'push its candidate folder'):
            transfer.source_files(self.temp)

    def test_names_match_without_case_and_new_files_take_no_sibling_type(self):
        device = FakeDevice({'/CONTENT/op1_factory.json': b'old', '/CONTENT/sample.wav': b'w'})
        transfer.push(device, self.files(), self.temp / 'record')
        self.assertEqual(device.get('/CONTENT/op1_factory.json'), b'{}')
        tops = [n[1] for n in device.nodes.values() if n[0] == 'root']
        self.assertEqual(tops, ['CONTENT', 'os.ldr'], 'The existing folder is reused, not a second "content"')
        self.assertIsNotNone(device.likes['op1_factory.json'], 'A replaced file keeps its own type')
        self.assertIsNone(device.likes['mine.svg'], 'A new file never borrows a sibling type')

    def test_cli_push_list_and_pull(self):
        device = FakeDevice({'/content/op1_factory.json': b'{"a":1}'})
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            transfer.main(['push', str(self.source), '--record', str(self.temp / 'record')], connect=lambda: device)
            transfer.main(['list', '/content'], connect=lambda: device)
            transfer.main(['pull', '/os.ldr', '--out', str(self.temp / 'os.ldr')], connect=lambda: device)
        self.assertIn('PASS: 3 files', out.getvalue())
        self.assertIn('display/', out.getvalue())
        self.assertEqual((self.temp / 'os.ldr').read_bytes(), b'new os')

    def test_cli_rejects_bad_source_without_connecting(self):
        def connect():
            raise AssertionError('connected')
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as stop:
            transfer.main(['push', str(self.temp / 'missing')], connect=connect)
        self.assertEqual(stop.exception.code, 1)


if __name__ == '__main__':
    unittest.main()
