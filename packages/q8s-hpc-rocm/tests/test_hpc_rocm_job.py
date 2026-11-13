import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from kubernetes import client

from q8s_hpc_rocm.hpc_rocm_job import (
    HpcRocmJobTemplatePlugin,
    _parse_config_line,
    load_hpc_config,
    resolve_hpc_config_path,
)


class TestParseConfigLine(unittest.TestCase):
    def test_flag_with_space_separated_value(self):
        self.assertEqual(
            _parse_config_line("--time 01:00:00", 1), ("--time", "01:00:00")
        )

    def test_flag_with_equals_value(self):
        self.assertEqual(
            _parse_config_line("--time=01:00:00", 1), ("--time", "01:00:00")
        )

    def test_blank_line_is_ignored(self):
        self.assertIsNone(_parse_config_line("   ", 1))

    def test_comment_line_is_ignored(self):
        self.assertIsNone(_parse_config_line("# a comment", 1))

    def test_missing_double_dash_raises(self):
        with self.assertRaises(ValueError):
            _parse_config_line("time 01:00:00", 1)

    def test_mixing_equals_with_extra_tokens_raises(self):
        with self.assertRaises(ValueError):
            _parse_config_line("--time=01:00:00 extra", 1)

    def test_missing_value_raises(self):
        with self.assertRaises(ValueError):
            _parse_config_line("--time", 1)

    def test_too_many_tokens_raises(self):
        with self.assertRaises(ValueError):
            _parse_config_line("--time 01:00:00 extra", 1)

    def test_empty_value_after_equals_raises(self):
        with self.assertRaises(ValueError):
            _parse_config_line("--time=", 1)


class TestResolveHpcConfigPath(unittest.TestCase):
    def test_explicit_path_from_workload_extra(self):
        workload = MagicMock()
        workload.extra = {"hpc_config": "~/configs/HpcConfig"}

        result = resolve_hpc_config_path(workload)

        self.assertEqual(result, Path("~/configs/HpcConfig").expanduser().resolve())

    def test_falls_back_to_project_root_when_no_explicit_path(self):
        workload = MagicMock()
        workload.extra = {}

        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir).resolve()
            (project_root / "Q8Sproject").write_text("")

            nested = project_root / "nested" / "deeper"
            nested.mkdir(parents=True)

            cwd = os.getcwd()
            os.chdir(nested)
            try:
                result = resolve_hpc_config_path(workload)
            finally:
                os.chdir(cwd)

            self.assertEqual(result, project_root / "HpcConfig")


class TestLoadHpcConfig(unittest.TestCase):
    def _workload_with_config(self, contents: str):
        tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_dir.cleanup)

        config_path = Path(tmp_dir.name) / "HpcConfig"
        config_path.write_text(contents)

        workload = MagicMock()
        workload.extra = {"hpc_config": str(config_path)}
        return workload

    def test_parses_q8s_node_and_slurm_flags(self):
        workload = self._workload_with_config(
            "\n".join(
                [
                    "# comment",
                    "",
                    "--q8s-node lumi-node-1",
                    "--account=project_123",
                    "--time 01:00:00",
                ]
            )
        )

        result = load_hpc_config(workload)

        self.assertEqual(result["q8s_node"], "lumi-node-1")
        self.assertEqual(
            result["slurm_flags"],
            ["--account=project_123", "--time=01:00:00"],
        )

    def test_missing_file_raises(self):
        workload = MagicMock()
        workload.extra = {"hpc_config": "/nonexistent/path/HpcConfig"}

        with self.assertRaises(FileNotFoundError):
            load_hpc_config(workload)

    def test_missing_q8s_node_raises(self):
        workload = self._workload_with_config("--account=project_123\n")

        with self.assertRaises(ValueError):
            load_hpc_config(workload)


