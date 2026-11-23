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

from kubernetes import client
from q8s.plugins.cpu_job import CPUJobTemplatePlugin
from q8s.workload import Workload


class TestCPUJobTemplatePlugin(unittest.TestCase):

    def test_makejob_invalid_target(self):
        plugin = CPUJobTemplatePlugin()
        name = "test-job"
        registry_pat = None
        registry_credentials_secret_name = "test-secret"
        container_image = "test-image"
        env = [client.V1EnvVar(name="TEST_ENV", value="value")]
        workload = Workload.from_code("print(42)")
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
