from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from io import StringIO
import selectors
from subprocess import Popen, PIPE, STDOUT
from os.path import join
from typing import List, Optional
from rich.progress import Progress
import yaml
from dacite import from_dict
import sys

from q8s.constants import BASE_IMAGES, WORKSPACE


def load(path: str):
    """
    Load the project configuration from the Q8Sproject file
    """
    with open(join(path, "Q8Sproject"), "r") as f:
        return yaml.safe_load(f)


def rmdir(directory):
    """
    Recursively remove a directory and its contents
    """
    directory = Path(directory)

    for item in directory.iterdir():
        if item.is_dir():
            rmdir(item)
        else:
            item.unlink()

    directory.rmdir()


def _read_stream_lines(stream, progress, silent, is_error: bool = False):
    """
    Helper to read from a stream line by line (testable without subprocess).
    """
    while True:
        line = stream.readline()
        if line == '':
            break
        if not silent:
            if is_error:
                progress.console.print(f"[red]{line}[/red]", end="")
            else:
                progress.console.print(line, end="")


def _handle_subprocess_output(process, progress, silent):
    """
    Read subprocess stdout and stderr line by line (Windows-safe).
    """
    if process.stdout:
        _read_stream_lines(process.stdout, progress, silent)
        process.stdout.close()

    if process.stderr:
        _read_stream_lines(process.stderr, progress, silent, is_error=True)
        process.stderr.close()

    process.wait()


@dataclass
class Q8SPythonEnv:
    dependencies: List[str]


@dataclass
class Q8STarget:
    python_env: Q8SPythonEnv


@dataclass
class Q8STargets:
    cpu: Optional[Q8STarget]
    gpu: Optional[Q8STarget]
    qpu: Optional[Q8STarget]

    def keys(self):
        return [
            key
            for key in self.__dataclass_fields__.keys()
            if getattr(self, key) is not None
        ]


@dataclass
class Q8SDocker:
    username: str


@dataclass
class Q8SProject:
    name: str
    python_env: Q8SPythonEnv
    targets: Q8STargets
    docker: Q8SDocker
    kubeconfig: str


class CacheNotBuiltException(Exception):
    pass


class ProjectNotFoundException(Exception):
    pass


