"""Shared local build utilities and stock firmware compatibility boundary."""
import argparse
import json
from pathlib import Path
import platform
import subprocess
import sys
import xml.etree.ElementTree as ET

from .formats import elf32, header, ldr, mapped_offset, require, sha

ROOT = Path(__file__).resolve().parents[1]
MAX_FILE = 16 * 1024 * 1024
TOOLCHAINS = 'profiles/toolchains.json'
TOOLCHAINS_SHA256 = '570f5e9826a78b83de33b55303985c5e53377f45b735be54749321202dc9ccd5'
# Additional exclusions, not a complete map of critical code. The exact source,
# module and whole-output pins remain the stronger reference boundary.
PROTECTED = (
    (0x11a00000, 0x11a0c000),  # Startup/entry payload
    (0x8c040ad4, 0x8c0d0d5c),  # OS block containing storage/partition/reboot code
    (0x8d516fa4, 0x8d517174),  # Simple factory/callbacks
    (0x8d504b74, 0x8d504bd0),  # Shared default voice callbacks
    (0x8d506246, 0x8d50626c),  # Simple registration
    (0x8404d2dc, 0x8404d308),  # Simple method table
    (0x84044afc, 0x84044b00),  # Stock amplitude constant
    (0x84045094, 0x8404509c),  # Simple name
    (0x840452f0, 0x84045310),  # Simple label pointers
    (0x84044c74, 0x84044c7c),  # Stock shape label
)


def check_patch_boundaries(profile, count=7):
    occupied = set()
    require(len(profile['patches']) == count, f'Expected {count} reviewed edit intervals')
    for patch in profile['patches']:
        start = int(patch['address'], 16)
        before, after = bytes.fromhex(patch['before']), bytes.fromhex(patch['after'])
        end = start + len(before)
        require(before and len(before) == len(after) and before != after and
                0 <= start < end <= 0x100000000, 'Invalid instruction edit')
        # Only the separately reviewed startup text-call boundary may intersect
        # this broad OS exclusion. Storage/entry routines remain protected.
        from .startup_label import allowed as startup_label_allowed
        from .sample_hooks import allowed as sample_hook_allowed
        require(not any(start < hi and lo < end for lo, hi in PROTECTED) or
                startup_label_allowed(profile, patch) or sample_hook_allowed(profile, patch), 'Protected code/data edit')
        positions = set(range(start, end))
        require(not occupied.intersection(positions), 'Overlapping instruction edits')
        occupied.update(positions)


def read(path):
    path = Path(path)
    require(path.is_file() and path.stat().st_size <= MAX_FILE, f'Missing/oversized input: {path}')
    return path.read_bytes()


def document(path):
    return json.loads(read(path))


def save_json(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def child(root, relative):
    require(isinstance(relative, str) and relative and '\\' not in relative and ':' not in relative,
            'Expected relative POSIX path')
    require(not relative.startswith('/') and all(p not in ('', '.', '..') for p in relative.split('/')),
            'Unsafe relative path')
    path = (root / relative).resolve()
    require(path.is_relative_to(root.resolve()), 'Path escapes its root')
    return path


def config():
    """The firmware profile: stock 1.2.0 hashes, the reservation and every edit."""
    profile = document(ROOT / 'profiles/opxy-1.2.0.json')
    require(profile['schema'] == 1 and profile['id'] == 'opxy-1.2.0', 'Incompatible profile')
    check_patch_boundaries(profile, len(profile['patches']))
    return profile


def host_platform():
    """Pin key of the running host, such as windows-x86_64 or darwin-arm64."""
    system, machine = platform.system().lower(), platform.machine().lower()
    if system.startswith(('msys_nt', 'cygwin', 'mingw')):
        system = 'windows'  # MSYS2/Cygwin Python runs the same Windows executables
    return system + '-' + {'amd64': 'x86_64', 'aarch64': 'arm64'}.get(machine, machine)


def check_toolchains(pins):
    require(pins['schema'] == 1, 'Incompatible toolchain pins')
    require(all('executable_suffix' in host for host in pins['hosts'].values()), 'Missing executable suffix')
    release = pins['hosts'].get(pins['release'], {})
    require('tools' in release and 'compiler' in release, 'The release host needs pinned tools and compiler')
    return pins


def toolchains():
    """Reviewed tool pins of every host; the release host builds published packages and kits."""
    data = read(ROOT / TOOLCHAINS)
    require(sha(data) == TOOLCHAINS_SHA256, 'Reviewed toolchain pins changed')
    return check_toolchains(json.loads(data))


def require_release_host():
    """Only the release host reproduces the reference module bytes (docs/toolchain.md)."""
    release = toolchains()['release']
    require(host_platform() == release,
            f'Release packages and browser kits are built and verified on {release}, not {host_platform()}')


def host_pins(kind):
    """Reviewed file hashes of this host's 'tools' or 'compiler', and its executable suffix."""
    host = toolchains()['hosts'].get(host_platform(), {})
    require(kind in host, f'No reviewed Blackfin {kind} for {host_platform()} (docs/toolchain.md)')
    return host[kind], host['executable_suffix']


def tool_paths(directory):
    directory = Path(directory).resolve()
    pins, suffix = host_pins('tools')
    result = {}
    for name, expected in pins.items():
        path = directory / ('bfin-elf-' + name + suffix)
        require(sha(read(path)) == expected, f'Tool hash mismatch: {path}')
        result[name] = path
    return result


def execute(args):
    return subprocess.check_output([str(a) for a in args], stderr=subprocess.STDOUT, text=True, timeout=120)


def fresh_output(path):
    path = Path(path).resolve()
    require(not path.exists(), f'Output already exists; choose a new directory: {path}')
    path.mkdir(parents=True)
    return path
