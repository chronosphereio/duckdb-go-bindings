//go:build cgo

package duckdbsrc

/*
#cgo CPPFLAGS: -I${SRCDIR}/upstream -DDUCKDB_STATIC_BUILD
#cgo CXXFLAGS: -w -std=c++11 -g0 -O3 -DNDEBUG -DDUCKDB_BUILD_LIBRARY -DDUCKDB_EXTENSION_AUTOLOAD_DEFAULT=0 -DDUCKDB_EXTENSION_AUTOINSTALL_DEFAULT=0
#cgo CFLAGS: -w -g0 -O3 -DNDEBUG
#include "upstream_stamp.h"
#include <duckdb.h>
*/
import "C"
