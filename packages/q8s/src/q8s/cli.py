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

import importlib
import sys
from pathlib import Path
from subprocess import Popen

import typer
from q8s.execution import K8sContext
from q8s.install import install_my_kernel_spec
from q8s.project import Project
from q8s.targets import get_available_targets
from q8s.utils import get_docker_image, get_kubeconfig
from q8s.workload import Workload
from q8s.workload_run import ProgressUpdate
from rich.markup import escape
from rich.progress import (
    Progress,
    SpinnerColumn,
    Task,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Column
from rich.text import Text
from typing_extensions import Annotated

app = typer.Typer()
TARGET_HELP = (
    f"Execution target. Available targets: {', '.join(get_available_targets())}"
)


class _WorkloadStatusColumn(SpinnerColumn):
    def render(self, task: Task):
        if task.finished:
            outcome = task.fields.get("outcome", "success")
            if outcome == "failed":
                return Text("×", style="red")
            if outcome == "warning":
                return Text("!", style="yellow")
            return Text("✓", style="green")
        return super().render(task)


class _WorkloadProgress:
    _descriptions = {
        "cluster": "Cluster configuration",
        "preparation": "Job preparation",
        "execution": "Job execution",
    }
    _statuses = {
        "loading": ("[dim]Loading[/]", False, ""),
        "creating": ("[dim]Creating resources[/]", False, ""),
        "ready": ("[green]Ready[/]", True, "success"),
        "waiting": ("[dim]Waiting for Job[/]", False, ""),
        "scheduled": ("[cyan]Scheduled[/]", False, ""),
        "running": ("[cyan]Running[/]", False, ""),
        "submitted": ("[cyan]Submitted[/]", True, "success"),
        "complete": ("[green]Complete[/]", True, "success"),
        "job_failed": ("[red]Failed[/]", True, "failed"),
        "watch_ended": ("[yellow]Watch ended before completion[/]", True, "warning"),
        "logs_unavailable": ("[red]Pod logs unavailable[/]", True, "failed"),
        "failed": ("[red]Failed[/]", True, "failed"),
        "interrupted": ("[red]Interrupted[/]", True, "failed"),
    }

    def __init__(self, progress: Progress):
        self._progress = progress
        self._tasks: dict[tuple[str | None, str], TaskID] = {}

    def __call__(self, update: ProgressUpdate):
        if update.status == "configured":
            status = f"[dim]Namespace[/] {escape(update.namespace or '')}"
            finished, outcome = True, "success"
        else:
            status, finished, outcome = self._statuses[update.status]

        key = (update.job_name, update.phase)
        task = self._tasks.get(key)
        if task is None:
            task = self._progress.add_task(
                self._descriptions[update.phase], total=1, status=status
            )
            self._tasks[key] = task
            if not finished:
                return
        self._progress.update(
            task, completed=int(finished), status=status, outcome=outcome
        )


@app.command(
    context_settings={
        "allow_extra_args": True,
        "ignore_unknown_options": True,
    }
)
def init(
    images: Annotated[
        bool, typer.Option(help="Initialize images cache if build in a CI pipeline")
    ] = False,
):
    project = Project()
    project.init_cache()

    if images:
        project.images_from_ci()
        project.update_images_cache()

    print(f"Project {project.name} initialized")


@app.command()
def build(
    init: Annotated[bool, typer.Option(help="Initialize project")] = False,
    target: Annotated[str, typer.Option(help=TARGET_HELP, case_sensitive=False)] = None,
    dry_run: Annotated[
        bool, typer.Option(help="Dry run does not push images to the registry")
    ] = False,
    silent: Annotated[bool, typer.Option(help="Silent mode")] = True,
):

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
        expand=True,
    ) as progress:
        task = progress.add_task(description="[cyan]Loading project...", total=1)

        project = Project()

        progress.advance(task)

        if init:
            # Convert the keys to a string with enumeration
            targets_str = ", ".join(
                [f"{key}" for i, key in enumerate(project.configuration.targets.keys())]
            )
            task = progress.add_task(
                description=f"[cyan]Initializing cache for targets: {targets_str}...",
                total=1,
            )

            project.init_cache()
            progress.advance(task)

        available = get_available_targets()

        if target:

            if target not in available:
                raise ValueError(
                    f"Invalid target '{target}'. Available plugin targets: {available}"
                )

            project.build_container(
                target,
                progress=progress,
                push=(not dry_run),
                silent=silent,
            )

        else:
            for build in project.configuration.targets.keys():
                if build not in available:
                    raise ValueError(
                        f"Invalid target '{build}' in Q8Sproject. "
                        f"Available plugin targets: {available}"
                    )

                project.build_container(
                    build,
                    progress=progress,
                    push=(not dry_run),
                    silent=silent,
                )

        print(f"Project {project.name} ready")
        project.update_images_cache()


