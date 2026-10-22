# Toolchains

| Task | Needs | Platforms |
| --- | --- | --- |
| Browser preview (`sdk.py preview`, `new`) | Python 3.11+, NumPy, Node 22+, Clang with the wasm32 target | Any |
| SDK checks (`sdk.py check`) | Python 3.11+, Node 22+ | Any |
| Native firmware (`sdk.py compile`, `build`) | The pinned Blackfin+ binutils and GCC 8 bundle below | Pinned hosts below |
| Release browser kit (`sdk.py kit`) | The same, on the release host | Windows x86_64 |

`python sdk.py doctor --preview` checks the preview tools, and
`python sdk.py doctor --toolchain <dir>` checks the native binutils.

## Native tools

The OP-XY CPU is a Blackfin+ (BF707). The native tools come from the
Blackfin+ GNU fork <https://github.com/deanm1278/blackfin-plus-gnu> at commit
`e4408a15b9be6cd911283f103a1a3f69e9a6b8c0`.

| Argument | Contents | Pinned in |
| --- | --- | --- |
| `--toolchain` | `bfin-elf-as`, `-ld`, `-objcopy`, `-objdump` | `tools` of the host in [`profiles/toolchains.json`](../profiles/toolchains.json) |
| `--compiler` | GCC 8 C++ for every machine | `compiler` of the host in the same file |

The fork's GCC needs one code-generation fix for correct output.
[`0001-bfin-loop-end-clobbers-cc.patch`](../tools/gcc/patches/0001-bfin-loop-end-clobbers-cc.patch)
marks the condition flag as clobbered when a hardware loop falls back to a
decrement-and-branch. Without it, GCC can keep a live comparison across that
branch and miscompile the code.
[`tools/gcc/build-gcc.sh`](../tools/gcc/build-gcc.sh) builds the `--compiler`
bundle with that fix under MSYS2 MinGW64.
The `0002` patch only lets the compiler itself build on a Windows host.
[`tools/gcc/build-macos.sh`](../tools/gcc/build-macos.sh) builds both on macOS
with the host fixes in `tools/gcc/patches/macos`: the bundled zlib on current
SDKs, Apple silicon host hooks, and a disassembler sign extension that assumed
a 32-bit `long`.

## Hosts

| Host | Compiler built by | Output |
| --- | --- | --- |
| `windows-x86_64` (release) | `build-gcc.sh` | Reference module bytes |
| `darwin-arm64` | `build-macos.sh` | Valid module; not byte-identical to the reference |

GCC 8 sorts with the host C library's `qsort`, which orders equal elements
differently on each host, so some units get a different but equally valid
instruction order. The binutils produce identical bytes on both hosts.
Published browser kits therefore come only from the release host named in
[`profiles/toolchains.json`](../profiles/toolchains.json); `sdk.py kit` refuses
on any other host.

Every tool file is hash-checked before it runs. Source and install paths are
compiled into the tools, so a rebuild matches its pins only at the same paths.
A host's `build` record in `profiles/toolchains.json` names the script, source
and output paths and host tools its pins were built with; `build-macos.sh`
refuses other Homebrew versions. A rebuilt tool gets a new reviewed entry and
a new `TOOLCHAINS_SHA256`; never relax a hash to admit it.

## Known gaps

- Linux has no pins.
- The tools are not distributed with the SDK. Distributing GNU binaries
  carries their license and corresponding-source obligations.
