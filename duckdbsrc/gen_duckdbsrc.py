#!/usr/bin/env python3
"""DuckDB amalgamation with statically linked extensions.

Usage: python3 gen_duckdbsrc.py <duckdb-checkout> <out-dir>

Thin wrapper over upstream scripts/amalgamation.py (imported unchanged).
Replaces <out-dir> with duckdb.hpp, one translation unit per upstream
build unit (duckdb.cpp = core + third_party + static loader, <ext>.cpp
per extension in EXTENSIONS, jemalloc.c as C99), the C API header
duckdb.h, DuckDB's LICENSE and a VERSION.txt stamp. One TU per build unit
keeps the libraries from meeting each other's macros and namespace-scope
statics. The only file written outside <out-dir> is
<out-dir>/../upstream_stamp.h, which cgo.go includes so that the go
build cache (it hashes package-dir files only) sees a regeneration.
"""
import hashlib
import importlib
import os
import re
import shutil
import subprocess
import sys
import tempfile

EXTENSIONS = ['core_functions', 'json', 'parquet', 'icu']
JEMALLOC = os.path.join('third_party', 'jemalloc')

if len(sys.argv) != 3:
    sys.exit(__doc__)
src_root, out_dir = sys.argv[1], os.path.abspath(sys.argv[2])
module_dir = os.path.dirname(out_dir)
bindings_header = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'include', 'duckdb.h')
shutil.rmtree(out_dir, ignore_errors=True)
os.makedirs(out_dir)
os.chdir(src_root)
sys.path.insert(0, 'scripts')
import amalgamation as am  # noqa: E402

# Extension sources and include dirs come from each <ext>_config.py, the
# lists package_build.py uses for the Python wheel.
ext_dirs = {}
for ext in EXTENSIONS:
    sys.path.insert(0, os.path.join('extension', ext))
    cfg = importlib.import_module(ext + '_config')
    am.include_paths += cfg.include_directories
    ext_dirs[ext] = sorted({os.path.normpath(os.path.dirname(f)) for f in cfg.source_files})
am.include_paths.append(os.path.join(JEMALLOC, 'include'))
am.excluded_files.append('jemalloc_cpp.cpp')  # OVERRIDE_NEW_DELETE is off
# Not under third_party/, so upstream's license scan does not see it.
ICU_LICENSE = os.path.join('extension', 'icu', 'third_party', 'icu', 'LICENSE')

# Upstream leaves these #includes verbatim (they expect -I dirs at build
# time); resolve them so the output is self-contained.
INLINE_EXTRA = {
    'extension_helper.cpp': [
        ('#include "%s_extension.hpp"' % e, os.path.join('extension', e, 'include', e + '_extension.hpp'))
        for e in EXTENSIONS
    ],
    'allocator_jemalloc.cpp': [
        ('#include "jemalloc/jemalloc.h"', os.path.join(JEMALLOC, 'include', 'jemalloc', 'jemalloc.h')),
        ('#include "duckdb/malloc_ncpus.h"', os.path.join(JEMALLOC, 'include', 'duckdb', 'malloc_ncpus.h')),
    ],
}

# Quoted includes upstream must not try to resolve: a system header,
# files that only exist behind inactive #ifdefs, and jemalloc's FreeBSD
# and Windows TSD backends. The latter come first in tsd.h's #if chain,
# so inlining them there would swallow headers shared with tsd_tls.h
# (the Linux backend) into a dead branch.
VERBATIM = {
    'stdio.h',
    'config.h',
    'ucln_local_hook.c',
    'jemalloc/internal/private_namespace_jet.h',
    'jemalloc/internal/tsd_malloc_thread_cleanup.h',
    'jemalloc/internal/tsd_win.h',
}
INCLUDE = re.compile(r'^[\t ]*#[\t ]*include[\t ]+"([^"]+)"')
# brotli and parquet_types.h include vendored thrift/brotli headers
# with <>, which upstream never inlines. Only from these trees: httplib
# names the same headers inside a dead #ifdef, which would swallow them.
ANGLE = re.compile(r'^[\t ]*#[\t ]*include[\t ]+<((thrift|brotli)/[^>]+)>', re.M)
ANGLE_DIRS = (os.path.join('third_party', 'brotli'), os.path.join('third_party', 'parquet'))

