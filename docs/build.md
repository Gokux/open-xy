# Build your own firmware

`sdk.py build` statically links every machine in the collection into exact
stock OS 1.2.0, using the [firmware ABI](abi-1.2.0.md), and checks the result.
It runs on Windows x86_64 and Apple-silicon macOS. To choose among the curated
machines without building, use the [browser builder](builder.md) instead.
External-engine discovery and dynamic loading are not implemented: a machine
reaches the firmware by joining the collection.

This firmware is unofficial and experimental. Native code is not sandboxed,
and host checks cannot guarantee a recoverable device.

## 1. Install the tools

Python 3.11+ and the pinned [toolchain](toolchain.md):

```sh
python sdk.py toolchain fetch
```

It installs the compiler in `local/toolchain`, which every native command uses
when `--toolchain` and `--compiler` are omitted.

## 2. Copy the stock files

From an OP-XY running OS 1.2.0, with the dev menu enabled (the
[builder's guide](builder.md#dev-menu) shows how), copy:

| Device path | Use as |
| --- | --- |
| `/upgrade/firmware/blackfin/bin/os.ldr` | `--stock-os` |
| `/content/op1_factory.json` | `op1_factory.json` in the `--stock-content` folder |

Keep them outside every checkout, for example in
`%LOCALAPPDATA%/OPXY-SDK/private/stock-1.2.0/` on Windows or
`~/Library/Application Support/OPXY-SDK/private/stock-1.2.0/` on macOS. The
build accepts only the exact stock files: an encrypted `.tfw` is a different
format, and an installed Open-XY build replaces `/content/op1_factory.json`.

## 3. Add your machine

Start from [your first machine](first-machine.md). To build it for the device:

1. Move its folder to `machines/<id>/` and rename its artwork IDs from
   `local_` to `<id>_`.
2. Add a [`machine.json`](api.md#registration-boundary) with a free
   [identity](api.md#identity). Names and IDs are saved in presets and
   projects, so they never change once published.
3. Add `<id>` to `profiles/collection.json`. Remove machines you don't want;
   all selected machines share 508 KiB ([memory and limits](api.md#memory-and-limits)).

## 4. Build

```sh
python sdk.py build --stock-os <stock>/os.ldr --stock-content <stock> --out <builds>/mine-001
```

Use a new `--out` folder for every build, also outside the checkout. The build
prints each machine's memory use and fails on any check below.
`python sdk.py compile --out <folder>` builds the module alone, without stock
files, for a quicker compile check.

## 5. Install

| File under `candidate/` | Device path |
| --- | --- |
| `os.ldr` | `/os.ldr` |
| `content/op1_factory.json` | `/content/op1_factory.json` |
| `content/display/<machine>.svg`, one per synth | `/content/display/<machine>.svg` |

Copy the files to the device as the builder's installation guide describes;
the dev menu's firmware writer reads `/os.ldr`, not the upgrade directory.
`module.elf` and `module.bin` are development artifacts, not installable
images. The SDK's commands never write to a device.

## What a build checks

| Check | Responsibility |
| --- | --- |
| Stock/tool hashes, exact edit intervals, entry/loader preservation, protected ranges | Shared platform/packager |
| Linked memory bounds, relocations, audio-callback recursion and stack depth, and complete output reconstruction | Shared infrastructure; the selected machines share one module limit |
| Callback layout, registration/name ownership, artwork format | SDK adapters and integration checks |
| Audio arithmetic, sound references, animation sequences and port fidelity | Selected engine's checks |

Host checks do not model device scheduling, interrupts, caches, stock graphics
or recovery, and do not guarantee a recoverable device.

## Release verification

Published packages and browser kits come from the release host named in
[`profiles/toolchains.json`](../profiles/toolchains.json), whose compiler
reproduces the reference bytes ([hosts](toolchain.md#hosts)). There, the
maintainer runs:

```sh
python sdk.py check --native-package <builds>/mine-001 --stock-os <stock>/os.ldr --stock-content <stock>
```

It independently rebuilds the package (`sdk.py verify`) and runs the fixture
tests that need the package and stock files, under normal Python and
`python -O`; missing inputs or skipped tests fail. The sample-service fixtures
need a host C++11 compiler (`--host-cxx`, default `g++`) on PATH. A changed
source requires a new package, not a manually changed manifest. Public `check`
ignores inherited fixture variables. A personal build doesn't need this step.
