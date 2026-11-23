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

import os
import re
from importlib.metadata import version

from kubernetes import client
from q8s.constants import WORKSPACE
from q8s.plugins.job import JobPlugin
from q8s.plugins.job_template_spec import hookimpl
from q8s.workload import Workload

_PYTHON_VERSION_RE = re.compile(r"^3(\.\d+){1,2}$")

MEMORY = os.environ.get("MEMORY", "32Gi")


class CUDAJobTemplatePlugin(JobPlugin):
    target_name = "gpu"

    """
    This plugin is used to create a job template for a GPU job.
    """

    def get_base_image(self, python_version: str) -> str:
        if not _PYTHON_VERSION_RE.fullmatch(python_version):
            raise ValueError(f"Invalid python_version format: {python_version!r}")

        return f"ghcr.io/qubernetes-dev/cuda:12.8.1-r2-py{python_version}"

    @hookimpl
    def makejob(
        self,
        name: str,
        registry_pat: str | None,
        registry_credentials_secret_name: str,
        container_image: str,
        workload: Workload,
        env: list[client.V1EnvVar],
        target: str,
    ) -> client.V1PodTemplateSpec:

        if target != self.target_name:
            return None

        env_var = list(env)
        if workload.is_src_project:
            env_var.append(client.V1EnvVar(name="PYTHONPATH", value=f"{WORKSPACE}/src"))

        env_var.append(
            client.V1EnvVar(
                name="Q8S_VERSION",
                value=version("q8s"),
            )
        )

        env_var.append(
            client.V1EnvVar(
                name="Q8S_PLUGIN_VERSION",
                value=version("q8s-cuda"),
            )
        )

        self.patch_environment_with_git_info(env_var)

        return self.build_workload_pod_template(
            workload,
            name=name,
            image=container_image,
            env=env_var,
            image_pull_secret_name=(
                registry_credentials_secret_name if registry_pat else None
            ),
            resources=client.V1ResourceRequirements(
                limits={
                    "cpu": "2",
                    "ephemeral-storage": "50Gi",
                    "memory": MEMORY,
                    "nvidia.com/gpu": "1",
                },
                requests={
                    "cpu": "2",
                    "ephemeral-storage": "0",
                    "memory": MEMORY,
                    "nvidia.com/gpu": "1",
                },
            ),
            runtime_class_name="nvidia",
        )
