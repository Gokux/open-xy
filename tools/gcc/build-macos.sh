#!/usr/bin/env bash
# Build the Blackfin binutils and GCC bundle on macOS (Apple silicon, Xcode clang).
#
#   tools/gcc/build-macos.sh <fork-checkout> <output>
#
# <fork-checkout>  deanm1278/blackfin-plus-gnu at e4408a15b9be6cd911283f103a1a3f69e9a6b8c0
#                  (only its gcc/ and binutils-gdb/ trees are used)
# <output>         new directory: `--toolchain <output>/bin`, `--compiler <output>`
#
# Needs the Homebrew versions below (gmp, mpfr and libmpc are linked statically).
# Applies the GCC codegen fix (patches/0001) and the macOS host fixes in
# patches/macos. Source and install paths are compiled into the tools, so
# their hashes match a profile record only when rebuilt from the same
# <fork-checkout> path into the same <output> path. The build directory is
# <output>.build and host objects carry no debug map, so such a rebuild
# reproduces the same files.
set -euo pipefail
src=$(cd "$1" && pwd); out=$2
repo=$(cd "$(dirname "$0")/../.." && pwd)
[ ! -e "$out" ] || { echo "output must not exist: $out" >&2; exit 1; }
brew=$(brew --prefix)
for pinned in 'gmp 6.3.0' 'mpfr 4.2.2' 'libmpc 1.3.1' 'bison 3.8.2'; do
  [ "$(brew list --versions "${pinned%% *}")" = "$pinned" ] ||
    { echo "Homebrew ${pinned%% *} must be ${pinned#* } (the pinned build)" >&2; exit 1; }
done
clang --version | head -n 1
mkdir -p "$out"; out=$(cd "$out" && pwd)
work=$out.build; rm -rf "$work"; mkdir "$work"  # this script's own build directory
export PATH="$brew/opt/bison/bin:$out/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export ZERO_AR_DATE=1  # archive member times feed cc1plus's embedded checksum
jobs=$(sysctl -n hw.ncpu)

for patch in "$repo"/tools/gcc/patches/0001-*.patch "$repo"/tools/gcc/patches/macos/*.patch; do
  # Paths are relative to the fork root; a rerun keeps already applied patches.
  git -C "$src" apply --ignore-whitespace -R --check "$patch" 2>/dev/null ||
    git -C "$src" apply --ignore-whitespace "$patch"
done
# The fork records its build helper scripts without the executable bit.
find "$src/binutils-gdb" "$src/gcc" -type f \( -name '*.sh' -o -name install-sh -o -name mkinstalldirs \
  -o -name move-if-change -o -name missing -o -name ylwrap -o -name depcomp -o -name genmultilib \) \
  -exec chmod +x {} +

mkdir "$work/binutils" && cd "$work/binutils"
"$src/binutils-gdb/configure" --target=bfin-elf --prefix="$out" \
  --disable-werror --disable-nls --disable-gdb --disable-sim --disable-gprof --disable-gold \
  --without-zlib --without-zstd CFLAGS=-O2 CXXFLAGS=-O2 MAKEINFO=true
make -j"$jobs" all-binutils all-gas all-ld MAKEINFO=true
for dir in binutils gas ld; do make -C "$dir" install-exec MAKEINFO=true; done

# Static gmp/mpfr/mpc: a prefix holding only their headers and archives.
mkdir -p "$work/static/include" "$work/static/lib"
for lib in gmp mpfr libmpc; do
  ln -s "$brew/opt/$lib"/include/*.h "$work/static/include/"
  ln -s "$brew/opt/$lib"/lib/*.a "$work/static/lib/"
done

mkdir "$work/gcc" && cd "$work/gcc"
"$src/gcc/configure" --target=bfin-elf \
  --prefix="$out" --enable-languages=c,c++ \
  --without-headers --with-newlib --disable-shared --disable-threads \
  --disable-libssp --disable-libquadmath --disable-libgomp --disable-libatomic \
  --disable-nls --disable-werror --disable-multilib --disable-lto --without-isl \
  --disable-plugin --disable-bootstrap \
  --with-gmp="$work/static" --with-mpfr="$work/static" --with-mpc="$work/static" \
  CC=clang CXX=clang++ CFLAGS="-O2 -std=gnu11" \
  CXXFLAGS="-O2 -std=gnu++14 -Wno-narrowing" MAKEINFO=true
make -j"$jobs" all-gcc MAKEINFO=true || {
  # Patch 0001 changes target hooks documentation; accept the regenerated copy.
  cp gcc/tm.texi "$src/gcc/gcc/doc/tm.texi"
  make -j"$jobs" all-gcc MAKEINFO=true
}
make install-gcc MAKEINFO=true

rm -rf "$work"
echo "Tools: $out/bin  Bundle: $out (record reviewed hashes in profiles/toolchains.json before use)"
