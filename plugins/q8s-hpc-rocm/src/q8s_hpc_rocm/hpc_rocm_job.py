from __future__ import annotations

import shlex
from pathlib import Path

from kubernetes import client

from q8s.constants import WORKSPACE
# from q8s.enums import Target
from q8s.plugins.job import JobPlugin
from q8s.plugins.job_template_spec import hookimpl
from q8s.workload import Workload

from importlib.metadata import version

def _get_workload_extra(workload: Workload) -> dict:
    """
    Gets the "extra" information of the workload.
    """
    extra = getattr(workload, "extra", {})
    return extra if isinstance(extra, dict) else {}


def _find_project_root(start: Path) -> Path:
    """
    Tries to find Q8Sproject file from current directory or a parent directory, 
    in order to locate the root directory of the project.
    """
    current = start.resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "Q8Sproject").exists():
            return candidate
    return Path.cwd().resolve()


def resolve_hpc_config_path(workload: Workload) -> Path:
    """
    Tries to find all necessary slurm settings by trying to
    find HpcConfig file in the project root directory, and checking if 
    the workload already includes a path to it.
    """
    extra = _get_workload_extra(workload)
    explicit_path = extra.get("hpc_config")

    if explicit_path:
        return Path(explicit_path).expanduser().resolve()

    project_root = _find_project_root(Path.cwd())
    return project_root / "HpcConfig"


def _parse_config_line(line: str, line_number: int) -> tuple[str, str] | None:
    """
    Parses a single line of a HpcConfig file

    Accepts values formatted like these two options:
    - --flag value
    - --flag=value

    Blank lines and lines starting with '#' are ignored.
    """
    stripped = line.strip()

    if not stripped or stripped.startswith("#"):
        return None

    parts = shlex.split(stripped)
    if not parts:
        return None

    first = parts[0]
    if not first.startswith("--"):
        raise ValueError(
            f"Invalid HPC config line {line_number}: expected a flag starting with '--', got: {line!r}"
        )

    if "=" in first:
        if len(parts) != 1:
            raise ValueError(
                f"Invalid HPC config line {line_number}: do not mix '--flag=value' with extra tokens: {line!r}"
            )
        flag, value = first.split("=", 1)
    else:
        if len(parts) != 2:
            raise ValueError(
                f"Invalid HPC config line {line_number}: expected '--flag value', got: {line!r}"
            )
        flag, value = parts

    if value == "":
        raise ValueError(
            f"Invalid HPC config line {line_number}: missing value for flag {flag}"
        )

    return flag, value


def load_hpc_config(workload: Workload) -> dict:
    """
    Load and parse the entire HpcCOnfig file

    Everything except q8s-node are treated as slurm flags.
    """
    config_path = resolve_hpc_config_path(workload)

    if not config_path.exists():
        raise FileNotFoundError(
            f"HPC target selected, but config file was not found: {config_path}"
        )

    q8s_node: str | None = None
    slurm_flags: list[str] = []

    with config_path.open("r", encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            parsed = _parse_config_line(line, line_number)
            if parsed is None:
                continue

            flag, value = parsed

            if flag == "--q8s-node":
                q8s_node = value
            else:
                slurm_flags.append(f"{flag}={value}")

    if q8s_node is None:
        raise ValueError(
            f"HPC config file '{config_path}' is missing required flag '--q8s-node'"
        )

    return {
        "path": str(config_path),
        "q8s_node": q8s_node,
        "slurm_flags": slurm_flags,
    }


class HpcRocmJobTemplatePlugin(JobPlugin):
    target_name = "hpc-rocm"

    def get_base_image(self, python_version: str) -> str:
        return "aapopeiponen/qiskit-lumi-rocm-singlenode"

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

        hpc_config = load_hpc_config(workload)

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
                value=version("q8s-hpc-rocm"),
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
            volume_mounts=[
                client.V1VolumeMount(
                    name=volume_name,
                    mount_path=WORKSPACE,
                    read_only=True,
                )
            ],
        )

        annotations = {
            "slurm-job.vk.io/flags": " ".join(hpc_config["slurm_flags"])
        }

        template = client.V1PodTemplateSpec(
            metadata=client.V1ObjectMeta(
                labels={
                    "app": name,
                    "interlink.cern.ch/provider": "remote-hpc",
                },
                annotations=annotations,
            ),
            spec=client.V1PodSpec(
                containers=[container],
                node_selector={
                    "kubernetes.io/hostname": hpc_config["q8s_node"]
                },
                tolerations=[
                    client.V1Toleration(
                        key="virtual-node.interlink/no-schedule",
                        operator="Exists"
                    )
                ],
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