class TestHpcRocmJobTemplatePlugin(unittest.TestCase):

    @patch("q8s_hpc_rocm.hpc_rocm_job.load_hpc_config")
    @patch("q8s_hpc_rocm.hpc_rocm_job.client.V1Container")
    @patch("q8s_hpc_rocm.hpc_rocm_job.client.V1PodTemplateSpec")
    @patch("q8s_hpc_rocm.hpc_rocm_job.client.V1PodSpec")
    @patch("q8s_hpc_rocm.hpc_rocm_job.client.V1ObjectMeta")
    @patch("q8s_hpc_rocm.hpc_rocm_job.client.V1VolumeMount")
    @patch("q8s_hpc_rocm.hpc_rocm_job.client.V1Volume")
    @patch("q8s_hpc_rocm.hpc_rocm_job.client.V1ConfigMapVolumeSource")
    @patch("q8s_hpc_rocm.hpc_rocm_job.client.V1LocalObjectReference")
    def test_makejob_hpc_rocm(
        self,
        mock_v1_local_object_reference,
        mock_v1_config_map_volume_source,
        mock_v1_volume,
        mock_v1_volume_mount,
        mock_v1_object_meta,
        mock_v1_pod_spec,
        mock_v1_pod_template_spec,
        mock_v1_container,
        mock_load_hpc_config,
    ):
        mock_load_hpc_config.return_value = {
            "path": "/tmp/HpcConfig",
            "q8s_node": "lumi-rocm-node-1",
            "slurm_flags": ["--account=project_123", "--time=01:00:00"],
        }

        plugin = HpcRocmJobTemplatePlugin()
        name = "test-job"
        registry_pat = "test-pat"
        registry_credentials_secret_name = "test-secret"
        container_image = "test-image"

        env = [client.V1EnvVar(name="TEST_ENV", value="value")]

        workload = MagicMock()
        workload.is_src_project = False
        workload.entry_module = "module"
        workload.entry_script = "script.py"
        workload.args = []
        workload.mappings = {"main.py": "main.py"}

        target = "hpc-rocm"

        result = plugin.makejob(
            name,
            registry_pat,
            registry_credentials_secret_name,
            container_image,
            workload,
            env,
            target,
        )

        self.assertIsNotNone(result)
        mock_load_hpc_config.assert_called_once_with(workload)
        mock_v1_container.assert_called_once()
        mock_v1_pod_template_spec.assert_called_once()
        mock_v1_pod_spec.assert_called_once()
        mock_v1_object_meta.assert_called_once()
        mock_v1_volume_mount.assert_called_once()
        mock_v1_volume.assert_called_once()
        mock_v1_config_map_volume_source.assert_called_once()
        mock_v1_local_object_reference.assert_called_once()

        _, pod_spec_kwargs = mock_v1_pod_spec.call_args
        self.assertEqual(
            pod_spec_kwargs["node_selector"],
            {"kubernetes.io/hostname": "lumi-rocm-node-1"},
        )

        _, object_meta_kwargs = mock_v1_object_meta.call_args
        self.assertEqual(
            object_meta_kwargs["annotations"],
            {"slurm-job.vk.io/flags": "--account=project_123 --time=01:00:00"},
        )

    def test_makejob_invalid_target(self):
        plugin = HpcRocmJobTemplatePlugin()
        name = "test-job"
        registry_pat = None
        registry_credentials_secret_name = "test-secret"
        container_image = "test-image"
        env = [client.V1EnvVar(name="TEST_ENV", value="value")]
        workload = MagicMock()
        target = "invalid-target"

        result = plugin.makejob(
            name,
            registry_pat,
            registry_credentials_secret_name,
            container_image,
            workload,
            env,
            target,
        )

        self.assertIsNone(result)

    def test_get_base_image(self):
        plugin = HpcRocmJobTemplatePlugin()

        self.assertEqual(
            plugin.get_base_image("3.12"), "aapopeiponen/qiskit-lumi-rocm-singlenode"
        )


if __name__ == "__main__":
    unittest.main()