@app.command(
    context_settings={
        "allow_extra_args": True,
        "ignore_unknown_options": True,
    }
)
def execute(
    file: Annotated[Path, typer.Argument(help="Python file to be executed")],
    target: Annotated[
        str,
        typer.Option(
            help=TARGET_HELP,
            case_sensitive=False,
        ),
    ] = "cpu",
    kubeconfig: Annotated[
        Path, typer.Option(help="Kubernetes configuration", envvar="KUBECONFIG")
    ] = None,
    image: Annotated[str, typer.Option(help="Docker image")] = None,
    registry_pat: Annotated[
        str,
        typer.Option(
            help="Registry personal access token (PAT)",
            envvar="REGISTRY_PAT",
        ),
    ] = None,
    submit: Annotated[
        bool, typer.Option(help="Submit job and exit without waiting for completion")
    ] = False,
    hpc_config: Annotated[
        Path | None,
        typer.Option(
            "--hpc-config",
            help="Path to HPC config file. If omitted, q8s will look for 'HpcConfig' next to 'Q8Sproject'.",  # noqa: E501
        ),
    ] = None,
    args: Annotated[list[str], typer.Argument(help="Additional arguments")] = None,
):
    project = Project()

    if target not in project.configuration.targets:
        available = ", ".join(project.configuration.targets)
        typer.echo(
            f"Target '{target}' not found in Q8Sproject. "
            f"Configured targets: {available}"
        )
        raise typer.Exit(code=1)

    if kubeconfig is None:
        kubeconfig = project.kubeconfig

    if kubeconfig.exists() is False:
        typer.echo(f"kubeconfig file {kubeconfig} does not exist")
        raise typer.Exit(code=1)

    if kubeconfig is None:
        typer.echo("KUBECONFIG not set")
        raise typer.Exit(code=1)

    with Progress(
        _WorkloadStatusColumn(style="cyan"),
        TextColumn("{task.description}", style="bold"),
        TimeElapsedColumn(table_column=Column(justify="right")),
        TextColumn("{task.fields[status]}"),
    ) as progress:
        k8s_context = K8sContext(
            kubeconfig.as_posix(), progress=_WorkloadProgress(progress)
        )

        if target not in k8s_context.available_targets():
            typer.echo(
                f"Invalid target '{target}'. Available: {k8s_context.available_targets()}"
            )
            raise typer.Exit(code=1)

        if image is None:
            image = project.cached_images(target)

        k8s_context.set_target(target)
        k8s_context.set_registry_pat(registry_pat)
        k8s_context.set_container_image(image)

        workload = Workload.from_entry_script(entry_script=file)
        workload.set_args(args or [])

        workload.extra = {}
        if hpc_config is not None:
            workload.extra["hpc_config"] = hpc_config.as_posix()

        output, stream_name = k8s_context.execute_workload(
            workload=workload, submit=submit
        )

        print(f"output:\n{output}")
        print(f"output stream: {stream_name}")


@app.command()
def jupyter(
    install: Annotated[
        bool,
        typer.Option(
            help="Install kernel spec for Jupyter",
        ),
    ] = False,
    target: Annotated[
        str, typer.Option(help=TARGET_HELP, case_sensitive=False)
    ] = "cpu",
    kubeconfig: Annotated[
        Path, typer.Option(help="Kubernetes configuration", envvar="KUBECONFIG")
    ] = None,
    image: Annotated[str, typer.Option(help="Docker image")] = None,
    registry_pat: Annotated[
        str,
        typer.Option(
            help="Registry personal access token (PAT)",
            envvar="REGISTRY_PAT",
        ),
    ] = None,
):
    if install:
        install_my_kernel_spec(user=False, prefix=sys.prefix)
        # install_my_kernel_spec(user=user, prefix=prefix)

    image = get_docker_image(target) if image is None else image

    kubeconfig = get_kubeconfig(kubeconfig)

    environment_variables = {"KUBECONFIG": kubeconfig.as_posix(), "DOCKER_IMAGE": image}

    if registry_pat:
        environment_variables["REGISTRY_PAT"] = registry_pat

    if importlib.util.find_spec("jupyterlab") is not None:
        typer.echo("Starting JupyterLab...")

        jupyter_process = Popen(
            [sys.executable, "-m", "jupyter", "lab", "-y"],
            env=environment_variables,
        )

        jupyter_process.wait()
    else:
        typer.echo("JupyterLab is not installed. Please install jupyter first.")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
