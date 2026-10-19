# duckdb-go-bindings

> [!NOTE]
> This fork compiles DuckDB from source under `go build` instead of
> linking prebuilt archives; see "This fork" below. Upstream's text
> about `lib/<platform>` modules and release tooling applies only to
> `lib/windows-amd64`, the one platform module left.

## This fork

`github.com/chronosphereio/duckdb-go-bindings`, branch `duckdb-src`:
one commit on top of the upstream bindings tag it wraps. Consumers
keep the upstream module path and point it here:

```
replace github.com/duckdb/duckdb-go-bindings => github.com/chronosphereio/duckdb-go-bindings v1.5.3-src-<build>
```

The root package compiles the DuckDB v1.5.3 amalgamation (core plus
the core_functions, json, parquet and icu extensions) with cgo; the
objects land in `GOCACHE` like any other cgo package, so the C++ is
compiled once per toolchain/flags/GOOS/GOARCH and reused until the
sources change. linux builds with zig against musl run on alpine;
darwin builds use the host clang. Extension autoload and autoinstall
are off and no loadable extensions exist, so `LOAD` of anything beyond
the bundled set does not work (`TestOpenSQLiteDB` fails for that
reason). No allocator is bundled: DuckDB uses the process malloc,
which the consumer picks (the monorepo links mimalloc into its linux
cgo executables). Compiling `upstream/duckdb.cpp` needs about 9 GB of
RAM; total CPU is about 250 s on an M-series Mac.

The build tags `duckdb_use_lib` and `duckdb_use_static_lib` keep their
upstream meaning: every file below carries
`//go:build !duckdb_use_lib && !duckdb_use_static_lib`, so either tag
skips the sources and links the library you supply.

### Layout

