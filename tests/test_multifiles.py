import shutil
import tempfile
import textwrap
import unittest
from pathlib import Path

from q8s.multifiles import _iter_imports


def write(tmpdir: Path, rel: str, content: str) -> Path:
    p = tmpdir / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


class TestIterImports(unittest.TestCase):
    def setUp(self):
        self._tmpdir = Path(tempfile.mkdtemp(prefix="iter_imports_"))

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_simple_imports(self):
        py = write(
            self._tmpdir,
            "simple.py",
            """
            import os, sys
            import pkg.sub
        """,
        )
        got = list(_iter_imports(py))
        self.assertIn(("os", 0, None), got)
        self.assertIn(("sys", 0, None), got)
        self.assertIn(("pkg.sub", 0, None), got)
        self.assertEqual(len(got), 3)

    def test_from_imports_absolute(self):
        py = write(
            self._tmpdir,
            "from_abs.py",
            """
            from collections import abc
            from pkg import mod
            from pkg.subpkg import mod1, mod2 as m2
        """,
        )
        got = list(_iter_imports(py))
        self.assertIn(("collections", 0, None), got)
        self.assertIn(("pkg", 0, None), got)
        self.assertIn(("pkg.subpkg", 0, None), got)
        self.assertEqual(len(got), 3)

    def test_relative_imports_l1_mod(self):
        # https://docs.python.org/3/reference/import.html#package-relative-imports
        py = write(
            self._tmpdir,
            "pkg/subpkg1/modX.py",
            """
            from . import modY
        """,
        )
        got = list(_iter_imports(py, cur_pkg="pkg.subpkg1"))
        self.assertIn(("pkg.subpkg1.modY", 0, None), got)
        self.assertEqual(len(got), 1)

    def test_relative_imports_l1_mod_func(self):
        # https://docs.python.org/3/reference/import.html#package-relative-imports
        py = write(
            self._tmpdir,
            "pkg/subpkg1/modX.py",
            """
            from .modY import spam, ham
        """,
        )
        got = list(_iter_imports(py, cur_pkg="pkg.subpkg1"))
        self.assertIn(("pkg.subpkg1.modY", 0, None), got)
        self.assertIn(("pkg.subpkg1.modY.spam", 0, None), got)
        self.assertIn(("pkg.subpkg1.modY.ham", 0, None), got)
        self.assertEqual(len(got), 3)

    def test_relative_imports_l2_mod(self):
        # https://docs.python.org/3/reference/import.html#package-relative-imports
        py = write(
            self._tmpdir,
            "pkg/subpkg2/__init__.py",
            """
            from ..subpkg1 import modY
        """,
        )
        got = list(_iter_imports(py, cur_pkg="pkg.subpkg2"))
        self.assertIn(("pkg.subpkg1.modY", 0, None), got)
        self.assertEqual(len(got), 1)

    def test_relative_imports_l2_mod_funct(self):
        # https://docs.python.org/3/reference/import.html#package-relative-imports
        py = write(
            self._tmpdir,
            "pkg/subpkg2/__init__.py",
            """
            from ..subpkg1.modY import spam
        """,
        )
        got = list(_iter_imports(py, cur_pkg="pkg.subpkg2"))
        self.assertIn(("pkg.subpkg1.modY", 0, None), got)
        self.assertIn(("pkg.subpkg1.modY.spam", 0, None), got)
        self.assertEqual(len(got), 2)

    def test_ignores_comments_and_strings(self):
        py = write(
            self._tmpdir,
            "noise.py",
            r"""
            # import json
            s = "from math import sqrt"
            t = """
            + '"""import re"""'
            + r"""
            import os  # a real import
        """,
        )
        got = list(_iter_imports(py))
        self.assertIn(("os", 0, None), got)
        self.assertEqual(len(got), 1)

    def test_syntax_error_returns_nothing(self):
        py = write(
            self._tmpdir,
            "bad.py",
            """
            def oops(:
                pass
        """,
        )
        got = list(_iter_imports(py))
        self.assertEqual(got, [])

    def test_empty_file(self):
        py = write(self._tmpdir, "empty.py", "")
        got = list(_iter_imports(py))
        self.assertEqual(got, [])


if __name__ == "__main__":
    unittest.main()
