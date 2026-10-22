# Open-XY browser builder

Open-XY builds OP-XY firmware in the browser. It runs as a website or from a
single `opxy-builder.html` file, including offline from `file://`. Firmware never
leaves the browser.

## Using the builder

1. Acknowledge the risk notice (asked again on every load).
2. Choose decrypted stock 1.2.0 `os.ldr`, or an Open-XY build to change. The
   stock file is in a device capture at `/upgrade/firmware/blackfin/bin/os.ldr`;
   a previously installed Open-XY build is at `/os.ldr`. A guide walks through
   enabling the dev menu and capturing the file if you don't have it.
3. Select machines. Synth rows have a playable preview of their C++ sound and
   display code; each row shows its code, data and state size against the
   memory meter.
4. Download the ZIP and follow the installation guide for Windows or Mac.

The ZIP contains:

| File | Install |
| --- | --- |
| `os.ldr` | Device root, replacing the existing file |
| `content/op1_factory.json` | Replaces the menu file |
| `content/display/*.svg` | New screens for the selected machines; keep the stock files |
| `content/presets/<machine>/default.json` | One init preset in each selected instrument's own folder |
| `layout.json`, hashes | Optional; for your records |

Every build shows `OPEN 0.0.1-1.2.0` at boot. Timestretch starts without a sample;
choose one on its sample page. Decimate is a send effect and has no preset.

The builder accepts only the exact stock file or an exact Open-XY output of the
same collection. Encrypted `.tfw`, unknown patches and damaged files are
rejected. Opening an Open-XY build restores its machine selection by rebuilding
the stock image from it; projects, presets and samples on the device are not
touched.

### Dev menu

The MIDI helper, adapted from [Ferret](https://github.com/bagofwaffles/ferret)
(MIT, Bag of Waffles; see `builder/ferret.mjs` and `builder/ferret.LICENSE`),
enables or disables the dev menu after an explicit click and browser MIDI
permission. It sets or removes only the `bootloader.dev` flag; it never
transfers firmware. Refresh the menu with track 8 twice to see the result. MIDI
needs a desktop browser and a secure context; otherwise the helper links to
hosted Ferret. Installing firmware is a manual file copy.

## Capacity and identity

The firmware reserves **512 KiB** of the application heap: 508 KiB that every
selected machine shares for code, data and state, and 4 KiB for relocated stock
tables. The memory meter shows each machine's share; see
[memory and limits](api.md#memory-and-limits). CPU headroom is not measured.

Each machine has a fixed engine and page ID across the whole collection, so a
project never changes instruments when the selection changes: 2op 34/82,
Macro Osc 26/83, Timestretch 35/7, Decimate effect 11/page 21. Adding a machine to
the collection means adding it to the native build; the builder is not a
plugin loader and does not raise the voice limit.

## Web development

The app is in `builder/`. Use Node 22.12+:

```sh
npm ci
npm run dev        # http://127.0.0.1:8918/
npm run test:web
```

The dev server serves only the browser source allowlist and the configured
collection; do not replace it with a server rooted at the repository. Previews
and bundles need a collection: point the ignored `.env.local` at a verified
export from [Maintainer export](#maintainer-export):

```dotenv
OPEN_XY_KIT=C:/Users/YOUR_USER/AppData/Local/OPXY-SDK/private/builds/browser-kit-001/opxy-builder.html
OPEN_XY_OUT_DIR=C:/Users/YOUR_USER/AppData/Local/OPXY-SDK/private/sites/browser-kit-001
```

`OPEN_XY_KIT` may also name an exported `kit.json`. Collections contain stock
menu content, so they and site output must live outside every checkout; the
server and build reject checkout-local paths, including through symlinks,
junctions and other worktrees. UI changes need no native rebuild; machine source
changes need a new export.

`npm run build:release` writes the site to `OPEN_XY_OUT_DIR` (or `--outDir`),
which must be a fresh directory; `npm run preview` serves it at
http://127.0.0.1:8919/. Asset URLs are relative, so the site can be hosted at a
domain root or a subpath; serve it over HTTPS for MIDI. CI runs `npm run build`
with no collection as a UI check and never consumes private inputs.

### Cloudflare deployment

`wrangler.jsonc` names the site `open-xy` and binds `open-xy.com`. The site is
static assets only, with no Worker script. With `.env.local` set as above:

```sh
npx wrangler login
npm run test:web
npm run deploy:cloudflare
```

The deploy rebuilds in release mode, fails without a valid collection, and
uploads only the release directory. To add a custom domain, make its parent an
active Cloudflare zone, then use **Workers & Pages → open-xy → Settings →
Domains & Routes → Add → Custom Domain**; see the
[custom-domain guide](https://developers.cloudflare.com/workers/configuration/routing/custom-domains/).

## Maintainer export

With the [pinned native tools](build.md) and Clang++ for wasm32:

```powershell
python sdk.py kit --toolchain local/toolchain/bin --compiler local/toolchain-gcc --preview-cxx clang++ --stock-os "$env:LOCALAPPDATA/OPXY-SDK/private/stock-1.2.0/os.ldr" --stock-content "$env:LOCALAPPDATA/OPXY-SDK/private/stock-1.2.0/content" --out "$env:LOCALAPPDATA/OPXY-SDK/private/builds/browser-kit-001"
```

The stock content directory needs only `op1_factory.json`. The export runs the
full native build and its checks, then packages the native objects in link
order with each machine's `machine.json` and definition. The HTML carries the
authenticated stock menu and the SDK screen template; firmware stays
user-supplied. It is named only after every check passes.

The browser links the normalized ELF32 Blackfin objects itself, supporting the
LUIMM16, HUIMM16, PCREL24, PCREL24_JUMP_L and BYTE4 relocations. Unsupported
sections, COMMON or weak symbols, unresolved imports, overlapping relocations,
range overflow, constructors and memory overflow are errors. A deselected
machine's startup callbacks resolve to fallback stubs that skip it; its audio
code and state are omitted.

The export checks, normally and under `python -O`, that:

- selecting every machine reproduces the native `os.ldr` byte for byte;
- every non-empty selection matches GNU ld, including symbols and BSS;
- browser output matches the Python writer, with correct catalog, artwork and ZIP;
- every output is recognized and its selection restored, and corruption inside
  or outside the allowed edits is rejected.

Restoring a build removes the appended module record, restores the profile's
edit intervals and FIRST record, checks the stock SHA-256, and accepts the file
only if relinking its selection reproduces it exactly. Uploaded code is never
executed or reused, so only outputs of the same kit are recognized.
