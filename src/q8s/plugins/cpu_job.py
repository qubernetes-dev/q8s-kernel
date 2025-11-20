from kubernetes import client

from q8s.constants import WORKSPACE
from q8s.enums import Target
from q8s.plugins.job import JobPlugin
from q8s.plugins.job_template_spec import hookimpl
from q8s.workload import Workload


class CPUJobTemplatePlugin(JobPlugin):

    @hookimpl
    def makejob(
        self,
        name: str,
        registry_pat: str | None,
        registry_credentials_secret_name: str,
        container_image: str,
        workload: Workload,
        env: list[client.V1EnvVar],
        target: Target,
    ) -> client.V1PodTemplateSpec:

        if target != Target.cpu:
            return None

        volume_name = f"app-volume-{name}"

        env_var = list(env)
        if workload.is_src_project:
            env_var.append(client.V1EnvVar(name="PYTHONPATH", value=f"{WORKSPACE}/src"))

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
            volume_mounts=[
                client.V1VolumeMount(
                    name=volume_name,
                    mount_path=WORKSPACE,
                    read_only=True,
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
