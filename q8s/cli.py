import os
from pathlib import Path
from subprocess import Popen
import importlib
import typer
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
import sys
from typing_extensions import Annotated
from q8s.execution import K8sContext
from q8s.enums import Target
from q8s.install import install_my_kernel_spec
from q8s.project import Project
from q8s.utils import get_docker_image, get_kubeconfig

app = typer.Typer()


@app.command()
def build(
    init: Annotated[bool, typer.Option(help="Initialize project")] = False,
    target: Annotated[
        Target, typer.Option(help="Execution target", case_sensitive=False)
    ] = None,
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

        if target:
            project.build_container(
                target=target.value,
                progress=progress,
                push=(not dry_run),
                silent=silent,
            )

        else:
            for build in project.configuration.targets.keys():
                project.build_container(
                    build, progress=progress, push=(not dry_run), silent=silent
                )

    print(f"Project {project.name} ready")
    project.update_images_cache()


@app.command()
def execute(
    file: Annotated[Path, typer.Argument(help="Python file to be executed")],
    target: Annotated[
        Target, typer.Option(help="Execution target", case_sensitive=False)
    ] = Target.gpu,
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
    project = Project()

    if image is None:
        image = project.cached_images(target.value)

    if kubeconfig is None:
        kubeconfig = project.kubeconfig

    if kubeconfig.exists() is False:
        typer.echo(f"kubeconfig file {kubeconfig} does not exist")
        raise typer.Exit(code=1)

    # kubeconfig = os.environ.get("KUBECONFIG", kubeconfig.as_posix())

    if kubeconfig is None:
        typer.echo("KUBECONFIG not set")
        raise typer.Exit(code=1)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
        expand=True,
    ) as progress:
        k8s_context = K8sContext(kubeconfig.as_posix(), progress=progress)
        k8s_context.set_target(target)
        k8s_context.set_container_image(image)
        k8s_context.set_registry_pat(registry_pat)

        with open(file, "r") as f:
            code = f.read()
            # output, stream_name = execute_k8s(code, None, image, registry_pat)
            output, stream_name = k8s_context.execute(code)

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
        Target, typer.Option(help="Execution target", case_sensitive=False)
    ] = Target.gpu,
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


# if __name__ == "__main__":
app()
