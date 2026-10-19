#!/usr/bin/env bash
#
# Rebuilds the static archives in lib/<goos>-<goarch> from the pinned
# DuckDB tag with zig: linux targets against musl so they link on alpine,
# darwin targets against Apple's libc++. The file set is the one upstream
# ships (DuckDB's gather-libs recipe) minus jemalloc, which prebuilt.go
# never links, so prebuilt.go stays untouched.
#
# usage: scripts/build_duckdb.sh <zig> <goos> <goarch>
#
# DuckDB is checked out into _build/src and compiled in
# _build/<goos>-<goarch>. Requires git, cmake and make.

[[ -z ${DEBUG:-} ]] || set -o xtrace

set -o errexit
set -o nounset
set -o pipefail

__dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd "${__dir}/.." && pwd)"

# Must match the DuckDB version wrapped by this module (see go.mod tags).
DUCKDB_VERSION="v1.5.3"
DUCKDB_COMMIT="14eca11bd9d4a0de2ea0f078be588a9c1c5b279c"
# Upstream's set on top of the defaults (core_functions, parquet).
DUCKDB_EXTENSIONS="json;icu;autocomplete;tpch;tpcds"
# C/C++ CPU baselines (zig -mcpu). x86_64_v3 (AVX2) matches the
# consumer's GOAMD64=v3; apple_m1 is zig's own default for
# aarch64-macos, spelled out; linux arm64 is v8.2-A+LSE+crypto without
# SVE so the archives also run in colima/Docker Desktop VMs on Apple
# Silicon (no neoverse_v2/v9a).
MCPU_AMD64="x86_64_v3"
MCPU_DARWIN_ARM64="apple_m1"
MCPU_LINUX_ARM64="generic+v8_2a+lse+crypto"

function checkout() {
  local src="$1"
  if [[ ! -d "${src}/.git" ]]; then
    git clone --depth 1 --branch "${DUCKDB_VERSION}" \
      https://github.com/duckdb/duckdb.git "${src}"
  fi
  local head
  head="$(git -C "${src}" rev-parse HEAD)"
  if [[ "${head}" != "${DUCKDB_COMMIT}" ]]; then
    echo >&2 "${src} is at ${head}, expected ${DUCKDB_COMMIT} (${DUCKDB_VERSION})"
    exit 1
  fi
}

