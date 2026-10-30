"""Copy files to an OP-XY in MTP file-transfer mode, or list and read them.

    python sdk.py device push <builds>/mine-001/candidate [--record <dir>]
    python sdk.py device list [/content/display]
    python sdk.py device pull /content/op1_factory.json --out <file>

`push` mirrors a folder onto the device root: <folder>/os.ldr goes to /os.ldr,
<folder>/content/... to /content/..., creating missing folders. Before writing
it backs up every file it will replace, then writes only changed files, reads
each one back byte for byte, and on any failure restores the backed-up files.
It never deletes anything it did not replace, never writes firmware to the boot
partition and never ejects. The record folder (default under the private
OPXY-SDK folder, outside every checkout) keeps transfer.json and the backups.
Windows only (tooling/wpd.py); on a Mac use the browser builder's transfer.
"""
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import sys

from .formats import require


def sha(data):
    return hashlib.sha256(data).hexdigest()


def private_root():
    if sys.platform == 'darwin':
        return Path.home() / 'Library/Application Support/OPXY-SDK/private'
    return Path(os.environ.get('LOCALAPPDATA') or Path.home() / '.local/share') / 'OPXY-SDK/private'


def source_files(folder):
    """{device path parts: bytes} for every file below folder."""
    folder = Path(folder)
    require(folder.is_dir(), f'Not a folder: {folder}')
    files = {}
    for path in sorted(folder.rglob('*')):
        require(not path.is_symlink(), f'Refusing a symbolic link: {path}')
        if path.is_file():
            files[path.relative_to(folder).parts] = path.read_bytes()
    require(files, f'No files below {folder}')
    return files


def child(device, parent, name):
    matches = [x for x in device.list(parent) if x.name == name]
    require(len(matches) <= 1, f'More than one {name} on the device')
    return matches[0] if matches else None


def resolve(device, root, folders):
    """The id of an existing folder path, or None if any part is missing."""
    parent = root
    for index, name in enumerate(folders):
        entry = child(device, parent, name)
        if entry is None:
            return None
        require(entry.folder, f'/{"/".join(folders[:index + 1])} is a file where a folder is needed')
        parent = entry.id
    return parent


def make_folders(device, root, folders, created):
    parent = root
    for index, name in enumerate(folders):
        entry = child(device, parent, name)
        if entry is None:
            like = next((x for x in device.list(parent) if x.folder), None)
            device.create_folder(parent, name, like)
            entry = child(device, parent, name)
            require(entry is not None and entry.folder, f'Creating /{"/".join(folders[:index + 1])} failed')
            created.append('/' + '/'.join(folders[:index + 1]))
        require(entry.folder, f'/{"/".join(folders[:index + 1])} is a file where a folder is needed')
        parent = entry.id
    return parent


def write(device, parent, name, data, old):
    like = old or next((x for x in device.list(parent) if not x.folder), None)
    if old is not None:
        device.delete(old)
        require(child(device, parent, name) is None, f'Deleting the old {name} was not confirmed')
    device.create_file(parent, name, data, like)


def verify(device, parent, name, data):
    entry = child(device, parent, name)
    require(entry is not None and entry.size == len(data) and device.read(entry) == data,
            f'Readback of {name} differs from the source')


def push(device, folder, record):
    """Mirror folder onto the device; returns the transfer report."""
    files = source_files(folder)
    record = Path(record)
    record.mkdir(parents=True, exist_ok=False)
    report = {'source': str(Path(folder).resolve()), 'files': [], 'created_folders': [], 'complete': False,
              'firmware_written': False, 'ejected': False}

    def save():
        (record / 'transfer.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')

    save()
    root = device.root()
    require(not any((x.name or '').lower().endswith('.tfw') for x in device.list(root)),
            'A firmware update (.tfw) is waiting in the device root; finish or remove it first')
    tasks = []
    for parts, data in files.items():
        path = '/' + '/'.join(parts)
        parent = resolve(device, root, parts[:-1])
        old = child(device, parent, parts[-1]) if parent else None
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
            parent = make_folders(device, root, parts[:-1], report['created_folders'])
            if entry['changed']:
                live = child(device, parent, parts[-1])
                require((live is None) == (old is None) and (live is None or live.id == old.id),
                        f'{entry["path"]} changed on the device after the backup')
                done.append((parts, before, entry))
                entry['written'] = True
                write(device, parent, parts[-1], data, live)
                print('copied ' + entry['path'], flush=True)
            verify(device, parent, parts[-1], data)
            entry['verified'] = True
            save()
        for parts, data, _, _, _ in tasks:
            verify(device, resolve(device, root, parts[:-1]), parts[-1], data)
        report['complete'] = True
        save()
        return report
    except Exception as error:
        report['error'] = str(error)
        for parts, before, entry in reversed(done):
            try:
                parent = resolve(device, root, parts[:-1])
                current = child(device, parent, parts[-1]) if parent else None
                if current is not None:
                    device.delete(current)
                if before is not None:
                    device.create_file(parent, parts[-1], before, current)
                    verify(device, parent, parts[-1], before)
                entry['rolled_back'] = True
            except Exception as rollback_error:
                entry['rollback_error'] = str(rollback_error)
        save()
        raise


def entry_at(device, path):
    parts = PurePosixPath('/' + path.strip('/')).parts[1:]
    root = device.root()
    if not parts:
        return root, None
    parent = resolve(device, root, parts[:-1])
    entry = child(device, parent, parts[-1]) if parent else None
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
    p.add_argument('--record', type=Path, help='New folder for the transfer record and backups')
    p = commands.add_parser('list', help='List a device folder')
    p.add_argument('path', nargs='?', default='/')
    p = commands.add_parser('pull', help='Read one device file')
    p.add_argument('path')
    p.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'push':
            files = source_files(args.folder)  # Fail on a bad source before touching the device.
            record = args.record or private_root() / 'transfers' / datetime.now().strftime('%Y%m%d-%H%M%S-%f')
            with connect() as device:
                try:
                    report = push(device, args.folder, record)
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
            with connect() as device:
                _, entry = entry_at(device, args.path)
                require(entry is not None and not entry.folder, f'{args.path} is not a file')
                data = device.read(entry)
            args.out.write_bytes(data)
            print(f'{args.out}: {len(data)} bytes, sha256 {sha(data)}')
    except (ValueError, OSError) as error:
        parser.exit(1, 'FAIL: ' + str(error) + '\n')
    return 0
