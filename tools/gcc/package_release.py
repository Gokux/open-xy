"""Package the reviewed Blackfin toolchain as release assets.

    python tools/gcc/package_release.py --compiler <bundle> --fork <checkout> --sources <dir> --out <new dir>

<bundle> is the hash-checked --compiler bundle, which also carries the pinned
binutils in bin/. <checkout> is deanm1278/blackfin-plus-gnu at the commit in
release-sources.json. <sources> holds that file's runtime source packages.

The binary zip contains exactly this host's pinned files from
profiles/toolchains.json, the runtime libraries those executables import from
their own directories, the license texts and SOURCES.md. The source tar
contains the fork at its pinned commit, tools/gcc (patches and build scripts)
and the source package of every bundled runtime library. Both are
byte-reproducible from the same inputs.
"""
import argparse
import gzip
import io
import json
from pathlib import Path, PurePosixPath
import shutil
import struct
import subprocess
import sys
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from opxy_sdk.formats import require  # noqa: E402
from opxy_sdk.native import file_hash  # noqa: E402
from opxy_sdk.pipeline import child, host_platform, toolchains  # noqa: E402

MANIFEST = Path(__file__).with_name('release-sources.json')
# Imports satisfied by every supported Windows installation.
WINDOWS_SYSTEM = {'advapi32.dll', 'kernel32.dll', 'msvcrt.dll', 'user32.dll'}
MACOS_SYSTEM = ('/usr/lib/', '/System/Library/')
MACHO_64 = b'\xcf\xfa\xed\xfe'
MACHO_LOADS = {0xc, 0x80000018, 0x8000001f}  # LC_LOAD_DYLIB, LC_LOAD_WEAK_DYLIB, LC_REEXPORT_DYLIB
ZIP_DATE = (1980, 1, 1, 0, 0, 0)


def pe_imports(data):
    """DLL names in a PE32/PE32+ import table."""
    require(data[:2] == b'MZ', 'Not a PE executable')
    pe = struct.unpack_from('<I', data, 0x3c)[0]
    require(data[pe:pe + 4] == b'PE\0\0', 'Not a PE executable')
    sections, optional_size = struct.unpack_from('<H12xH', data, pe + 6)
    optional = pe + 24
    magic = struct.unpack_from('<H', data, optional)[0]
    directories = optional + {0x10b: 96, 0x20b: 112}[magic]
    import_rva = struct.unpack_from('<I', data, directories + 8)[0]
    table = optional + optional_size
    spans = [struct.unpack_from('<8xIIII', data, table + 40 * i) for i in range(sections)]

    def offset(rva):
        for size, address, raw_size, raw in spans:
            if address <= rva < address + max(size, raw_size):
                return raw + rva - address
        raise ValueError(f'RVA {rva:#x} outside every section')

    names, at = [], offset(import_rva) if import_rva else None
    while at is not None:
        name_rva = struct.unpack_from('<12xI', data, at)[0]
        if not name_rva:
            break
        start = offset(name_rva)
        names.append(data[start:data.index(b'\0', start)].decode('ascii'))
        at += 20
    return names


def macho_imports(data):
    """Install names of the libraries a 64-bit Mach-O image loads."""
    require(data[:4] == MACHO_64, 'Not a 64-bit Mach-O image')
    names, at = [], 32
    for _ in range(struct.unpack_from('<I', data, 16)[0]):
        command, size = struct.unpack_from('<II', data, at)
        if command in MACHO_LOADS:
            start = at + struct.unpack_from('<I', data, at + 8)[0]
            names.append(data[start:data.index(b'\0', start)].decode('utf-8'))
        at += size
    return names


def is_image(path):
    with path.open('rb') as handle:
        magic = handle.read(4)
    return magic[:2] == b'MZ' or magic == MACHO_64


def runtime_closure(root, executables, host):
    """Libraries the executables load from their own directories, recursively."""
    if host.startswith('darwin-'):
        # The macOS build links gmp, mpfr and mpc statically; only system libraries remain.
        for path in executables:
            for name in macho_imports(path.read_bytes()):
                require(name.startswith(MACOS_SYSTEM), f'{path.name} loads {name} from outside macOS')
        return {}
    require(host.startswith('windows-'), f'Runtime discovery for {host} is not implemented')
    found, pending = {}, list(executables)
    while pending:
        path = pending.pop()
        for name in pe_imports(path.read_bytes()):
            local = {p.name.lower(): p for p in path.parent.glob('*.dll')}.get(name.lower())
            if local is None:
                require(name.lower() in WINDOWS_SYSTEM, f'{path.name} imports {name} from outside the bundle')
                continue
            relative = local.relative_to(root).as_posix()
            if relative not in found:
                found[relative] = local
                pending.append(local)
    return found


def bundle_files(compiler, host, pins):
    """Pinned files plus runtime closure, hash-checked; {relative path: Path}."""
    files = {}
    for relative, expected in pins['compiler'].items():
        path = child(compiler, relative)
        require(path.is_file() and file_hash(path) == expected, f'Compiler file hash mismatch: {relative}')
        files[relative] = path
    for name, expected in pins['tools'].items():
        relative = f'bin/bfin-elf-{name}{pins["executable_suffix"]}'
        path = child(compiler, relative)
        require(path.is_file() and file_hash(path) == expected, f'Tool hash mismatch: {relative}')
        files[relative] = path
    executables = [path for path in files.values() if is_image(path)]
    for relative, path in runtime_closure(compiler, executables, host).items():
        files.setdefault(relative, path)
    return files