# Meant to be included more than once per TU, so it is inlined every
# time instead of on first sight: jemalloc's malloc_io.c #undefs its
# macros at the end and the next file re-includes it.
REINLINE = {os.path.join(JEMALLOC, 'include', 'jemalloc', 'internal', 'assert.h')}
# lz4.cpp needs lz4.hpp's LZ4_STATIC_LINKING_ONLY section, but the
# header is inlined once, at its first user (column_reader.cpp).
PRELUDE = {'parquet.cpp': '#define LZ4_STATIC_LINKING_ONLY\n\n'}

# Namespace-scope names that repeat across files of one build unit;
# DuckDB compiles those files separately, one TU makes them clash.
RENAMES = {
    os.path.join('extension', 'icu', 'icu-dateadd.cpp'): [('ICUCalendarSub', 'ICUCalendarSubtract')],
    os.path.join('third_party', 'brotli', 'enc', 'compress_fragment.cpp'): [
        ('kHashMul32', 'kHashMul32Fragment'),
        ('BrotliStoreMetaBlockHeader', 'BrotliStoreMetaBlockHeaderFragment'),
        ('RewindBitPosition', 'RewindBitPositionFragment'),
    ],
    os.path.join('third_party', 'brotli', 'enc', 'compress_fragment_two_pass.cpp'): [
        ('kHashMul32', 'kHashMul32TwoPass'),
        ('BrotliStoreMetaBlockHeader', 'BrotliStoreMetaBlockHeaderTwoPass'),
        ('RewindBitPosition', 'RewindBitPositionTwoPass'),
    ],
    os.path.join('third_party', 'brotli', 'enc', 'entropy_encode.cpp'): [('SortHuffmanTree', 'SortHuffmanTreeEntropy')],
}

upstream_get_includes = am.get_includes
upstream_write_file = am.write_file


def get_includes(fpath, text):
    # Upstream raises on repeated and on unresolvable #includes (ICU,
    # snappy, jemalloc have both). Hand it a filtered copy; write_file
    # replaces every occurrence of a statement, so repeats get inlined.
    # Like the preprocessor, look in the including file's directory
    # first (brotli has dec/state.h and enc/state.h); upstream does not.
    am.include_paths.insert(0, os.path.dirname(fpath))
    seen = set()
    lines = []
    for line in text.split('\n'):
        m = INCLUDE.match(line)
        if m and (m.group(1) in VERBATIM or m.group(0) in seen):
            continue
        if m:
            seen.add(m.group(0))
        lines.append(line)
    statements, files = upstream_get_includes(fpath, '\n'.join(lines))
    am.include_paths.pop(0)
    extra = list(INLINE_EXTRA.get(os.path.basename(fpath), []))
    if fpath.startswith(ANGLE_DIRS):
        extra += [(m.group(0), find_include(m.group(1))) for m in ANGLE.finditer(text)]
    for statement, path in extra:
        statements.append(statement)
        files.append(path)
    return statements, files


def find_include(name):
    for include_path in am.include_paths:
        if os.path.isfile(os.path.join(include_path, name)):
            return os.path.join(include_path, name)
    raise Exception('Could not find include file ' + name)


def write_file(current_file, ignore_excluded=False):
    text = upstream_write_file(current_file, ignore_excluded)
    path = os.path.normpath(current_file)
    for old, new in RENAMES.get(path, []):
        text = re.sub(r'\b%s\b' % old, new, text)
    if path in REINLINE:
        am.written_files.pop(current_file)
    if path.endswith('LICENSE'):
        text = text.replace('*/', '* /')  # ICU's license would end the comment
    return text


am.get_includes = get_includes
am.write_file = write_file