# CMake wants single executables, so zig subcommands get wrappers.
function write_zig_wrappers() {
  local zig="$1" wrap="$2" target="$3" mcpu="$4"
  mkdir -p "${wrap}"
  printf '#!/bin/sh\nexec "%s" cc -target %s %s "$@"\n' "${zig}" "${target}" "${mcpu:+-mcpu=${mcpu}}" > "${wrap}/cc"
  printf '#!/bin/sh\nexec "%s" c++ -target %s %s "$@"\n' "${zig}" "${target}" "${mcpu:+-mcpu=${mcpu}}" > "${wrap}/c++"
  printf '#!/bin/sh\nexec "%s" ar "$@"\n' "${zig}" > "${wrap}/ar"
  printf '#!/bin/sh\nexec "%s" ranlib "$@"\n' "${zig}" > "${wrap}/ranlib"
  chmod +x "${wrap}"/*
}

# ICU's putil.cpp includes Apple's <tzfile.h>, which zig does not ship.
function write_tzfile_shim() {
  local shim="$1"
  mkdir -p "${shim}"
  cat > "${shim}/tzfile.h" << 'EOF'
#ifndef TZFILE_H
#define TZFILE_H
#define TZDIR "/var/db/timezone/zoneinfo"
#define TZDEFAULT "/etc/localtime"
#endif
EOF
}

function configure() {
  local zig="$1" goos="$2" goarch="$3" src="$4" build="$5"
  local zarch="${goarch/amd64/x86_64}"
  zarch="${zarch/arm64/aarch64}"
  # zig adds -Werror=date-time and third_party/pcg uses __DATE__; -g0
  # because zig emits DWARF even at -O3, which makes the lib 1 GB.
  local cflags="-Wno-date-time -g0"
  local cxxflags="${cflags}"
  local target mcpu
  local -a flags=()
  case "${goos}-${goarch}" in
  linux-amd64 | darwin-amd64) mcpu="${MCPU_AMD64}" ;;
  darwin-arm64) mcpu="${MCPU_DARWIN_ARM64}" ;;
  linux-arm64) mcpu="${MCPU_LINUX_ARM64}" ;;
  esac
  case "${goos}" in
  linux)
    target="${zarch}-linux-musl"
    # Like upstream's musl release: no jemalloc, DuckDB uses malloc.
    flags+=(
      -DCMAKE_SYSTEM_NAME=Linux
      -DCMAKE_SYSTEM_PROCESSOR="${zarch}"
      -DMUSL_ENABLED=ON
    )
    ;;
  darwin)
    # 15.0: zig's libc++ needs std::__hash_memory, exported from macOS 15.
    target="${zarch}-macos.15.0"
    write_tzfile_shim "${build}/shim"
    cxxflags+=" -isystem ${build}/shim"
    # CMake spells Apple Silicon arm64, unlike zig's aarch64.
    flags+=(
      -DCMAKE_SYSTEM_NAME=Darwin
      -DCMAKE_SYSTEM_PROCESSOR="${goarch/amd64/x86_64}"
    )
    ;;
  esac
  write_zig_wrappers "${zig}" "${build}/zig-wrappers" "${target}" "${mcpu}"
  cmake -S "${src}" -B "${build}" \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_C_COMPILER="${build}/zig-wrappers/cc" \
    -DCMAKE_CXX_COMPILER="${build}/zig-wrappers/c++" \
    -DCMAKE_AR="${build}/zig-wrappers/ar" \
    -DCMAKE_RANLIB="${build}/zig-wrappers/ranlib" \
    -DCMAKE_C_FLAGS="${cflags}" \
    -DCMAKE_CXX_FLAGS="${cxxflags}" \
    -DBUILD_SHELL=OFF -DBUILD_UNITTESTS=OFF -DBUILD_BENCHMARKS=OFF \
    -DENABLE_SANITIZER=OFF -DENABLE_UBSAN=OFF \
    -DENABLE_EXTENSION_AUTOLOADING=OFF -DENABLE_EXTENSION_AUTOINSTALL=OFF \
    -DOVERRIDE_GIT_DESCRIBE="${DUCKDB_VERSION}" \
    -DBUILD_EXTENSIONS="${DUCKDB_EXTENSIONS}" \
    "${flags[@]}"
}

function compile() {
  local build="$1"
  # Only the static targets: the loadable extensions do not link with zig.
  local -a targets=(duckdb_static duckdb_generated_extension_loader)
  local ext
  for ext in core_functions parquet ${DUCKDB_EXTENSIONS//;/ }; do
    targets+=("${ext}_extension")
  done
  cmake --build "${build}" --parallel "$(getconf _NPROCESSORS_ONLN)" --target "${targets[@]}"
}

# DuckDB's own gather-libs set, minus the dummy loader and jemalloc.
function gather() {
  local build="$1" src="$2" out="$3"
  if ! cmp -s "${src}/src/include/duckdb.h" "${out}/duckdb.h"; then
    echo >&2 "${src}/src/include/duckdb.h differs from ${out}/duckdb.h:"
    echo >&2 "DuckDB ${DUCKDB_VERSION} does not match the bindings this branch sits on;"
    echo >&2 "rebase onto the upstream duckdb-go-bindings release for ${DUCKDB_VERSION} first"
    exit 1
  fi
  rm -f "${out}"/*.a
  cd "${build}"
  cp -f \
    src/libduckdb_static.a \
    third_party/*/libduckdb_*.a \
    extension/libduckdb_generated_extension_loader.a \
    extension/*/lib*_extension.a \
    "${out}/"
}

if [[ $# -ne 3 ]]; then
  echo >&2 "usage: $0 <zig> <goos> <goarch>"
  exit 1
fi

zig="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
goos="$2"
goarch="$3"
case "${goos}-${goarch}" in
linux-amd64 | linux-arm64 | darwin-amd64 | darwin-arm64) ;;
*)
  echo >&2 "unsupported target ${goos}-${goarch}"
  exit 1
  ;;
esac
out="${root}/lib/${goos}-${goarch}"
build="${root}/_build/${goos}-${goarch}"

checkout "${root}/_build/src"
configure "${zig}" "${goos}" "${goarch}" "${root}/_build/src" "${build}"
compile "${build}"
gather "${build}" "${root}/_build/src" "${out}"
ls -la "${out}"
