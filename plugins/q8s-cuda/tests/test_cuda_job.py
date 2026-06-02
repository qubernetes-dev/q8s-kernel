import unittest
from unittest.mock import MagicMock, patch

from kubernetes import client

from q8s_cuda.cuda_job import CUDAJobTemplatePlugin


class TestCUDAJobTemplatePlugin(unittest.TestCase):

    @patch("q8s_cuda.cuda_job.client.V1Container")
    @patch("q8s.plugins.job_template_spec.client.V1PodTemplateSpec")
    @patch("q8s.plugins.job_template_spec.client.V1PodSpec")
    @patch("q8s.plugins.job_template_spec.client.V1ObjectMeta")
    @patch("q8s.plugins.job_template_spec.client.V1VolumeMount")
    @patch("q8s.plugins.job_template_spec.client.V1Volume")
    @patch("q8s.plugins.job_template_spec.client.V1ConfigMapVolumeSource")
    @patch("q8s.plugins.job_template_spec.client.V1LocalObjectReference")
    @patch("q8s.plugins.job_template_spec.client.V1ResourceRequirements")

    def test_makejob_gpu(
        self,
        mock_v1_resource_requirements,
        mock_v1_local_object_reference,
        mock_v1_config_map_volume_source,
        mock_v1_volume,
        mock_v1_volume_mount,
        mock_v1_object_meta,
        mock_v1_pod_spec,
        mock_v1_pod_template_spec,
        mock_v1_container,
    ):
        plugin = CUDAJobTemplatePlugin()
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

        target = "gpu"

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
        mock_v1_local_object_reference.assert_called_once()
        mock_v1_resource_requirements.assert_called_once()

    def test_get_base_image_default(self):
        plugin = CUDAJobTemplatePlugin()

        self.assertEqual(
            plugin.get_base_image("3.12"),
            "ghcr.io/qubernetes-dev/cuda:12.8.1-r2-py3.12",
        )

    def test_get_base_image_custom_version(self):
        plugin = CUDAJobTemplatePlugin()

        self.assertEqual(
            plugin.get_base_image("3.11"),
            "ghcr.io/qubernetes-dev/cuda:12.8.1-r2-py3.11",
        )

    def test_get_base_image_invalid_version_raises(self):
        plugin = CUDAJobTemplatePlugin()

        with self.assertRaises(ValueError):
            plugin.get_base_image("invalid")

if __name__ == "__main__":
    unittest.main()