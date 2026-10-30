"""Copy files to an OP-XY in MTP file-transfer mode, or list and read them.

    python sdk.py device push <builds>/mine-001/candidate [--record <dir>]
    python sdk.py device list [/content/display]
    python sdk.py device pull /content/op1_factory.json --out <file>

`push` mirrors a folder onto the device root: <folder>/os.ldr goes to /os.ldr,
<folder>/content/... to /content/..., creating missing folders. Before writing
it backs up every file it will replace, then writes only changed files, reads
each one back byte for byte, and on any failure or interruption restores the
backed-up files. It never deletes anything it did not replace, never writes
firmware to the boot partition and never ejects. The record folder (default
under the private OPXY-SDK folder; always outside every checkout, since backups
hold stock firmware) keeps transfer.json and the backups. Windows only
(tooling/wpd.py); on a Mac use the browser builder's transfer.
"""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path, PurePosixPath
import sys

from .formats import require, sha
from .release import outside_checkouts

# Explorer and Finder leave these beside copied files; they never belong on the device.
JUNK = {'thumbs.db', 'desktop.ini', '.ds_store'}


def private_root():
    if sys.platform == 'darwin':
        return Path.home() / 'Library/Application Support/OPXY-SDK/private'
    return Path(os.environ.get('LOCALAPPDATA') or Path.home() / '.local/share') / 'OPXY-SDK/private'


def source_files(folder):
    """({device path parts: bytes}, [skipped junk paths]) for every file below folder."""
    folder = Path(folder)
    require(folder.is_dir(), f'Not a folder: {folder}')
    require(not (folder / 'candidate').is_dir() or (folder / 'os.ldr').exists(),
            f'{folder} holds a build; push its candidate folder: {folder / "candidate"}')
    files, skipped = {}, []
    for path in sorted(folder.rglob('*')):
        require(not path.is_symlink(), f'Refusing a symbolic link: {path}')
        parts = path.relative_to(folder).parts
        if path.name.lower() in JUNK or path.name.startswith('._'):
            skipped.append('/'.join(parts))
        elif path.is_file():
            files[parts] = path.read_bytes()
    require(files, f'No files below {folder}')
    return files, skipped


class Listings:
    """Device access with each folder listed once until something in it changes."""

    def __init__(self, device):
        self.device, self.cache = device, {}

    def list(self, parent):
        if parent not in self.cache:
            self.cache[parent] = self.device.list(parent)
        return self.cache[parent]

    def child(self, parent, name):
        # The device's FAT storage ignores case, so matching must too.
        matches = [x for x in self.list(parent) if (x.name or '').casefold() == name.casefold()]
        require(len(matches) <= 1, f'More than one {name} on the device')
        return matches[0] if matches else None

    def read(self, entry):
        return self.device.read(entry)

    def delete(self, parent, entry):
        self.device.delete(entry)
        self.cache.pop(parent, None)
        require(self.child(parent, entry.name) is None, f'Deleting {entry.name} was not confirmed')

    def create_file(self, parent, name, data, like):
        self.cache.pop(parent, None)
        try:
            self.device.create_file(parent, name, data, like)
        finally:
            self.cache.pop(parent, None)

    def create_folder(self, parent, name, like):
        self.cache.pop(parent, None)
        self.device.create_folder(parent, name, like)
        self.cache.pop(parent, None)

    def resolve(self, root, folders, create=None):
        """The id of a folder path; a missing part gives None, or is made and noted in create."""
        parent = root
        for index, name in enumerate(folders):
            path = '/' + '/'.join(folders[:index + 1])
            entry = self.child(parent, name)
            if entry is None:
                if create is None:
                    return None
                self.create_folder(parent, name, next((x for x in self.list(parent) if x.folder), None))
                entry = self.child(parent, name)
                require(entry is not None and entry.folder, f'Creating {path} failed')
                create.append(path)
            require(entry.folder, f'{path} is a file where a folder is needed')
            parent = entry.id
        return parent

    def verify(self, parent, name, data):
        entry = self.child(parent, name)
        require(entry is not None and entry.size == len(data) and self.read(entry) == data,
                f'Readback of {name} differs from the source')


