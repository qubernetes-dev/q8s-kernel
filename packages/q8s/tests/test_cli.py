# Copyright 2024-2026 Qubernetes
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from q8s.cli import app
from typer.testing import CliRunner


class TestExecute(unittest.TestCase):
    def setUp(self):
        project_patch = patch("q8s.cli.Project")
        self.project = project_patch.start().return_value
        self.addCleanup(project_patch.stop)
        self.project.configuration.targets = {"cpu": {}, "gpu": {}}
        self.project.kubeconfig = Mock(spec=Path)
        self.project.kubeconfig.exists.return_value = True
        self.project.kubeconfig.as_posix.return_value = "test-kubeconfig"
        self.project.cached_images.return_value = "cached-image"

        context_patch = patch("q8s.cli.K8sContext")
        self.context_class = context_patch.start()
        self.addCleanup(context_patch.stop)
        self.context = self.context_class.return_value
        self.context.available_targets.return_value = ["cpu", "gpu"]
        self.context.execute_workload.return_value = ("completed", "stdout")

        workload_patch = patch("q8s.cli.Workload")
        self.workload_class = workload_patch.start()
        self.addCleanup(workload_patch.stop)

    def invoke(self, *args):
        return CliRunner().invoke(
            app,
            ["execute", "example.py", *args],
            env={"KUBECONFIG": None, "REGISTRY_PAT": None},
        )

    def assert_project_rejection(self, result, target):
        available = ", ".join(self.project.configuration.targets)
        self.assertEqual(result.exit_code, 1, result.output)
        self.assertEqual(
            result.output,
            f"Target '{target}' not found in Q8Sproject. "
            f"Configured targets: {available}\n",
        )
        self.project.kubeconfig.exists.assert_not_called()
        self.project.kubeconfig.as_posix.assert_not_called()
        self.project.cached_images.assert_not_called()
        self.context_class.assert_not_called()
        self.workload_class.from_entry_script.assert_not_called()
        self.context.execute_workload.assert_not_called()

    def test_rejects_unconfigured_target_even_with_plugin(self):
        self.context.available_targets.return_value.append("other")

        self.assert_project_rejection(self.invoke("--target", "other"), "other")

    def test_rejects_unconfigured_target_with_stale_cached_image(self):
        self.project.cached_images.return_value = "cached-other-image"

        self.assert_project_rejection(self.invoke("--target", "other"), "other")

    def test_rejects_unconfigured_target_with_explicit_image(self):
        result = self.invoke("--target", "other", "--image", "custom-other-image")

        self.assert_project_rejection(result, "other")

    def test_rejects_unconfigured_target_before_kubeconfig_validation(self):
        self.project.kubeconfig.exists.return_value = False

        self.assert_project_rejection(self.invoke("--target", "other"), "other")

    def test_rejects_configured_target_without_plugin(self):
        self.context.available_targets.return_value = ["cpu"]

        result = self.invoke("--target", "gpu")

        self.assertEqual(result.exit_code, 1, result.output)
        self.assertIn("Invalid target 'gpu'. Available: ['cpu']", result.output)
        self.project.cached_images.assert_not_called()
        self.context.set_container_image.assert_not_called()
        self.workload_class.from_entry_script.assert_not_called()
        self.context.execute_workload.assert_not_called()

    def assert_execution(self, result, target, image):
        self.assertEqual(result.exit_code, 0, result.output)
        self.context.set_target.assert_called_once_with(target)
        self.context.set_container_image.assert_called_once_with(image)
        self.workload_class.from_entry_script.assert_called_once_with(
            entry_script=Path("example.py")
        )
        self.context.execute_workload.assert_called_once_with(
            workload=self.workload_class.from_entry_script.return_value,
            submit=False,
        )

    def test_executes_configured_cpu(self):
        result = self.invoke("--target", "cpu")

        self.assert_execution(result, "cpu", "cached-image")
        self.project.cached_images.assert_called_once_with("cpu")

    def test_executes_configured_gpu(self):
        result = self.invoke("--target", "gpu")

        self.assert_execution(result, "gpu", "cached-image")
        self.project.cached_images.assert_called_once_with("gpu")

    def test_executes_default_cpu(self):
        result = self.invoke()

        self.assert_execution(result, "cpu", "cached-image")
        self.project.cached_images.assert_called_once_with("cpu")

    def test_executes_configured_target_with_explicit_image(self):
        result = self.invoke("--target", "gpu", "--image", "custom-gpu-image")

        self.assert_execution(result, "gpu", "custom-gpu-image")
        self.project.cached_images.assert_not_called()

    def test_rejects_unconfigured_default_cpu(self):
        self.project.configuration.targets = {"gpu": {}}

        self.assert_project_rejection(self.invoke(), "cpu")

    def test_rejects_target_with_empty_configuration(self):
        self.project.configuration.targets = {}

        self.assert_project_rejection(self.invoke("--target", "other"), "other")

    def test_target_names_require_exact_match(self):
        for target in ("CPU", "gpu1"):
            with self.subTest(target=target):
                self.assert_project_rejection(self.invoke("--target", target), target)
