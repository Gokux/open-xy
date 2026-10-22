# Native builds and verification

Native integration is a maintainer task. `sdk.py build` statically links every
machine in the curated collection into exact stock 1.2.0, using the
[firmware ABI](abi-1.2.0.md). External-engine discovery and arbitrary ID
assignment are not implemented.

For browser-only selection and download of curated modules, see the
[machine builder](builder.md). Its exporter runs these native checks before
validating the browser linker and packager.

## Inputs

Use the pinned [toolchains](toolchain.md), decrypted stock `os.ldr` and stock
content. An encrypted `.tfw` is not interchangeable. Keep private inputs and
firmware outputs outside every checkout, such as `%LOCALAPPDATA%/OPXY-SDK/private/`.
Tools and source-image hashes are checked before use. Every build uses a fresh
output directory. Commands below perform no device operations.

## Build

```powershell
$private = "$env:LOCALAPPDATA/OPXY-SDK/private"
python sdk.py build --toolchain local/toolchain/bin --compiler local/toolchain-gcc --stock-os "$private/stock-1.2.0/os.ldr" --stock-content "$private/stock-1.2.0/content" --out "$private/builds/collection-001"
python sdk.py check --native-package "$private/builds/collection-001" --toolchain local/toolchain/bin --compiler local/toolchain-gcc --host-cxx g++ --stock-os "$private/stock-1.2.0/os.ldr" --stock-content "$private/stock-1.2.0/content"
```

The collection is the ordered machine list in `profiles/collection.json`; each
machine's `machine.json` declares its kind, identity and any extra C++ sources,
and `definition.json` its controls, resources and display. The build uses the
512 KiB reservation with [relocated engine and screen tables](abi-1.2.0.md#identities).
`sdk.py compile` builds the module alone and needs no stock firmware;
`sdk.py verify --package` rebuilds and compares an existing package.

## What verification establishes

| Check | Responsibility |
| --- | --- |
| Stock/tool hashes, exact edit intervals, entry/loader preservation, protected ranges | Shared platform/packager |
| Linked memory bounds, relocations, audio-callback recursion and stack depth, and complete output reconstruction | Shared infrastructure; the selected machines share one module limit |
| Callback layout, registration/name ownership, artwork format | SDK adapters and integration checks |
| Audio arithmetic, sound references, animation sequences and port fidelity | Selected engine's checks |

Native verification independently rebuilds the package and runs required private
fixtures under normal Python and `python -O`; missing inputs or skipped required
tests fail. A changed source requires a new package, not a manually changed
manifest. Public `check` ignores inherited private-fixture variables.
The native sample-service fixtures require a host C++11 compiler (`--host-cxx`,
default `g++`) on PATH, including its runtime DLLs when applicable.

Host checks do not model device scheduling, interrupts, caches, stock graphics
or recovery, and do not guarantee a recoverable device.

## Package files

| File under `candidate/` | Device path |
| --- | --- |
| `os.ldr` | `/os.ldr` |
| `content/op1_factory.json` | `/content/op1_factory.json` |
| `content/display/<machine>.svg`, one per synth | `/content/display/<machine>.svg` |

The dev-menu firmware writer reads `/os.ldr`, not the upgrade directory.
`module.elf` and `module.bin` are development artifacts, not installable images.
Installing a candidate is a separate device action; these commands only build
and verify local files.
