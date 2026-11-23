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

from kubernetes import client
from q8s.constants import WORKSPACE
from q8s.plugins.job import JobPlugin
from q8s.plugins.job_template_spec import hookimpl


class LabCpuAdapter(JobPlugin):
    target_name = "lab-cpu"

    def get_base_image(self, python_version):
        return f"python:{python_version}-slim"

    @hookimpl
    def makejob(
        self,
        name,
        registry_pat,
        registry_credentials_secret_name,
        container_image,
        workload,
        env,
        target,
    ):
        if target != self.target_name:
            return None

        workload_env = list(env)
        if workload.is_src_project:
            workload_env.append(
                client.V1EnvVar(name="PYTHONPATH", value=f"{WORKSPACE}/src")
            )

        return self.build_workload_pod_template(
            workload,
            name=name,
            image=container_image,
            env=workload_env,
            image_pull_secret_name=(
                registry_credentials_secret_name if registry_pat else None
            ),
            resources=client.V1ResourceRequirements(
                requests={"cpu": "1", "memory": "1Gi"}
            ),
            node_selector={"q8s.example.com/pool": "lab-cpu"},
        )