- `upstream/`: generator output only (`duckdb.hpp`, one translation
  unit per upstream build unit, DuckDB's `LICENSE`).
  Never edit it; it can be `rm -rf`'d and regenerated. `duckdb.h` is
  `include/duckdb.h`, shared with the Go side.
- `duckdb.cpp`, `core_functions.cpp`, `json.cpp`, `parquet.cpp`,
  `icu.cpp`: one-line `#include "upstream/<same>.cpp"` wrappers; cgo
  only compiles files directly in the package directory.
- `upstream_stamp.h`: keys the go build cache to `upstream/` (see
  `gen_upstream.py`).
- `cgo_source.go`: the C++ flags (`-O3`, `-std=c++11`, autoload off).
  No CPU baseline: that is the consumer's `CC`/`CXX`.
- `gen_upstream.py`: the generator. It imports upstream's
  `scripts/amalgamation.py` unchanged, patches only include resolution
  and file writing, and refuses to run if the checkout's
  `src/include/duckdb.h` differs from `include/duckdb.h`. Its tables
  (`VERBATIM`, `INLINE_EXTRA`, `ANGLE_DIRS`, `PRELUDE`, `RENAMES`)
  list where one TU per build unit exposes what upstream's per-file
  build hides; each miss is a loud compile error, fixed by one more
  entry, never by editing `upstream/`.

### Updating DuckDB

1. Rebase `duckdb-src` onto the upstream bindings tag for the new
   DuckDB (`v0.1NNMM.P` for DuckDB `vN.NN.MM`), keeping one commit.
2. Regenerate from a checkout of the matching DuckDB tag:

   ```
   git clone --depth 1 --branch v1.5.3 https://github.com/duckdb/duckdb.git /tmp/duckdb-v1.5.3
   rm -rf upstream upstream_stamp.h
   python3 gen_upstream.py /tmp/duckdb-v1.5.3
   ```

   (`DUCKDB_SRC=/tmp/duckdb-v1.5.3 go generate .` runs the last line.)
3. `go vet ./...`, `go test -skip TestOpenSQLiteDB .`, and the
   consumer's tests against the working tree (a filesystem `replace`).
4. Tag the root `v<duckdb>-src-<build>` (e.g. `v1.5.3-src-4`); a new
   DuckDB resets `<build>` to 1. The tag only appears on the right-hand
   side of the consumer's `replace`, so it is independent of the
   `v0.1NNMM.P` versions upstream publishes. Push the branch
   (`--force-with-lease`) and the tag, then bump the consumer's
   `replace` and let `go mod tidy` refresh `go.sum`.

![Tests status](https://github.com/duckdb/duckdb-go-bindings/actions/workflows/run_tests.yml/badge.svg)

This repository wraps DuckDB's C API calls in Go native types and functions.

Minimum Go version: 1.24.

#### 🚧 WORK IN PROGRESS 🚧

> [!IMPORTANT]
> Some type aliases and function wrappers are still missing.
>
> Breaking changes can happen.

## Releases

### Semantic versioning

Starting with DuckDB `v1.5.0` the duckdb-go-bindings package changes its versioning scheme to contain
- the DuckDB release version
- the duckdb-go-bindings patch iteration

For `v1.5.0` the corresponding tagged release is `v0.10500.0`.

### Single module (v0.3.0+)

Starting with v0.3.0, the module includes pre-built static libraries for all platforms. Simply import `github.com/duckdb/duckdb-go-bindings`.

| duckdb version | module version |
| -------------- | -------------- |
| v1.4.4         | v0.3.3         |
| v1.4.3         | v0.3.0         |

### Legacy per-platform submodules (v0.1.x)

Older versions require platform-specific imports (e.g., `github.com/duckdb/duckdb-go-bindings/darwin-arm64`). These tags continue to work.

| duckdb version | main    | darwin  | linux   | windows |
| -------------- | ------- | ------- | ------- | ------- |
| v1.4.3         | v0.1.24 | v0.1.24 | v0.1.24 | v0.1.24 |
| v1.4.2         | v0.1.23 | v0.1.23 | v0.1.23 | v0.1.23 |
| v1.4.1         | v0.1.21 | v0.1.21 | v0.1.21 | v0.1.21 |
| v1.4.0         | v0.1.19 | v0.1.19 | v0.1.19 | v0.1.19 |
| v1.3.2         | v0.1.17 | v0.1.12 | v0.1.12 | v0.1.12 |
| v1.3.1         | v0.1.16 | v0.1.11 | v0.1.11 | v0.1.11 |
| v1.3.0         | v0.1.15 | v0.1.10 | v0.1.10 | v0.1.10 |
| v1.2.2         | v0.1.14 | v0.1.9  | v0.1.9  | v0.1.9  |
| v1.2.1         | v0.1.13 | v0.1.8  | v0.1.8  | v0.1.8  |
| v1.2.0         | v0.1.10 | v0.1.5  | v0.1.5  | v0.1.5  |

## Known Issues

### Malformed default extension directory on Windows (DuckDB v1.5.0 only)

DuckDB v1.5.0 has a [regression](https://github.com/duckdb/duckdb/pull/21260) where the default extension directory is malformed on Windows. 
This causes extension directory creation to fail and **has been fixed in `v1.5.1`.**
To work around this, set `extension_directory` explicitly in your DuckDB configuration:

```go
config := duckdb.CreateConfig()
duckdb.SetConfig(config, "extension_directory", `C:\path\to\ext\dir`)
```

## Local Development

To develop locally, copy the workspace template file:

```bash
cp go.work.dev go.work
```

This sets up Go workspaces to use the local lib/\* submodules instead of fetching from the module proxy.

## Releasing a new DuckDB version

1. Create a new branch and update the `DUCKDB_VERSION` in the `Makefile`.
2. Invoke the `Fetch and Push Libs` workflow on the new branch (it commits fetched libs to the branch; it does not tag).
3. If the header (`duckdb.h`) has changes, add all changes (new types, functions, etc.) to the bindings.
4. Open a PR.
5. Wait for all tests to pass.
6. Merge the PR into `main` (direct pushes to `main` are not allowed).
7. Publish tags using the release script (re-entrant, safe to run multiple times):

```bash
./scripts/release.sh v0.10502.0           # pushes to 'origin'
./scripts/release.sh v0.10502.0 upstream  # pushes to custom remote
```

The script handles:

- Tagging and pushing lib/\* submodules
- Updating root module deps (stops for PR if changes needed)
- Tagging and pushing root module

Run it again after merging the deps PR to complete the release.

## Installation

Simply import the module in your Go project:

```go
import "github.com/duckdb/duckdb-go-bindings"
```

The module includes pre-built static libraries for all supported platforms:

- darwin-amd64
- darwin-arm64
- linux-amd64
- linux-arm64
- windows-amd64

Platform detection and linking is handled automatically through cgo directives. `CGO_ENABLED=1` is required, and your system needs a C compiler.

## Build Configuration

### Default: Pre-built Static Libraries

By default (no build tags needed), the module automatically links against the pre-built static libraries for your platform:

```bash
go build  # Just works!
go test   # Just works!
```

The appropriate library and linker flags are selected automatically based on your OS and architecture.

### Alternative: Custom Static Libraries

To use your own DuckDB static library instead of the pre-built ones, use the `duckdb_use_static_lib` build tag and provide library paths via `CGO_LDFLAGS`:

```bash
# Darwin/macOS
CGO_ENABLED=1 \
  CPPFLAGS="-DDUCKDB_STATIC_BUILD" \
  CGO_LDFLAGS="-lduckdb -lc++ -L/path/to/lib" \
  go build -tags=duckdb_use_static_lib

# Linux
CGO_ENABLED=1 \
  CPPFLAGS="-DDUCKDB_STATIC_BUILD" \
  CGO_LDFLAGS="-lduckdb -lstdc++ -lm -ldl -L/path/to/lib" \
  go build -tags=duckdb_use_static_lib

# Windows
CGO_ENABLED=1 \
  CPPFLAGS="-DDUCKDB_STATIC_BUILD" \
  CGO_LDFLAGS="-lduckdb -lws2_32 -lwsock32 -lrstrtmgr -lstdc++ -lm --static -L/path/to/lib" \
  go build -tags=duckdb_use_static_lib
```

### Alternative: Dynamic Libraries

To link against a shared DuckDB library, use the `duckdb_use_lib` build tag:

```bash
# Darwin/macOS
CGO_ENABLED=1 \
  CGO_LDFLAGS="-lduckdb -L/path/to/dir" \
  DYLD_LIBRARY_PATH=/path/to/dir \
  go build -tags=duckdb_use_lib

# Linux
CGO_ENABLED=1 \
  CGO_LDFLAGS="-lduckdb -L/path/to/dir" \
  LD_LIBRARY_PATH=/path/to/dir \
  go build -tags=duckdb_use_lib
```

## Arrow functions

Provide the duckdb_arrow build tag if you want to use arrow functions
