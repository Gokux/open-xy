# OP-XY SDK

Write an instrument in C++, audition it locally in a browser, and integrate it
with stock OP-XY 1.2.0. The same sound and display code compiles to WebAssembly
and Blackfin. Two examples are included: [2op FM](machines/fm2op/README.md)
and [Macro Osc](machines/macroosc/README.md), a port of Mutable Instruments Braids.
[Ring Mod](machines/ringmod/README.md) and [Timestretch](machines/timestretch/README.md)
demonstrate the experimental FX and sample interfaces.

The SDK also includes [Open-XY](docs/builder.md), its browser firmware builder.
Open-XY composes curated machines from stock or a supported Open-XY `os.ldr`,
restoring recognized selections. The stock menu JSON and SDK-owned screen template are included.
A maintainer exports one self-contained HTML;
users select machines, inspect memory use and display previews, and download a
patched bundle entirely in the browser, without a local server.

For Open-XY web development, run `npm ci` and `npm run dev`, then open
http://127.0.0.1:8918/. The [web development guide](docs/builder.md#web-development)
covers the local machine collection, hot reload, static builds and CI.

This is an unofficial, experimental SDK. Native integration patches exact stock
OS 1.2.0 with a curated collection of machines; arbitrary engine installation
and dynamic loading are not implemented. Native code is not sandboxed, and build
checks cannot guarantee recovery from a faulty image. Browser previews work on
any OS; native firmware builds need Windows x86_64 or Apple-silicon macOS, where
`python sdk.py toolchain fetch` installs the compiler ([toolchains](docs/toolchain.md)).

## Try an example

Requires Python 3.11+, Node 22+, numpy 2.3.5, Clang++ with wasm32/wasm-ld,
and a recent Chrome or Edge. Firmware and Blackfin tools are not needed.
Follow [Check your tools](docs/first-machine.md#check-your-tools) to set up an
isolated Python environment and verify WebAssembly support, then run:

```sh
python sdk.py preview --engine fm2op --out local/preview-001
python tools/serve_harness.py --preview local/preview-001
```

Open http://127.0.0.1:8917/ and click **Enable audio**. Use `--engine macroosc`
for the other example. The [preview guide](docs/preview.md) covers iteration,
patches and automation.

## Write an engine

Start with [Your first machine](docs/first-machine.md): check the prerequisites,
create a custom C++ machine, play it in the browser and make an audible edit.

A machine is a folder of source: `machine.json`, which declares its kind and
stock identity, controls in `definition.json`, and C++ for its kind: a synth's
sound (`engine.cpp`) and display (`display.cpp` and artwork), a sample engine's
`sample.cpp` or an effect's `fx.cpp`. The SDK supplies adapters, storage,
previews, firmware builds and packaging.

- [Engine API](docs/api.md): platform rules, schemas, callbacks for each kind, buffers and ownership.
- [Display API](docs/display.md): retained drawing frames and asset constraints.
- [Contributing](CONTRIBUTING.md): code ownership and checks.
- [Build your own firmware](docs/build.md): toolchain, stock files, adding a machine, build, install and release verification.

## Repository layout

| Path | Owns |
| --- | --- |
| `machines/<engine>/` | Machine source, definition, `machine.json` and artwork |
| `sdk/` | C++ interfaces, adapter templates and browser runners |
| `opxy_sdk/` | Shared build support, definitions, firmware container checks and command orchestration |
| `profiles/`, `linker/` | The firmware profile, the machine collection and the memory layout |
| `tests/` | SDK contracts and infrastructure tests |
| `tools/` | Shared development utilities and compiler tooling |
| `local/` | Ignored non-firmware development outputs and tool binaries |

`python sdk.py check` checks the SDK. A machine's sound tests belong to its
maintainer; adding an instrument does not add tests or Python modules to the SDK.

Most authored code is MIT; [Braids notices](machines/macroosc/vendor/LICENSE)
apply to that port. Timestretch, including its Capicola-derived analysis, is
AGPL-3.0; see its [source and license notices](machines/timestretch/vendor/README.md).
Shared SDK code carries no copyleft code, so the AGPL applies only to builds
that include Timestretch.
Stock firmware, stock artwork and compiler binaries are separate inputs and
are not included.
