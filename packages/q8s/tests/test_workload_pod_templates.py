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

from importlib.metadata import entry_points, version

import pluggy
import pytest
from kubernetes import client
from q8s.plugins.job_template_spec import JobTemplatePluginSpec
from q8s.workload import Workload


@pytest.mark.parametrize("target", ["cpu", "gpu", "hpc-cpu", "hpc-rocm"])
@pytest.mark.parametrize("layout", ["inline", "script", "src"])
def test_target_projects_workload_into_pod(target, layout, tmp_path, monkeypatch):
    entry = next(
        (ep for ep in entry_points(group="q8s.targets") if ep.name == target), None
    )
    if entry is None and target != "cpu":
        pytest.skip(f"Optional target {target!r} is not installed")
    assert entry is not None
    manager = pluggy.PluginManager("q8s")
    manager.add_hookspecs(JobTemplatePluginSpec)
    manager.register(entry.load()())
    monkeypatch.chdir(tmp_path)

    src_layout = layout == "src"
    if src_layout:
        (tmp_path / "setup.cfg").write_text("[options.packages.find]\nwhere = src\n")
        # Import discovery caches Python packages, so each target uses a distinct name.
        package_name = f"pod_fixture_{target.replace('-', '_')}"
        package = tmp_path / "src" / package_name
        package.mkdir(parents=True)
        (package / "__init__.py").write_text("")
        (package / "helper.py").write_text("VALUE = 42\n")
        script = package / "main.py"
        script.write_text("from .helper import VALUE\nprint(VALUE)\n")
        workload = Workload.from_entry_script(script)
        expected_command = ["-m", f"src.{package_name}.main", "two words"]
        expected_paths = {
            f"src__{package_name}__main.py": f"src/{package_name}/main.py",
            f"src__{package_name}__helper.py": f"src/{package_name}/helper.py",
        }
    elif layout == "inline":
        workload = Workload.from_code("print(42)")
        expected_command = ["/app/main.py", "two words"]
        expected_paths = {"main.py": "main.py"}
    else:
        script = tmp_path / "script.py"
        script.write_text("print(42)\n")
        workload = Workload.from_entry_script(script)
        expected_command = ["/app/script.py", "two words"]
        expected_paths = {"script.py": "script.py"}

    workload.set_args(["two words"])
    if target.startswith("hpc-"):
        config_path = tmp_path / "HpcConfig"
        config_path.write_text("--q8s-node compute-1\n--time 00:01:00\n")
        workload.extra = {"hpc_config": str(config_path)}

    env = [client.V1EnvVar(name="PYTHONPATH", value="/user/path")]
    (pod,) = manager.hook.makejob(
        name="runner",
        registry_pat="placeholder" if src_layout else None,
        registry_credentials_secret_name="runner-regcred",
        container_image="example/image",
        workload=workload,
        env=env,
        target=target,
    )

    (container,) = pod.spec.containers
    (volume,) = pod.spec.volumes
    (mount,) = container.volume_mounts
    assert container.command == ["python"]
    assert container.args == expected_command
    assert container.name == "quantum-routine"
    assert container.image == "example/image"
    assert container.working_dir is None
    assert container.image_pull_policy == "Always"
    assert pod.spec.restart_policy == "Never"
    assert pod.metadata.labels["app"] == "runner"
    assert mount.name == volume.name == "app-volume-runner"
    assert mount.mount_path == "/app" and mount.read_only
    assert volume.config_map.name == "runner"
    assert {item.key: item.path for item in volume.config_map.items} == expected_paths
    assert [secret.name for secret in pod.spec.image_pull_secrets] == (
        ["runner-regcred"] if src_layout else []
    )

    versions = [
        ("Q8S_VERSION", version("q8s")),
        ("Q8S_PLUGIN_VERSION", entry.dist.version),
    ]
    src_path = [("PYTHONPATH", "/app/src")] if src_layout else []
    expected_env = [("PYTHONPATH", "/user/path")]
    expected_env += versions + src_path if target == "hpc-cpu" else src_path + versions
    actual_env = [(entry.name, entry.value) for entry in container.env]
    assert actual_env[: len(expected_env)] == expected_env
    assert actual_env[-1] == ("GIT_PYTHON_REFRESH", "quiet")
    assert [(entry.name, entry.value) for entry in env] == [
        ("PYTHONPATH", "/user/path")
    ]

    if target == "gpu":
        assert pod.spec.runtime_class_name == "nvidia"
        assert container.resources.limits["nvidia.com/gpu"] == "1"
        assert container.resources.requests["nvidia.com/gpu"] == "1"
    if target.startswith("hpc-"):
        assert pod.metadata.labels["interlink.cern.ch/provider"] == "remote-hpc"
        assert pod.metadata.annotations["slurm-job.vk.io/flags"] == "--time=00:01:00"
        assert pod.spec.node_selector == {"kubernetes.io/hostname": "compute-1"}
        (toleration,) = pod.spec.tolerations
        assert toleration.key == "virtual-node.interlink/no-schedule"
        assert toleration.operator == "Exists"
