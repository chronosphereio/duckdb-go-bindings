//go:build !duckdb_use_lib && !duckdb_use_static_lib

package duckdb_go_bindings

// DuckDB is compiled from upstream/ by the .cpp wrappers next to this
// file; upstream_stamp.h keys the go build cache to upstream/.

/*
#cgo CXXFLAGS: -w -std=c++11 -g0 -O3 -DNDEBUG -DDUCKDB_BUILD_LIBRARY -DDUCKDB_EXTENSION_AUTOLOAD_DEFAULT=0 -DDUCKDB_EXTENSION_AUTOINSTALL_DEFAULT=0 -I${SRCDIR}/upstream
#include "upstream_stamp.h"
*/
import "C"

//go:generate python3 gen_upstream.py ${DUCKDB_SRC}
