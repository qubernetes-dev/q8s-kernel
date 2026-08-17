import unittest
from unittest.mock import MagicMock, patch

from kubernetes import client
from q8s.plugins.cpu_job import CPUJobTemplatePlugin


class TestCPUJobTemplatePlugin(unittest.TestCase):

    @patch("q8s.plugins.cpu_job.client.V1Container")
    @patch("q8s.plugins.cpu_job.client.V1PodTemplateSpec")
    @patch("q8s.plugins.cpu_job.client.V1PodSpec")
    @patch("q8s.plugins.cpu_job.client.V1ObjectMeta")
    @patch("q8s.plugins.cpu_job.client.V1VolumeMount")
    @patch("q8s.plugins.cpu_job.client.V1Volume")
    @patch("q8s.plugins.cpu_job.client.V1ConfigMapVolumeSource")
    def test_makejob_cpu(
        self,
        mock_v1_config_map_volume_source,
        mock_v1_volume,
        mock_v1_volume_mount,
        mock_v1_object_meta,
        mock_v1_pod_spec,
        mock_v1_pod_template_spec,
        mock_v1_container,
    ):
        plugin = CPUJobTemplatePlugin()
        name = "test-job"
        registry_pat = None
        registry_credentials_secret_name = "test-secret"
        container_image = "test-image"
        env = [client.V1EnvVar(name="TEST_ENV", value="value")]
        workload = MagicMock()
        workload.is_src_project = False
        workload.entry_module = "module"
        workload.entry_script = "script.py"
        workload.args = []
        workload.mappings = {"main.py": "main.py"}
        target = "cpu"

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
        mock_v1_container.assert_called_once()
        mock_v1_pod_template_spec.assert_called_once()
        mock_v1_pod_spec.assert_called_once()
        mock_v1_object_meta.assert_called_once()
        mock_v1_volume_mount.assert_called_once()
        mock_v1_volume.assert_called_once()
        mock_v1_config_map_volume_source.assert_called_once()

    def test_makejob_invalid_target(self):
        plugin = CPUJobTemplatePlugin()
        name = "test-job"
        registry_pat = None
        registry_credentials_secret_name = "test-secret"
        container_image = "test-image"
        env = [client.V1EnvVar(name="TEST_ENV", value="value")]
        workload = MagicMock()
        workload.is_src_project = False
        workload.entry_module = "module"
        workload.entry_script = "script.py"
        workload.args = []
        workload.mappings = {"main.py": "main.py"}
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

    def test_get_base_image_default(self):
        plugin = CPUJobTemplatePlugin()

        self.assertEqual(
            plugin.get_base_image("3.12"),
            "python:3.12-slim",
        )

    def test_get_base_image_custom_version(self):
        plugin = CPUJobTemplatePlugin()

        self.assertEqual(
            plugin.get_base_image("3.11"),
            "python:3.11-slim",
        )

    def test_get_base_image_invalid_version_raises(self):
        plugin = CPUJobTemplatePlugin()

        with self.assertRaises(ValueError):
            plugin.get_base_image("invalid")


if __name__ == "__main__":
    unittest.main()
