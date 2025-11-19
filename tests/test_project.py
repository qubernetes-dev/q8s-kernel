import unittest
from io import StringIO
from os import remove
from os.path import exists, join
from unittest.mock import Mock

from rich.progress import Progress, SpinnerColumn

from q8s.project import Project

mocked_configuration = {
    "name": "Example",
    "python_env": {"dependencies": ["qiskit==1.1.0"]},
    "targets": {
        "cpu": {"python_env": {"dependencies": ["qiskit-aer==0.15.1"]}},
        "gpu": {"python_env": {"dependencies": ["qiskit-aer-gpu==0.15.1"]}},
    },
    "docker": {"username": "vstirbu", "registry": None},
    "kubeconfig": "tests/fixtures/cache/kubeconfig",
}


def _completed_process():
    process = Mock()
    process.stdout = StringIO("")
    process.stderr = None
    process.returncode = 0
    process.wait.return_value = 0
    return process


class TestProject(unittest.TestCase):
    def before(self):
        pass

    def after(self):
        remove("tests/fixtures/cache/.q8s_cache/cpu/requirements.txt", missing_ok=True)

    @unittest.mock.patch("q8s.project.load")
    def test_init(self, mock_load: Mock):
        mock_load.return_value = mocked_configuration

        # TODO: mock reading configuration file
        project = Project("tests/fixtures/cache")

        self.assertEqual(project.name, "Example")
        self.assertIsNotNone(project.configuration.python_env)
        self.assertEqual(project.configuration.targets.keys(), ["cpu", "gpu"])

    @unittest.mock.patch("q8s.project.load")
    def test_init_cache(self, mock_load: Mock):
        mock_load.return_value = mocked_configuration

        project_path = "tests/fixtures/cache"
        project = Project(project_path)

        self.assertFalse(exists(join(project_path, ".q8s_cache/cpu/requirements.txt")))
        self.assertFalse(exists(join(project_path, ".q8s_cache/gpu/requirements.txt")))

        project.init_cache()

        self.assertTrue(exists(join(project_path, ".q8s_cache/cpu/requirements.txt")))
        self.assertTrue(exists(join(project_path, ".q8s_cache/gpu/requirements.txt")))

    @unittest.mock.patch("q8s.project.load")
    def test_clear_cache(self, mock_load: Mock):
        mock_load.return_value = mocked_configuration

        project_path = "tests/fixtures/cache"
        project = Project(project_path)

        project.init_cache()

        self.assertTrue(exists(join(project_path, ".q8s_cache/cpu/requirements.txt")))
        self.assertTrue(exists(join(project_path, ".q8s_cache/gpu/requirements.txt")))

        project.clear_cache()

        self.assertFalse(exists(join(project_path, ".q8s_cache/cpu/requirements.txt")))
        self.assertFalse(exists(join(project_path, ".q8s_cache/gpu/requirements.txt")))

    @unittest.mock.patch("q8s.project.load")
    def test_check_cache(self, mock_load: Mock):
        mock_load.return_value = mocked_configuration

        project_path = "tests/fixtures/cache"
        project = Project(project_path)

        project.init_cache()

        with open(join(project_path, ".q8s_cache/cpu/requirements.txt"), "a") as f:
            f.write("qiskit==1.0.0")

        self.assertFalse(project.check_cache())

        project.clear_cache()

    @unittest.mock.patch("q8s.project.sys.platform", "win32")
    @unittest.mock.patch("q8s.project.Popen")
    @unittest.mock.patch("q8s.project.load")
    def test_build_container(self, mock_load: Mock, mock_popen: Mock):
        mock_load.return_value = mocked_configuration

        project_path = "tests/fixtures/cache"
        project = Project(project_path)

        project.init_cache()

        mock_process = _completed_process()
        mock_popen.return_value = mock_process

        with Progress(SpinnerColumn()) as progress:
            project.build_container(
                target="cpu", progress=progress, silent=True, push=False
            )

        mock_popen.assert_called_once()
        self.assertEqual(
            mock_popen.call_args.args[0],
            [
                "docker",
                "build",
                "--progress",
                "plain",
                "--platform",
                "linux/amd64",
                "--tag",
                "vstirbu/q8s-example:cpu",
                join(project_path, ".q8s_cache", "cpu"),
            ],
        )

    @unittest.mock.patch("q8s.project.sys.platform", "win32")
    @unittest.mock.patch("q8s.project.Popen")
    @unittest.mock.patch("q8s.project.load")
    def test_push_container(self, mock_load: Mock, mock_popen: Mock):
        mock_load.return_value = mocked_configuration

        project_path = "tests/fixtures/cache"
        project = Project(project_path)

        project.init_cache()

        mock_build_process = _completed_process()
        mock_push_process = _completed_process()
        mock_popen.side_effect = [mock_build_process, mock_push_process]

        with Progress(SpinnerColumn()) as progress:
            project.build_container(
                target="cpu", progress=progress, silent=True, push=False
            )
            project.push_container(target="cpu", progress=progress, silent=True)

        self.assertEqual(mock_popen.call_count, 2)
        self.assertEqual(
            mock_popen.call_args_list[1].args[0],
            ["docker", "push", "vstirbu/q8s-example:cpu"],
        )