def static_loader():
    """What package_build.py emits as generated_extension_loader_package_build.cpp."""
    defines = headers = body = names = ''
    for ext in EXTENSIONS:
        define = 'DUCKDB_EXTENSION_%s_LINKED' % ext.upper()
        klass = ext.replace('_', ' ').title().replace(' ', '') + 'Extension'
        defines += '#define %s 1\n' % define
        headers += '#include "%s_extension.hpp"\n' % ext
        body += (
            '    if (extension == "%s") {\n'
            '        db.LoadStaticExtension<%s>();\n'
            '        return ExtensionLoadResult::LOADED_EXTENSION;\n'
            '    }\n' % (ext, klass)
        )
        names += '\n        "%s",' % ext
    with open(os.path.join('extension', 'generated_extension_loader.cpp.in')) as f:
        loader = f.read()
    loader = (
        loader.replace('${EXT_LOADER_BODY}', body)
        .replace('${EXT_NAME_VECTOR_INITIALIZER}', names)
        .replace('${EXT_TEST_PATH_INITIALIZER}', '')
    )
    return defines + '\n' + headers + '\n' + loader


def write_tu(name, dirs, include_header=True, licenses=()):
    # Every TU inlines its own headers; only duckdb.hpp's stay shared.
    am.written_files = dict(hpp_written)
    am.licenses = list(licenses)
    with open(os.path.join(out_dir, name), 'w') as f:
        if include_header:  # same prelude as upstream's generate_amalgamation
            f.write('#include "duckdb.hpp"\n\n#ifndef DUCKDB_AMALGAMATION\n#error header mismatch\n#endif\n\n')
            f.write('#if (!defined(DEBUG) && !defined NDEBUG)\n#define NDEBUG\n#endif\n\n')
        f.write(PRELUDE.get(name, ''))
        for d in dirs:
            f.write(am.write_dir(d))
        f.write('\n\n/*\n')
        for i, license in enumerate(am.licenses):
            f.write('\n\n\n### THIRD PARTY LICENSE #%d ###\n\n' % (i + 1))
            f.write(am.write_file(license))
        f.write('\n\n*/\n')


am.generate_duckdb_hpp(os.path.join(out_dir, 'duckdb.hpp'))
shutil.move(am.temp_header, os.path.join(out_dir, 'duckdb.hpp'))
hpp_written = dict(am.written_files)

# The loader goes first so its DUCKDB_EXTENSION_*_LINKED defines are seen
# by src/main/extension/extension_helper.cpp; it replaces extension/loader.
with tempfile.TemporaryDirectory() as loader_dir:
    with open(os.path.join(loader_dir, 'generated_extension_loader.cpp'), 'w') as f:
        f.write(static_loader())
    am.compile_directories.remove(os.path.join('extension', 'loader'))
    write_tu('duckdb.cpp', [loader_dir] + am.compile_directories)
for ext in EXTENSIONS:
    write_tu(ext + '.cpp', ext_dirs[ext], licenses=[ICU_LICENSE] if ext == 'icu' else ())
write_tu('jemalloc.c', [os.path.join(JEMALLOC, 'src')], include_header=False)

# duckdb-go-bindings' own duckdb.h is the same release's; a mismatch
# means the bindings and this module were not bumped in lock-step.
with open(os.path.join('src', 'include', 'duckdb.h'), 'rb') as f, open(bindings_header, 'rb') as g:
    if f.read() != g.read():
        sys.exit('src/include/duckdb.h differs from %s' % os.path.normpath(bindings_header))
shutil.copyfile(os.path.join('src', 'include', 'duckdb.h'), os.path.join(out_dir, 'duckdb.h'))
shutil.copyfile('LICENSE', os.path.join(out_dir, 'LICENSE'))

tag = subprocess.check_output(['git', 'describe', '--tags', '--exact-match'], text=True).strip()
commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
# .txt: <out-dir> is on the include path and libc++ has a <version>.
with open(os.path.join(out_dir, 'VERSION.txt'), 'w') as f:
    f.write('%s %s\nextensions: %s\njemalloc: linux only\n' % (tag, commit, ' '.join(EXTENSIONS)))

digest = hashlib.sha256()
for name in sorted(os.listdir(out_dir)):
    digest.update(name.encode() + b'\0')
    with open(os.path.join(out_dir, name), 'rb') as f:
        digest.update(f.read())
    digest.update(b'\0')
with open(os.path.join(module_dir, 'upstream_stamp.h'), 'w') as f:
    f.write('// Generated by gen_duckdbsrc.py; do not edit.\n')
    f.write('#define DUCKDBSRC_UPSTREAM "%s %s %s"\n' % (tag, commit, digest.hexdigest()))
