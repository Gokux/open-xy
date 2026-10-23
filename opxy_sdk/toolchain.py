"""Install the reviewed Blackfin toolchain from its release archive.

    python sdk.py toolchain fetch [--archive <zip>] [--dir local/toolchain]

Downloads this host's archive named in profiles/toolchains.json (or uses a
copy already downloaded), checks the archive hash, unpacks it and checks every
pinned file before moving it into place. Build commands use the result when
--toolchain and --compiler are omitted. This is the SDK's only network access.
"""
import argparse
import os
from pathlib import Path, PurePosixPath
import shutil
import sys
import urllib.error
import urllib.request
import zipfile

from .formats import require
from .native import compiler_paths, file_hash
from .pipeline import ROOT, TOOLCHAIN_HOME, host_platform, tool_paths, toolchains


def release_record():
    host = host_platform()
    record = toolchains()['hosts'].get(host, {}).get('download')
    require(record, f'No reviewed toolchain download for {host} (docs/toolchain.md)')
    return record


def verify(directory):
    tool_paths(directory / 'bin')
    compiler_paths(directory)


def download(url, path):
    request = urllib.request.Request(url, headers={'User-Agent': 'open-xy-sdk'})
    with urllib.request.urlopen(request, timeout=120) as response, path.open('wb') as handle:
        shutil.copyfileobj(response, handle, 1 << 20)


def unpack(archive, folder, destination):
    """Extract folder/* into destination; every entry must stay inside it."""
    with zipfile.ZipFile(archive) as files:
        for info in files.infolist():
            path = PurePosixPath(info.filename)
            require(path.parts[:1] == (folder,) and '..' not in path.parts and not path.is_absolute()
                    and '\\' not in info.filename, f'Unexpected archive entry: {info.filename}')
            if info.is_dir() or len(path.parts) == 1:
                continue
            target = destination.joinpath(*path.parts[1:])
            target.parent.mkdir(parents=True, exist_ok=True)
            with files.open(info) as source, target.open('wb') as handle:
                shutil.copyfileobj(source, handle, 1 << 20)
            if (info.external_attr >> 16) & 0o111:
                target.chmod(0o755)


def fetch(record, destination, archive=None, check=verify):
    """Install record's archive at destination; returns False if already installed."""
    destination = Path(destination).resolve()
    if destination.exists():
        try:
            check(destination)
        except ValueError as error:
            raise ValueError(f'{destination} does not match the pins ({error}); remove it and fetch again') from None
        return False
    partial = destination.with_name(destination.name + '.partial')
    if partial.exists():
        shutil.rmtree(partial)  # an interrupted earlier fetch
    partial.mkdir(parents=True)
    try:
        if archive is None:
            archive = partial / 'archive.zip'
            print(f'Downloading {record["url"]}', flush=True)
            download(record['url'], archive)
        require(file_hash(Path(archive)) == record['sha256'], f'Archive hash mismatch: {archive}')
        unpack(archive, record['folder'], partial)
        if archive == partial / 'archive.zip':
            archive.unlink()
        check(partial)
        os.replace(partial, destination)
    except BaseException:
        shutil.rmtree(partial, ignore_errors=True)
        raise
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(prog='sdk.py toolchain', description=__doc__.split('\n')[0])
    parser.add_argument('action', choices=['fetch'])
    parser.add_argument('--archive', type=Path, help='an already downloaded release archive')
    parser.add_argument('--dir', type=Path, default=ROOT / TOOLCHAIN_HOME, help='install directory')
    args = parser.parse_args(argv)
    record = None
    try:
        record = release_record()
        installed = fetch(record, args.dir, args.archive)
    except (ValueError, KeyError, OSError, zipfile.BadZipFile) as error:
        print('ERROR: ' + str(error), file=sys.stderr)
        if isinstance(error, urllib.error.URLError) and record:
            print(f'Download {record["url"]} in a browser, then run:\n'
                  '  python sdk.py toolchain fetch --archive <downloaded zip>', file=sys.stderr)
            if 'CERTIFICATE_VERIFY_FAILED' in str(error) and sys.platform == 'darwin':
                print('Or install Python\'s certificates: run "Install Certificates.command" in its Applications folder.',
                      file=sys.stderr)
        return 1
    print(('Installed' if installed else 'Already installed') +
          f' the pinned Blackfin toolchain for {host_platform()} in {args.dir.resolve()}')
    return 0
