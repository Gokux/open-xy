#!/usr/bin/env bash
# Build the Blackfin GCC bundle passed to `sdk.py build --compiler` (MSYS2 MINGW64 shell).
#
#   tools/gcc/build-gcc.sh <fork-checkout> <binutils-bin> <output-bundle>
#
# <fork-checkout>  deanm1278/blackfin-plus-gnu at e4408a15b9be6cd911283f103a1a3f69e9a6b8c0
#                  (only its gcc/ and binutils-gdb/ trees are used)
# <binutils-bin>   the pinned bfin-elf-{as,ld,objcopy,objdump}.exe plus ar/ranlib/nm
#                  from the same binutils build (docs/toolchain.md)
# <output-bundle>  new directory; becomes the --compiler argument
#
# Applies tools/gcc/patches (GCC codegen fix, MinGW host fix), builds C/C++
# cc1plus + libgcc (no libc) and bundles the MSYS2 runtime DLLs next to the
# executables. Host compilers, paths and
# timestamps change executable hashes: a rebuilt bundle needs its own review
# and a new entry in profiles/toolchains.json, never a relaxed check.
set -euo pipefail
src=$(cd "$1" && pwd); binutils=$(cd "$2" && pwd); out=$3
repo=$(cd "$(dirname "$0")/../.." && pwd)
[ ! -e "$out" ] || { echo "output must not exist: $out" >&2; exit 1; }
mkdir -p "$out"; out=$(cd "$out" && pwd)
work=$(mktemp -d)
export PATH="/mingw64/bin:/usr/bin"

for patch in "$repo"/tools/gcc/patches/*.patch; do
  git -C "$src" apply --ignore-whitespace "$patch"  # paths relative to the fork root
done

mkdir -p "$out/bin" "$out/bfin-elf/bin"
for t in as ld objcopy objdump ar ranlib nm; do
  cp "$binutils/bfin-elf-$t.exe" "$out/bin/"
  cp "$binutils/bfin-elf-$t.exe" "$out/bfin-elf/bin/$t.exe"
done
export PATH="$out/bin:$PATH"

mkdir "$work/gcc" && cd "$work/gcc"
"$src/gcc/configure" \
  --build=x86_64-w64-mingw32 --host=x86_64-w64-mingw32 --target=bfin-elf \
  --prefix="$out" --enable-languages=c,c++ \
  --without-headers --with-newlib --disable-shared --disable-threads \
  --disable-libssp --disable-libquadmath --disable-libgomp --disable-libatomic \
  --disable-nls --disable-werror --disable-multilib --disable-lto --without-isl \
  --disable-plugin --disable-bootstrap \
  --with-gmp=/mingw64 --with-mpfr=/mingw64 --with-mpc=/mingw64 \
  CC=gcc CXX=g++ CFLAGS="-O2 -std=gnu11" \
  CXXFLAGS="-O2 -std=gnu++14 -fpermissive -Wno-narrowing" MAKEINFO=true
make -j"$(nproc)" all-gcc MAKEINFO=true || {
  # Patch 0001 changes target hooks documentation; accept the regenerated copy.
  cp gcc/tm.texi "$src/gcc/gcc/doc/tm.texi"
  make -j"$(nproc)" all-gcc MAKEINFO=true
}
make install-gcc MAKEINFO=true
make -j"$(nproc)" all-target-libgcc MAKEINFO=true
make install-target-libgcc MAKEINFO=true

for dir in "$out/bin" "$out/libexec/gcc/bfin-elf/8.0.0"; do
  for dll in libgcc_s_seh-1.dll libgmp-10.dll libiconv-2.dll libmpc-3.dll \
             libmpfr-6.dll libwinpthread-1.dll zlib1.dll; do
    cp "/mingw64/bin/$dll" "$dir/"
  done
done

rm -rf "$work"
echo "Bundle: $out (record reviewed hashes in profiles/toolchains.json before use)"
