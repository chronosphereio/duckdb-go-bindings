# duckdbsrc

DuckDB v1.5.3 as an amalgamation, compiled by `go build` (cgo) instead
of linking prebuilt archives. Objects land in `GOCACHE` like any other
cgo package, so the C++ is compiled once per toolchain/flag/GOOS/GOARCH
combination and reused until the module version changes.

Module: `github.com/chronosphereio/duckdb-go-bindings/duckdbsrc`, tagged
`duckdbsrc/v<duckdb version>-<build>` (`duckdbsrc/v1.5.3-<build>`).

Extension autoload and autoinstall are off and no loadable extensions
are built, so unlike upstream's archives `LOAD` of anything beyond the
bundled set (core_functions, json, parquet, icu) does not work.

## How it is wired

This fork's `lib/linux-*` and `lib/darwin-*` modules contain nothing
but a blank import of this module; `duckdb-go-bindings` imports the
`lib/<platform>` module for the current GOOS/GOARCH exactly as
upstream does, so consumers need no build tag. Only the module path is
a contract: the files below can change without touching
`lib/<platform>`.

`cgo.go` carries `//go:build cgo`, so a `CGO_ENABLED=0` build sees an
empty package. Its `-O3` follows cgo's default `-O2 -g` on the command
line and wins, matching upstream's Release build and the binaries
branch. It has no `LDFLAGS`: the go linker adds the C++ runtime
itself, and an explicit `-lc++` would be a duplicate. It sets no CPU
baseline either: that is the consumer's `CC`/`CXX`. The monorepo
passes `-mcpu=x86_64_v3` for linux-amd64 to match `GOAMD64=v3`, and
`-mcpu=generic+v8_2a+lse+crypto` for linux-arm64, no SVE, so the
binaries also run in colima/Docker Desktop VMs on Apple Silicon; the
proof for that is the consumer's linux-arm64 test binary passing on
alpine arm64 inside colima.

## Layout

Everything derived from DuckDB lives in `upstream/`, which is only
ever written by the generator and can be `rm -rf`'d and regenerated.
Everything else in this directory is hand-written and static, with one
exception, `upstream_stamp.h` (see below).

`upstream/` (generator output, do not edit):

| file                | what                                                          |
|---------------------|---------------------------------------------------------------|
| `duckdb.hpp`        | upstream's amalgamation header, byte-identical to theirs       |
| `duckdb.cpp`        | core + `third_party/` + the static extension loader            |
| `core_functions.cpp`, `json.cpp`, `parquet.cpp`, `icu.cpp` | one TU per extension; parquet bundles thrift, snappy, lz4, brotli; icu includes its stubdata |
| `jemalloc.c`        | jemalloc as C99                                               |
| `duckdb.h`          | the C API header, `src/include/duckdb.h` of the checkout      |
| `LICENSE`           | DuckDB's                                                      |
| `VERSION.txt`       | tag, commit and extension list the files were generated from  |

Top level (hand-written):

| file                | what                                                          |
|---------------------|---------------------------------------------------------------|
| `cgo.go`            | the `#cgo` flags; `-I${SRCDIR}/upstream`                      |
| `duckdb.cpp`, `core_functions.cpp`, `json.cpp`, `parquet.cpp`, `icu.cpp` | one-line `#include "upstream/<same>.cpp"` wrappers |
| `jemalloc_linux.c`  | `#include "upstream/jemalloc.c"`; the `_linux` suffix makes cgo skip it elsewhere |
| `gen_duckdbsrc.py`  | the generator                                                 |
| `doc.go`, `go.mod`, this file |                                                     |

The wrappers exist because cgo only compiles files directly in the
package directory. `upstream_stamp.h` is the single generated file
outside `upstream/`: one `#define DUCKDBSRC_UPSTREAM "<tag> <commit>
<sha256 of upstream/>"`, included by `cgo.go`. The go build cache
hashes the files in the package directory and nothing below it, and
with `-trimpath` not even the directory path, so without the stamp a
regenerated `upstream/` would keep hitting objects built from the old
one. Editing a file in `upstream/` by hand has exactly that effect:
the next build silently reuses the cached objects. Always go through
the generator.

