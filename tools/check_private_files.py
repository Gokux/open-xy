"""Reject private build inputs/artifacts in the index or Git history.

Uses Git objects, so checks staged bytes rather than a potentially different
working file. No firmware or other private fixture is needed by this check.
"""
import argparse
from functools import reduce
from operator import xor
from pathlib import PurePosixPath
import subprocess
import sys

PRIVATE_DIRS = {'local', 'stock', 'extracted', 'dumps', 'toolchain', 'build', 'dist'}
PRIVATE_SUFFIXES = {'.ldr', '.tfw', '.zfw', '.bin', '.elf', '.o', '.map', '.zip',
                    '.exe', '.dll', '.dmp', '.dump', '.7z', '.rar', '.gz', '.xz'}


def git(*args):
    return subprocess.check_output(['git', *args])


def path_problem(name):
    path = PurePosixPath(name.lower())
    if PRIVATE_DIRS.intersection(path.parts[:-1]):
        return 'private input/output directory'
    if path.suffix in PRIVATE_SUFFIXES:
        return 'private firmware/build artifact extension'
    if path.name == '.env' or path.name.startswith('.env.'):
        return 'local environment file'
    return None


def content_problem(data):
    # A Blackfin LDR header has the AD signature and an XOR checksum of zero.
    # This catches original and patched images even when the file is renamed.
    if len(data) >= 16 and data[3] == 0xad and reduce(xor, data[:16]) == 0:
        return 'Blackfin firmware container'
    if data.startswith((b'PK\x03\x04', b'PK\x05\x06', b'\x1f\x8b', b'7z\xbc\xaf\x27\x1c', b'Rar!', b'\xfd7zXZ\0')):
        return 'archive payload (may contain private inputs)'
    if data.startswith((b'\x7fELF', b'MZ')):
        return 'compiled executable/object payload'
    return None


def scan(staged=False, tree=None, all_objects=False):
    problems, objects = [], {}
    def add(oid, name):
        reason = path_problem(name)
        if reason:
            problems.append(f'{name}: {reason}')
        objects.setdefault(oid, name)
    if staged:
        for record in git('ls-files', '--stage', '-z').split(b'\0'):
            if not record:
                continue
            metadata, name = record.split(b'\t', 1)
            add(metadata.split()[1].decode(), name.decode('utf-8', 'replace'))
    elif tree:
        for record in git('ls-tree', '-rz', tree).split(b'\0'):
            if not record:
                continue
            metadata, name = record.split(b'\t', 1)
            if metadata.split()[1] == b'blob':
                add(metadata.split()[2].decode(), name.decode('utf-8', 'replace'))
    else:
        for line in git('rev-list', '--objects', '--all', '--reflog').decode('utf-8', 'replace').splitlines():
            oid, _, name = line.partition(' ')
            if name:
                add(oid, name)
        # Inspect every historical pathname, including renames of an object
        # that rev-list may have listed under a different representative name.
        names = git('log', '--all', '--reflog', '--format=', '--name-only', '-z')
        for raw in names.split(b'\0'):
            name = raw.decode('utf-8', 'replace').strip('\n')
            if name and (reason := path_problem(name)):
                problems.append(f'{name}: {reason}')
    if all_objects:
        for line in git('cat-file', '--batch-all-objects', '--batch-check=%(objectname) %(objecttype)').splitlines():
            oid, kind = line.split()
            if kind == b'blob':
                objects.setdefault(oid.decode(), '(unreachable or unnamed blob)')
    # Batch streaming keeps private bytes out of stdout and avoids one process
    # per object. Oversized blobs fail without loading them into memory.
    process = subprocess.Popen(['git', 'cat-file', '--batch'], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    count = 0
    try:
        for oid, name in objects.items():
            process.stdin.write((oid + '\n').encode()); process.stdin.flush()
            header = process.stdout.readline().split()
            if len(header) != 3:
                raise ValueError('Cannot inspect Git object ' + oid)
            size = int(header[2])
            first = process.stdout.read(min(size, 4096))
            remaining = size - len(first)
            while remaining:
                chunk = process.stdout.read(min(remaining, 1024 * 1024))
                if not chunk:
                    raise ValueError('Truncated Git object')
                remaining -= len(chunk)
            process.stdout.read(1)
            if header[1] != b'blob':
                continue
            count += 1
            reason = content_problem(first)
            if size > 16 * 1024 * 1024:
                reason = 'oversized blob; private artifacts are not source'
            if reason:
                problems.append(f'{name} [{oid[:12]}]: {reason}')
    finally:
        process.stdin.close(); process.stdout.close(); process.wait()
    return count, sorted(set(problems))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--staged', action='store_true')
    modes.add_argument('--tree')
    modes.add_argument('--history', action='store_true')
    parser.add_argument('--all-objects', action='store_true', help='Also audit unreachable objects; use with --history')
    args = parser.parse_args()
    if args.all_objects and not args.history:
        parser.error('--all-objects requires --history')
    count, problems = scan(args.staged, args.tree, args.all_objects)
    if problems:
        print('BLOCKED: private data must stay outside Git:', file=sys.stderr)
        for item in problems:
            print('  ' + item, file=sys.stderr)
        return 1
    print(f'PASS: {count} Git blobs checked; no forbidden paths or firmware/archive/executable signatures.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
