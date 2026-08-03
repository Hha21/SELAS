"""
Environment workarounds applied at import time.

Imported for its side effects by src.config, so every entry point (scripts,
server, notebooks) picks it up without having to remember to call anything.
"""

import logging
import os
import shutil
import sysconfig
from pathlib import Path

log = logging.getLogger(__name__)


def _can_build_triton_shim() -> tuple[bool, str]:
    """Can triton JIT-compile its CPython extension shim on this machine?

    It shells out to a C compiler with `-I<python include dir>` and
    `#include <Python.h>`, so it needs *both* a compiler and the Python
    development headers. Having gcc alone is not enough -- that combination
    fails at link/compile time rather than at the "find compiler" check,
    which is a much less obvious error.
    """
    if not any(shutil.which(c) for c in ("cc", "gcc", "clang")):
        return False, "no C compiler (install build-essential)"

    include = sysconfig.get_paths().get("include")
    if not include or not Path(include, "Python.h").exists():
        version = sysconfig.get_python_version()
        return False, f"missing Python headers (install python{version}-dev)"

    return True, ""


def disable_triton_ops_without_compiler() -> bool:
    """Route torch's triton-backed native ops back to eager when triton cannot build.

    torch >= 2.13 dispatches some plain aten ops (e.g. the batched outer product
    inside RoPE) to triton kernels. Triton JIT-compiles a small C driver shim on
    first use, so on a box that cannot compile it *every* forward pass dies --
    long after model loading has appeared to succeed.

    Installing the missing toolchain is the real fix; this only keeps the
    pipeline usable meanwhile. Set NLA_KEEP_TRITON=1 to skip the workaround.

    Returns True if the workaround was applied.
    """
    if os.getenv("NLA_KEEP_TRITON"):
        return False

    ok, reason = _can_build_triton_shim()
    if ok:
        return False

    try:
        from torch._native.registry import deregister_op_overrides
    except ImportError:
        return False   # older torch without the native-op registry -- nothing to do

    deregister_op_overrides(disable_dsl_names="triton")
    log.warning(
        "Triton cannot JIT-compile here (%s); disabled torch's triton op "
        "overrides so forward passes fall back to eager.", reason
    )
    return True
