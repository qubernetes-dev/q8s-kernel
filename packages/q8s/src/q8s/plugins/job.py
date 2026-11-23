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
from collections.abc import Mapping, Sequence

from kubernetes import client
from q8s.constants import WORKSPACE
from q8s.plugins.utils.git_info import get_git_info
from q8s.workload import Workload


class JobPlugin:
    """
    Common Pod assembly and Git metadata for job template plugins.

    The following environment variables are added:
        - Q8S_GIT_COMMIT, MLFLOW_GIT_COMMIT: The current Git commit hash.
        - Q8S_GIT_BRANCH, MLFLOW_GIT_BRANCH: The current Git branch name.
        - Q8S_GIT_REPO_URL, MLFLOW_GIT_REPO_URL: The remote repository URL.
        - GIT_PYTHON_REFRESH: Set to "quiet" to suppress GitPython refresh warnings.
    """

    @staticmethod
    def build_workload_pod_template(
        workload: Workload,
        *,
        name: str,
        image: str | None,
        env: Sequence[client.V1EnvVar],
        image_pull_secret_name: str | None = None,
        resources: client.V1ResourceRequirements | None = None,
        runtime_class_name: str | None = None,
        labels: Mapping[str, str] | None = None,
        annotations: Mapping[str, str] | None = None,
        node_selector: Mapping[str, str] | None = None,
        tolerations: Sequence[client.V1Toleration] | None = None,
    ) -> client.V1PodTemplateSpec:
        """Build the common workload Pod template for an execution adapter.

        Use the workload run name for `name`. The template mounts the same-named
        ConfigMap read-only at the workspace path and reserves the `app` label
        for that name. Pass the resolved image, prepared environment in order,
        and the pull Secret name when the run uses registry credentials.
        Optional resource, runtime, metadata, and placement settings apply
        to the resulting container or Pod. The workload run creates resources
        from the template.
        """
        volume_name = f"app-volume-{name}"
        launch_args = (
            ["-m", workload.entry_module]
            if workload.is_src_project
            else [f"{WORKSPACE}/{workload.entry_script}"]
        )
        container = client.V1Container(
            name="quantum-routine",
            image=image,
            env=list(env),
            command=["python"],
            args=launch_args + workload.args,
            image_pull_policy="Always",
            resources=resources,
            volume_mounts=[
                client.V1VolumeMount(
                    name=volume_name, mount_path=WORKSPACE, read_only=True
                )
            ],
        )
        volume = client.V1Volume(
            name=volume_name,
            config_map=client.V1ConfigMapVolumeSource(
                name=name,
                items=[
                    client.V1KeyToPath(key=key, path=path)
                    for key, path in workload.mappings.items()
                ],
            ),
        )
        return client.V1PodTemplateSpec(
            metadata=client.V1ObjectMeta(
                labels={**(labels or {}), "app": name},
                annotations=dict(annotations) if annotations is not None else None,
            ),
            spec=client.V1PodSpec(
                containers=[container],
                image_pull_secrets=(
                    [client.V1LocalObjectReference(name=image_pull_secret_name)]
                    if image_pull_secret_name is not None
                    else []
                ),
                restart_policy="Never",
                runtime_class_name=runtime_class_name,
                node_selector=(
                    dict(node_selector) if node_selector is not None else None
                ),
                tolerations=list(tolerations) if tolerations is not None else None,
                volumes=[volume],
            ),
        )

    def patch_environment_with_git_info(
        self, env: list[client.V1EnvVar]
    ) -> list[client.V1EnvVar]:
        """
        Patch environment variables for the job with Git information

        Args:
            env (list[client.V1EnvVar]): Original environment variables
        Returns:
            list[client.V1EnvVar]: Patched environment variables
        """

        # Get Git information from the q8sctl current working directory
        git_info = get_git_info(os.getcwd())

        if git_info.commit:
            env.append(client.V1EnvVar(name="Q8S_GIT_COMMIT", value=git_info.commit))
            env.append(client.V1EnvVar(name="MLFLOW_GIT_COMMIT", value=git_info.commit))

        if git_info.branch:
            env.append(client.V1EnvVar(name="Q8S_GIT_BRANCH", value=git_info.branch))
            env.append(client.V1EnvVar(name="MLFLOW_GIT_BRANCH", value=git_info.branch))

        if git_info.remote_url:
            env.append(
                client.V1EnvVar(name="Q8S_GIT_REPO_URL", value=git_info.remote_url)
            )
            env.append(
                client.V1EnvVar(name="MLFLOW_GIT_REPO_URL", value=git_info.remote_url)
            )

        env.append(client.V1EnvVar(name="GIT_PYTHON_REFRESH", value="quiet"))

        return env
