import os
import shutil
import tempfile
import unittest
from pathlib import Path

from q8s.workload import Workload
from tests.utils import write


class TestWorkloadSrcLayoutDetection(unittest.TestCase):
    def setUp(self):
        self._tmpdir = Path(tempfile.mkdtemp(prefix="workload_src_layout_"))
        self._old_cwd = os.getcwd()
        os.chdir(self._tmpdir)

    def tearDown(self):
        os.chdir(self._old_cwd)
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_src_layout_detected_from_config_cfg(self):
        # Make this directory look like a project root
        (self._tmpdir / "setup.cfg").write_text("", encoding="utf-8")
        write(
            self._tmpdir,
            "config.cfg",
            """
            [options.packages.find]
            where = src
            """,
        )

        entry_script = write(self._tmpdir, "src/pkg/main.py", "print('hello')\n")

        workload = Workload.from_entry_script(entry_script)

        self.assertTrue(workload.is_src_project)

    def test_src_layout_detected_from_pyproject_toml(self):
        write(
            self._tmpdir,
            "pyproject.toml",
            """
            [tool.setuptools.packages.find]
            where = ["src"]
            """,
        )

        entry_script = write(self._tmpdir, "src/pkg/main.py", "print('hello')\n")

        workload = Workload.from_entry_script(entry_script)

        self.assertTrue(workload.is_src_project)

    def test_non_src_layout_when_no_project_files(self):
        entry_script = write(self._tmpdir, "main.py", "print('hello')\n")

        workload = Workload.from_entry_script(entry_script)

        self.assertFalse(workload.is_src_project)
        self.assertEqual(workload.entry_script, "main.py")


if __name__ == "__main__":
    unittest.main()
