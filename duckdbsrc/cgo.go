//go:build cgo

package duckdbsrc

/*
#cgo CPPFLAGS: -I${SRCDIR}/upstream -DDUCKDB_STATIC_BUILD
#cgo CXXFLAGS: -w -std=c++11 -g0 -DNDEBUG -DDUCKDB_BUILD_LIBRARY -DDUCKDB_EXTENSION_AUTOLOAD_DEFAULT=0 -DDUCKDB_EXTENSION_AUTOINSTALL_DEFAULT=0 -Wno-date-time
#cgo CFLAGS: -w -g0 -DNDEBUG
#cgo linux CXXFLAGS: -DDUCKDB_ENABLE_JEMALLOC
#include "upstream_stamp.h"
#include <duckdb.h>
*/
import "C"