class Project:
    name: str
    __path: str
    configuration: Q8SProject
    __images: dict

    def __init__(self, path: str = Path.cwd()):
        try:
            configuration = from_dict(data_class=Q8SProject, data=load(path=path))
        except FileNotFoundError:
            raise ProjectNotFoundException(
                "Q8Sproject file not found in current folder"
            )

        self.configuration = configuration
        self.name = self.configuration.name
        self.__path = path

        self.load_images_cache()

    @property
    def kubeconfig(self):
        return Path(self.configuration.kubeconfig)

    def init_cache(self):
        """
        Initialize the cache directory
        """
        cachepath = join(self.__path, ".q8s_cache")
        Path(cachepath).mkdir(exist_ok=True)

        for target in self.configuration.targets.keys():
            Path(join(self.__path, ".q8s_cache", target)).mkdir(exist_ok=True)

            with open(join(cachepath, target, "requirements.txt"), "w") as f:
                self.__create_requirements_txt(target, f)

            with open(join(cachepath, target, "Dockerfile"), "w") as f:
                self.__create_dockerfile(target, f)

    def check_cache(self):
        result = True

        for target in self.configuration.targets.keys():
            result = self.__check_cache_file(target, "requirements.txt") and result

        return result

    def load_images_cache(self):
        cachepath = join(self.__path, ".q8s_cache", "images")

        if Path(cachepath).exists() is False:
            self.__images = {}
        else:
            with open(cachepath, "r") as f:
                self.__images = yaml.safe_load(f)

    def cached_images(self, target: str) -> str:
        """
        Get the cached images
        """
        cachepath = join(self.__path, ".q8s_cache", "images")

        if Path(cachepath).exists() is False:
            raise CacheNotBuiltException(
                "Images cache not found, build the images first"
            )

        with open(cachepath, "r") as f:
            return yaml.safe_load(f)[target]

    def build_container(
        self, target: str, progress: Progress, silent: bool, push: bool = True
    ):
        """
        Build the container image
        """
        targetpath = join(self.__path, ".q8s_cache", target)

        task = progress.add_task(
            description=f"[cyan]Building container for {target}...", total=1
        )

        # start the docker build command in subprocess and capture the output
        build_process = Popen(
            [
                "docker",
                "build",
                "--progress",
                "plain",
                "--platform",
                "linux/amd64",
                "--tag",
                self.__image_name(target),
                targetpath,
            ],
            stdout=PIPE,
            stderr=STDOUT,
            bufsize=1,
            universal_newlines=True,
            encoding="utf-8",   # force UTF-8 decoding
            errors="replace",   # avoid crashing on bad bytes
        )

        if sys.platform == "win32":
            # Windows-safe: read line by line instead of using selectors
            _handle_subprocess_output(build_process, progress, silent)
        else:
            def handle_output(stream, mask):
                # Because the process' output is line buffered, there's only ever one
                # line to read when this function is called
                line = stream.readline()
                if not silent:
                    progress.console.print(line, end="")

            # Register callback for an "available for read" event from subprocess' stdout stream
            selector = selectors.DefaultSelector()
            selector.register(build_process.stdout, selectors.EVENT_READ, handle_output)

            # Loop until subprocess is terminated
            while build_process.poll() is None:
                # Wait for events and handle them with their registered callbacks
                events = selector.select()
                for key, mask in events:
                    callback = key.data
                    callback(key.fileobj, mask)

            selector.close()

        if build_process.returncode != 0:
            progress.advance(task)
            raise Exception("Failed to build the container")
        else:
            progress.console.print(f"Container {self.__image_name(target)} built")
            progress.advance(task, 1)

        if push:
            self.push_container(target, progress, silent)

        self.__images[target] = self.__image_name(target)

    def push_container(self, target: str, progress: Progress, silent: bool):
        """
        Push the container image to the registry
        """
        task = progress.add_task(
            description=f"[cyan]Pushing container for {target}...", total=1
        )

        push_process = Popen(
            ["docker", "push", self.__image_name(target)],
            stdout=PIPE,
            stderr=STDOUT,
            bufsize=1,
            universal_newlines=True,
            encoding="utf-8",   # force UTF-8 decoding
            errors="replace",   # avoid crashing on bad bytes
        )

        if sys.platform == "win32":
            # Windows-safe: read line by line instead of using selectors
            _handle_subprocess_output(push_process, progress, silent)

        else:
            def handle_output(stream, mask):
                # Because the process' output is line buffered, there's only ever one
                # line to read when this function is called
                line = stream.readline()
                if not silent:
                    progress.console.print(line, end="")

            # Register callback for an "available for read" event from subprocess' stdout stream
            selector = selectors.DefaultSelector()
            selector.register(push_process.stdout, selectors.EVENT_READ, handle_output)

            # Loop until subprocess is terminated
            while push_process.poll() is None:
                # Wait for events and handle them with their registered callbacks
                events = selector.select()
                for key, mask in events:
                    callback = key.data
                    callback(key.fileobj, mask)

            selector.close()

        if push_process.returncode != 0:
            progress.advance(task)
            raise Exception("Failed to push the container")
        else:
            progress.advance(task)

    def update_images_cache(self):
        """
        Update the images cache
        """
        with open(join(self.__path, ".q8s_cache", "images"), "w") as f:
            yaml.dump(self.__images, f)

    def clear_cache(self):
        """
        Clear the cache directory
        """
        cachepath = join(self.__path, ".q8s_cache")
        rmdir(cachepath)

    def __docker_login(self) -> str:
        return self.configuration.docker.username

    def __image_name(self, target: str):
        return f"{self.__docker_login()}/q8s-{self.name.lower()}:{target}"

    def __check_cache_file(self, target: str, file: str):
        cachepath = join(self.__path, ".q8s_cache", target, file)
        if Path(cachepath).exists() is False:
            print(f"Cache file {cachepath} does not exist")
            return False

        file = StringIO()
        self.__create_requirements_txt(target, file)

        with open(cachepath, "r") as f:
            if file.getvalue() != f.read():
                print(f"Cache file {cachepath} is outdated")
                return False

        return True

    def __create_requirements_txt(self, target: str, f):
        print("# This file is autogenerated by q8sctl", file=f)
        print("# Do not edit manually", file=f)

        print("\n# Common dependencies:", file=f)

        for dep in self.configuration.python_env.dependencies:
            print(f"{dep}", file=f)

        print("\n# Target specific dependencies:", file=f)

        for dep in self.__get_target(target=target).python_env.dependencies:
            print(f"{dep}", file=f)

    def __create_dockerfile(self, target: str, f):
        print("# This file is autogenerated by q8sctl", file=f)
        print("# Do not edit manually\n", file=f)

        if target == "gpu":
            print(
                "# Base image specifications are available at https://github.com/qubernetes-dev/images/tree/main/cuda",
                file=f,
            )

        print(f"FROM {BASE_IMAGES[target]}", file=f)
        print("", file=f)

        print(
            f"LABEL org.opencontainers.image.created={datetime.now().isoformat()}",
            file=f,
        )
        print(f"LABEL org.opencontainers.image.title={self.name}", file=f)
        print("", file=f)

        print(f"WORKDIR {WORKSPACE}", file=f)
        print("COPY requirements.txt .", file=f)
        print("RUN pip install --no-cache -r requirements.txt", file=f)

    def __get_target(self, target: str) -> Q8STarget:
        if hasattr(self.configuration.targets, target) is False:
            raise Exception(f"Target {target} not found")

        return getattr(self.configuration.targets, target)