def push(device, files, record):
    """Mirror files ({device path parts: bytes}) onto the device; returns the transfer report."""
    record = Path(record)
    require(outside_checkouts(record), f'Keep the transfer record outside every checkout: backups hold stock firmware ({record})')
    record.mkdir(parents=True, exist_ok=False)
    report = {'files': [], 'created_folders': [], 'complete': False, 'firmware_written': False, 'ejected': False}

    def save():
        (record / 'transfer.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')

    save()
    device = Listings(device)
    root = device.device.root()
    require(not any((x.name or '').lower().endswith('.tfw') for x in device.list(root)),
            'A firmware update (.tfw) is waiting in the device root; finish or remove it first')
    tasks = []
    for parts, data in files.items():
        path = '/' + '/'.join(parts)
        parent = device.resolve(root, parts[:-1])
        old = device.child(parent, parts[-1]) if parent else None
        require(old is None or not old.folder, f'{path} is a folder on the device')
        before = device.read(old) if old else None
        if before is not None:
            backup = record.joinpath('before', *parts)
            backup.parent.mkdir(parents=True, exist_ok=True)
            backup.write_bytes(before)
        entry = {'path': path, 'bytes': len(data), 'sha256': sha(data),
                 'before_sha256': sha(before) if before is not None else None,
                 'changed': before != data, 'verified': False}
        report['files'].append(entry)
        tasks.append((parts, data, old, before, entry))
    save()
    done = []
    try:
        for parts, data, old, before, entry in tasks:
            parent = device.resolve(root, parts[:-1], report['created_folders'])
            if entry['changed']:
                live = device.child(parent, parts[-1])
                require((live is None) == (old is None) and (live is None or live.id == old.id),
                        f'{entry["path"]} changed on the device after the backup')
                done.append((parts, before, entry))
                entry['written'] = True
                save()  # Recorded before the device changes, so an interruption still shows it.
                if live is not None:
                    device.delete(parent, live)
                # Only the replaced file's own type carries over; a sibling's may be unrelated.
                device.create_file(parent, parts[-1], data, live)
                print('copied ' + entry['path'], flush=True)
            device.verify(parent, parts[-1], data)
            entry['verified'] = True
            save()
        device.cache.clear()
        for parts, data, _, _, _ in tasks:
            device.verify(device.resolve(root, parts[:-1]), parts[-1], data)
        report['complete'] = True
        save()
        return report
    except BaseException as error:  # Ctrl+C mid-write must still restore the backups.
        report['error'] = str(error) or type(error).__name__
        device.cache.clear()
        for parts, before, entry in reversed(done):
            try:
                parent = device.resolve(root, parts[:-1])
                current = device.child(parent, parts[-1]) if parent else None
                if current is not None:
                    device.delete(parent, current)
                if before is not None:
                    device.create_file(parent, parts[-1], before, current)
                    device.verify(parent, parts[-1], before)
                entry['rolled_back'] = True
            except Exception as rollback_error:
                entry['rollback_error'] = str(rollback_error)
        save()
        raise


def entry_at(device, path):
    device = Listings(device)
    parts = PurePosixPath('/' + path.strip('/')).parts[1:]
    root = device.device.root()
    if not parts:
        return root, None
    parent = device.resolve(root, parts[:-1])
    entry = device.child(parent, parts[-1]) if parent else None
    require(entry is not None, f'Nothing at {path} on the device')
    return entry.id, entry


def open_device():
    from .wpd import Device
    return Device()


def main(argv=None, connect=open_device):
    parser = argparse.ArgumentParser(prog='sdk.py device', description=__doc__.split('\n\n')[0])
    commands = parser.add_subparsers(dest='command', required=True)
    p = commands.add_parser('push', help='Mirror a folder onto the device root')
    p.add_argument('folder', type=Path, help='Folder laid out like the device, such as <build>/candidate')
    p.add_argument('--record', type=Path, help='New folder outside every checkout for the record and backups')
    p = commands.add_parser('list', help='List a device folder')
    p.add_argument('path', nargs='?', default='/')
    p = commands.add_parser('pull', help='Read one device file')
    p.add_argument('path')
    p.add_argument('--out', type=Path, required=True, help='New file outside every checkout')
    args = parser.parse_args(argv)
    try:
        if args.command == 'push':
            files, skipped = source_files(args.folder)  # A bad source fails before the device is touched.
            for path in skipped:
                print('skipped ' + path, flush=True)
            record = args.record or private_root() / 'transfers' / datetime.now().strftime('%Y%m%d-%H%M%S-%f')
            with connect() as device:
                try:
                    report = push(device, files, record)
                finally:
                    print('Transfer record: ' + str(record), flush=True)
            changed = sum(x['changed'] for x in report['files'])
            print(f'PASS: {len(files)} files on the device and read back ({changed} changed). '
                  'Firmware not written to the boot partition.')
        elif args.command == 'list':
            with connect() as device:
                folder, entry = entry_at(device, args.path)
                require(entry is None or entry.folder, f'{args.path} is a file')
                for x in sorted(device.list(folder), key=lambda x: (not x.folder, x.name or '')):
                    print(f'{x.name}/' if x.folder else f'{x.name}  {x.size}')
        else:
            require(not args.out.exists(), f'{args.out} already exists')
            require(outside_checkouts(args.out), f'Keep device files outside every checkout: they may be stock ({args.out})')
            with connect() as device:
                _, entry = entry_at(device, args.path)
                require(entry is not None and not entry.folder, f'{args.path} is not a file')
                data = device.read(entry)
            args.out.write_bytes(data)
            print(f'{args.out}: {len(data)} bytes, sha256 {sha(data)}')
    except Exception as error:  # Includes the driver's COMError, which is not an OSError.
        parser.exit(1, 'FAIL: ' + str(error) + '\n')
    return 0
