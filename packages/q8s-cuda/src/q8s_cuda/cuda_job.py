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

        volume_name = f"app-volume-{name}"

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

        container = client.V1Container(
            name="quantum-routine",
            image=container_image,
            env=env_var,
            command=["python"],
            args=(
                ["-m", workload.entry_module] + workload.args
                if workload.is_src_project
                else [f"{WORKSPACE}/{workload.entry_script}"] + workload.args
            ),
            image_pull_policy="Always",
            resources=(
                client.V1ResourceRequirements(
                    limits=(
                        {
                            "cpu": "2",
                            "ephemeral-storage": "50Gi",
                            "memory": MEMORY,
                            "nvidia.com/gpu": "1",
                            # "qubernetes.dev/qpu": "1",
                        }
                    ),
                    requests=(
                        {
                            "cpu": "2",
                            "ephemeral-storage": "0",
                            "memory": MEMORY,
                            "nvidia.com/gpu": "1",
                            # "qubernetes.dev/qpu": "1",
                        }
                    ),
                )
            ),
            volume_mounts=[
                client.V1VolumeMount(
                    name=volume_name, mount_path=WORKSPACE, read_only=True
                )
            ],
        )

        template = client.V1PodTemplateSpec(
            metadata=client.V1ObjectMeta(labels={"app": name}),
            spec=client.V1PodSpec(
                containers=[container],
                image_pull_secrets=(
                    [
                        client.V1LocalObjectReference(
                            name=registry_credentials_secret_name
                        )
                    ]
                    if registry_pat
                    else []
                ),
                runtime_class_name="nvidia",
                restart_policy="Never",
                volumes=[
                    client.V1Volume(
                        name=volume_name,
                        config_map=client.V1ConfigMapVolumeSource(
                            name=name,
                            items=[
                                client.V1KeyToPath(key=k, path=v)
                                for k, v in workload.mappings.items()
                            ],
                        ),
                    )
                ],
            ),
        )

        return template
