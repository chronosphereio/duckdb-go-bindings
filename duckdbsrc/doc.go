// Package duckdbsrc compiles DuckDB from source as part of the Go build.
//
// Importing it (a blank import is enough) makes cgo compile the DuckDB
// amalgamation in upstream/ (core plus the core_functions, json, parquet
// and icu extensions; jemalloc on linux) into Go's build cache. The
// objects satisfy the symbols github.com/duckdb/duckdb-go-bindings
// expects from its prebuilt lib/<platform> archives. See README.md.
package duckdbsrc

//go:generate python3 gen_duckdbsrc.py ${DUCKDB_SRC} upstream