def library_sources(manifest, host, files, sources):
    """Every bundled third-party library maps to a hash-checked source package."""
    packages = manifest['hosts'][host]['runtime']
    provided = {name: package for package in packages for name in package['provides']}
    for relative in files:
        if relative.endswith('.dll'):
            require(PurePosixPath(relative).name in provided, f'No source package for {relative}')
    result = []
    for package in packages:
        path = child(sources, package['file'])
        require(path.is_file() and file_hash(path) == package['sha256'], f'Source package hash mismatch: {package["file"]}')
        result.append((package, path))
    return result


def git(fork, *args):
    return subprocess.check_output(['git', '-C', str(fork), *args])


def check_fork(manifest, fork):
    commit = manifest['fork']['commit']
    head = git(fork, 'rev-parse', 'HEAD').decode().strip()
    require(head == commit, f'Fork checkout is at {head}, not {commit}')
    return commit


def write_fork_archive(fork, commit, path):
    """git archive of the commit, gzip-compressed without a timestamp."""
    with subprocess.Popen(['git', '-C', str(fork), 'archive', '--format=tar', '--prefix=blackfin-plus-gnu/', commit],
                          stdout=subprocess.PIPE) as process, path.open('wb') as raw,             gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0) as compressed:
        shutil.copyfileobj(process.stdout, compressed, 1 << 20)
    require(process.returncode == 0, 'git archive failed')


def licenses(manifest, host, fork, commit):
    texts = {target: git(fork, 'show', f'{commit}:{source}') for target, source in manifest['fork']['licenses'].items()}
    for name in manifest['hosts'][host]['notices']:
        texts[name] = (Path(__file__).parent / 'licenses' / name).read_bytes()
    return texts


def sources_text(manifest, host, packages, source_name):
    fork = manifest['fork']
    lines = [
        '# Open-XY Blackfin toolchain', '',
        f'Host: {host}. Built by {manifest["hosts"][host]["build"]} from the Open-XY repository.', '',
        'Every file in this archive is free software. The corresponding source is the',
        f'release asset `{source_name}`, published alongside this archive. It contains:', '',
        f'- `blackfin-plus-gnu.tar.gz`: {fork["url"]} at `{fork["commit"]}` (GCC and binutils,',
        '  GPL-3.0-or-later; libgcc with the GCC Runtime Library Exception)',
        '- `tools/gcc/`: the Open-XY patches applied to it and the build scripts',
    ]
    for package, _ in packages:
        lines.append(f'- `{package["file"]}`: {", ".join(package["provides"])} '
                     f'({package["license"]}; {package["url"]})')
    lines += ['', 'License texts are in `licenses/`.', '']
    return '\n'.join(lines).encode('utf-8')


def write_zip(path, prefix, entries):
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in sorted(entries):
            data, executable = entries[name]
            info = zipfile.ZipInfo(f'{prefix}/{name}', ZIP_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o100755 if executable else 0o100644) << 16
            archive.writestr(info, data)


def write_tar(path, entries):
    """entries: {name: bytes or Path}, stored with fixed metadata."""
    with tarfile.open(path, 'w', format=tarfile.PAX_FORMAT) as archive:
        for name in sorted(entries):
            value = entries[name]
            info = tarfile.TarInfo(name)
            info.size = value.stat().st_size if isinstance(value, Path) else len(value)
            info.mode, info.mtime = 0o644, 0
            with (value.open('rb') if isinstance(value, Path) else io.BytesIO(value)) as handle:
                archive.addfile(info, handle)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--compiler', type=Path, required=True)
    parser.add_argument('--fork', type=Path, required=True)
    parser.add_argument('--sources', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--host', default=host_platform())
    args = parser.parse_args(argv)
    require(not args.out.exists(), f'Output already exists; choose a new directory: {args.out}')
    manifest = json.loads(MANIFEST.read_text('utf-8'))
    host = args.host
    pins = toolchains()['hosts'].get(host, {})
    require('tools' in pins and 'compiler' in pins, f'No reviewed toolchain for {host}')
    compiler = args.compiler.resolve()
    files = bundle_files(compiler, host, pins)
    packages = library_sources(manifest, host, files, args.sources.resolve())
    commit = check_fork(manifest, args.fork)

    name = f'open-xy-toolchain-{host}'
    source_name = f'open-xy-toolchain-source-{host}.tar'
    entries = {relative: (path.read_bytes(), is_image(path)) for relative, path in files.items()}
    entries.update({f'licenses/{target}': (data, False)
                    for target, data in licenses(manifest, host, args.fork, commit).items()})
    entries['SOURCES.md'] = (sources_text(manifest, host, packages, source_name), False)

    tracked = subprocess.check_output(['git', '-C', str(ROOT), 'ls-files', '-z', 'tools/gcc'], text=True).split('\0')
    args.out.mkdir(parents=True)
    fork_archive = args.out / 'blackfin-plus-gnu.tar.gz.partial'
    write_fork_archive(args.fork, commit, fork_archive)
    source = {'blackfin-plus-gnu.tar.gz': fork_archive}
    source.update({name: (ROOT / name).read_bytes() for name in tracked if name})
    source.update({f'runtime/{package["file"]}': path for package, path in packages})

    write_zip(args.out / (name + '.zip'), name, entries)
    write_tar(args.out / source_name, source)
    fork_archive.unlink()
    sums = ''.join(f'{file_hash(args.out / asset)}  {asset}\n' for asset in (name + '.zip', source_name))
    (args.out / 'SHA256SUMS').write_text(sums, 'utf-8', newline='\n')
    print(sums, end='')
    print(f'{len(entries)} files in {name}.zip; {len(source)} entries in {source_name}')


if __name__ == '__main__':
    main()
