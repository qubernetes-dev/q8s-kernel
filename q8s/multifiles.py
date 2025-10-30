import ast
import importlib.util
import os
import sys
from pathlib import Path

GLOBAL = getattr(sys, "base_prefix", sys.prefix)
LOCAL = sys.prefix


def _resolve_spec(modname: str, package: str | None = None):
    try:
        return importlib.util.find_spec(modname, package=package)
    except Exception:
        return None


def _spec_origin_files(spec):
    """Yield file paths for a spec (module file, or package __init__ if present)."""
    if not spec:
        return
    if spec.origin and spec.origin != "namespace":
        yield spec.origin
    # If it's a package (including namespace), try its __init__.py if present
    if spec.submodule_search_locations:
        for loc in spec.submodule_search_locations:
            init_py = os.path.join(loc, "__init__.py")
            if os.path.isfile(init_py):
                yield init_py


def _iter_imports(pyfile: str, cur_pkg: str | None = None):
    """Parse a file and yield (module, level, from_module) entries."""
    try:
        src = Path(pyfile).read_text(encoding="utf-8")
    except Exception:
        return
    try:
        tree = ast.parse(src, filename=str(pyfile))
    except SyntaxError:
        return
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, 0, None
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                yield node.module or "", node.level, None

            elif node.level == 1:
                # from .module import ...
                if node.module:
                    yield f"{cur_pkg}.{node.module}", 0, None

                    for name in [alias.name for alias in node.names]:
                        yield f"{cur_pkg}.{node.module}.{name}", 0, None
                # from . import ...
                else:
                    for name in [alias.name for alias in node.names]:
                        yield f"{cur_pkg}.{name}", 0, None

            elif node.level > 1:
                # from ..module import ...
                if node.module:
                    parent_pkg = ".".join(cur_pkg.split(".")[: -(node.level - 1)])
                    if "." in node.module:
                        yield f"{parent_pkg}.{node.module}", 0, None

                    for name in [alias.name for alias in node.names]:
                        yield f"{parent_pkg}.{node.module}.{name}", 0, None


def _qualname(base_pkg, module, level):
    """Resolve 'from ..foo import bar' style relative imports against base_pkg."""
    if level == 0:
        return module
    if not base_pkg:
        return None
    parts = base_pkg.split(".")
    if level > len(parts):
        return module  # cannot resolve further; best effort
    prefix = ".".join(parts[: len(parts) - level])
    return f"{prefix}.{module}" if module else prefix


def pkg_name_for_file(fpath):
    """
    Map module file -> containing package name (best effort)
    """
    fpath = os.path.abspath(fpath)
    # Walk up until a non-package dir (missing __init__.py) to compute dotted pkg
    parts = []
    cur = os.path.dirname(fpath)
    while True:
        if os.path.isfile(os.path.join(cur, "__init__.py")):
            parts.append(os.path.basename(cur))
            cur = os.path.dirname(cur)
        else:
            break
    return ".".join(reversed(parts)) if parts else None


def collect_imported_files(
    entry_script: str, restrict_to_top_package: str | None = None
):
    """
    Return a set of file paths transitively imported by entry_script.
    If restrict_to_top_package is given (e.g., 'numpy'), only files under that package are returned.
    """
    files = set()
    visited_modules = set()
    to_process = []

    # Seed with the entry script
    entry_script = os.path.abspath(entry_script)
    files.add(entry_script)

    # Determine restriction roots (paths) if filtering to a specific top-level package
    restrict_roots = None
    if restrict_to_top_package:
        top_spec = _resolve_spec(restrict_to_top_package)
        if top_spec and top_spec.submodule_search_locations:
            restrict_roots = {
                os.path.abspath(p) for p in top_spec.submodule_search_locations
            }

    # Start by parsing the entry script
    to_process.append((entry_script, pkg_name_for_file(entry_script)))

    while to_process:
        cur_file, cur_pkg = to_process.pop()
        for mod, level, _ in _iter_imports(cur_file, cur_pkg):
            target = _qualname(cur_pkg, mod, level)
            if not target:
                continue

            # Explore the resolved module/package
            spec = _resolve_spec(target)
            if not spec:
                continue

            # Avoid re-visiting same resolved module
            key = (
                spec.name or target,
                spec.origin,
                tuple(spec.submodule_search_locations or []),
            )
            if key in visited_modules:
                continue
            visited_modules.add(key)

            for origin in _spec_origin_files(spec):
                origin = os.path.abspath(origin)
                if not os.path.exists(origin):
                    continue
                # Apply optional package restriction
                if restrict_roots:
                    # keep if origin is under any of the top package roots
                    if not any(
                        os.path.commonpath([origin, root]) == root
                        for root in restrict_roots
                    ):
                        continue
                if (
                    origin not in files
                    # exclude global interpreter packages
                    and origin.startswith(GLOBAL) is False
                    # exclude venv packages
                    and origin.startswith(LOCAL) is False
                ):
                    files.add(origin)
                    to_process.append(
                        (
                            origin,
                            (
                                spec.name
                                if spec.submodule_search_locations
                                else pkg_name_for_file(origin)
                            ),
                        )
                    )

    return files