The static loader at the top of `duckdb.cpp` defines
`DUCKDB_EXTENSION_<X>_LINKED` itself, so `cgo.go` needs no `-D` for
the extension set. jemalloc is paired by GOOS: `jemalloc_linux.c` is
only compiled on linux and `-DDUCKDB_ENABLE_JEMALLOC` is only set in
the linux `CXXFLAGS`, which is what DuckDB's CMake does (minus its
musl exclusion; jemalloc builds and runs fine on musl). darwin uses
the system allocator, as upstream's archives do.

It is one translation unit per upstream build unit, not one file:
libpg_query's `ON` token and keyword `#define`s, its `makeNode` macro
and several namespace-scope statics clash with ICU and across
extensions when they meet in one TU.

Compiling `duckdb.cpp` needs about 9 GB of RAM (true of upstream's
own amalgamation too); `icu.cpp` is the next largest. Total CPU is
about 250 s on an M-series Mac against about 770 s for the per-file
layout; wall time is bounded by `duckdb.cpp`.

## Updating DuckDB

`duckdb.h` must match the `duckdb-go-bindings` release that wraps it,
so DuckDB, `duckdb-go-bindings` and `duckdb-go` move in lock-step: pick
the bindings tag for the new DuckDB (`v0.1NNMM.P` for DuckDB
`vN.NN.MM`), rebase this branch onto it, then regenerate. The
generator refuses to run if the checkout's `src/include/duckdb.h`
differs from `../include/duckdb.h`.

Version scheme: `duckdbsrc/v<duckdb>-<build>` for this module and
`lib/<platform>/v<duckdb>-src-<build>` for the four lib modules (the
`-src-` keeps them apart from the binaries branch's
`lib/<platform>/v<duckdb>-zig<zig>-<build>`). A new DuckDB resets
`<build>` to 1; regenerating the same DuckDB with a fixed generator
bumps it. No zig version in it: consumers compile with their own
toolchain. The replace in a consumer's go.mod names this version on
its right-hand side; it is independent of the `v0.1NNMM.P` version
`duckdb-go-bindings` requires and only has to exist as a tag.

```
git clone --depth 1 --branch v1.5.3 https://github.com/duckdb/duckdb.git /tmp/duckdb-v1.5.3
cd duckdbsrc
rm -rf upstream upstream_stamp.h
python3 gen_duckdbsrc.py /tmp/duckdb-v1.5.3 upstream
go vet ./...
cd ..
git add -A duckdbsrc
```

(`DUCKDB_SRC=/tmp/duckdb-v1.5.3 go generate .` runs the generator
line; the `rm -rf` is what the generator does first anyway, nothing
else is touched.) Then:

1. Bump the `require` in `lib/{linux,darwin}-{amd64,arm64}/go.mod` to
   the new `duckdbsrc` version and commit.
2. Run the consumer's tests against the working tree, e.g. from the
   monorepo with
   `replace github.com/chronosphereio/duckdb-go-bindings/duckdbsrc => <this dir>`
   in `go.mod`: `go test -count=1 ./src/tako/db/live/`, and a zig cross
   compile of a cgo service for linux to see `jemalloc_linux.c` build.
3. Tag the commit `duckdbsrc/v<duckdb>-<build>` and
   `lib/<platform>/v<duckdb>-src-<build>` for the four platforms, push
   the branch and the tags.
4. In the monorepo bump the four
   `replace github.com/duckdb/duckdb-go-bindings/lib/<platform> => github.com/chronosphereio/duckdb-go-bindings/lib/<platform> <version>`
   lines and the indirect `require` of `duckdbsrc`, then
   `GOFLAGS=-mod=mod go mod download` and let `go mod tidy` refresh
   `go.sum`.

The generator imports upstream's `scripts/amalgamation.py` unchanged
and only patches how includes are resolved and files are written. It
is deterministic for a given checkout.

### Maintenance rule for a new DuckDB version

The generator's tables (`VERBATIM`, `INLINE_EXTRA`, `ANGLE_DIRS`,
`REINLINE`, `PRELUDE`, `RENAMES`) list the places where upstream's
per-file build hides something a single TU exposes: an include that
must stay verbatim, one upstream leaves to `-I`, a header meant to be
inlined twice, or a namespace-scope name that two files of one build
unit both define. Each of those is a loud compile error (a
redefinition, a missing declaration, a header mismatch), never a
silent miscompile. When a new upstream version introduces one, add
one more table entry, rerun, and recompile; do not edit the generated
files.
