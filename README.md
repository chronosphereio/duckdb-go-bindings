# duckdb-go-bindings

> [!NOTE]
> This fork rebuilds the prebuilt archives in `lib/linux-*` and
> `lib/darwin-*` from the pinned DuckDB tag with zig
> (`scripts/build_duckdb.sh`): linux against musl, so cgo binaries link
> and run on alpine, and darwin against Apple's libc++ with a macOS 15
> floor. The file set and `prebuilt.go` are upstream's, minus
> `libduckdb_jemalloc.a`, which upstream ships but never links. The
> archives are allocator-agnostic: linux builds like upstream's musl
> release, without jemalloc, so DuckDB uses the process malloc, which
> the consumer picks (the monorepo links mimalloc). Extension autoload
> and autoinstall are off in these archives, unlike upstream's.

## Updating DuckDB (this fork)

Fork: `github.com/chronosphereio/duckdb-go-bindings`, branch
`zig.0-17`, one commit on top of the upstream tag it wraps. Only the
four `lib/<platform>/*.a` sets differ from upstream; `prebuilt.go`,
`duckdb.h` and the Go code are upstream's, so a DuckDB bump is a
rebase onto the matching upstream bindings tag plus a rebuild.

Tag scheme: `lib/<platform>/v<duckdb>-zig<zig>-<build>`, e.g.
`lib/linux-arm64/v1.5.3-zig0.17.0-1`. A new DuckDB resets `<build>`
to 1; rebuilding the same DuckDB with a new zig or a fixed script
bumps it. The version appears only on the right-hand side of the
consumer's `replace`, so it is independent of the `v0.1NNMM.P`
version `duckdb-go-bindings` itself requires and only has to exist
as a tag. The sources branch (`duckdb-src`) uses
`lib/<platform>/v<duckdb>-src-<build>` so the two never collide.

1. Rebase `zig.0-17` onto the upstream tag for the new DuckDB
   (`v0.1NNMM.P` for DuckDB `vN.NN.MM`); upstream's `include/duckdb.h`
   must match the DuckDB being built.
2. Bump `DUCKDB_VERSION` and `DUCKDB_COMMIT` in
   `scripts/build_duckdb.sh`; the commit is the tag's
   (`git rev-parse <tag>^{commit}` in a DuckDB checkout, or the
   release page). `DUCKDB_EXTENSIONS` stays upstream's set unless
   `prebuilt.go`'s `LDFLAGS` changed. The CPU baselines (`-mcpu`)
   live next to them: `x86_64_v3` (AVX2) for linux-amd64 and
   darwin-amd64, matching the consumer's `GOAMD64=v3`; `apple_m1`
   for darwin-arm64, which is zig's own default for aarch64-macos;
   `generic+v8_2a+lse+crypto` for linux-arm64, deliberately without
   SVE so the binaries also run in colima/Docker Desktop VMs on Apple
   Silicon (no `neoverse_v2`/`v9a`). The linux-arm64 proof is the
   consumer's test binary passing on alpine arm64 inside colima.
3. Build the four platforms. Needs git, cmake, make and zig (the
   version in the branch name, `zig-0.17.0` from `make install-zig`
   in the monorepo lands in `_tools/bin/`); about 5 minutes and a
   few GB of disk per platform on an M-series Mac. The script clones
   DuckDB into `_build/src` on first use (checks the commit pin),
   compiles in `_build/<goos>-<goarch>` and replaces
   `lib/<goos>-<goarch>/*.a`; `_build/` is gitignored.

   ```
   scripts/build_duckdb.sh /path/to/zig-0.17.0 linux amd64
   scripts/build_duckdb.sh /path/to/zig-0.17.0 linux arm64
   scripts/build_duckdb.sh /path/to/zig-0.17.0 darwin amd64
   scripts/build_duckdb.sh /path/to/zig-0.17.0 darwin arm64
   ```

   Leave `prebuilt.go` untouched: the archive set is the one upstream's
   `LDFLAGS` name. `git status` should show only `lib/*/*.a` changes.
4. Commit (amend the fork commit; this branch is kept to one commit
   and force-pushed with `--force-with-lease`), then tag each
   platform and push:

   ```
   for p in linux-amd64 linux-arm64 darwin-amd64 darwin-arm64; do
     git tag "lib/$p/v<duckdb>-zig<zig>-<build>"
   done
   git push --force-with-lease origin zig.0-17
   git push origin 'refs/tags/lib/*'
   ```

5. In the monorepo bump the four
   `replace github.com/duckdb/duckdb-go-bindings/lib/<platform> => github.com/chronosphereio/duckdb-go-bindings/lib/<platform> <version>`
   lines in `go.mod` (and the `duckdb-go` / `duckdb-go-bindings`
   requires if DuckDB moved), `GOFLAGS=-mod=mod go mod download`, let
   `go mod tidy` refresh `go.sum`, and run `go test ./src/tako/db/live/`
   plus a zig cross build of a cgo service.

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
