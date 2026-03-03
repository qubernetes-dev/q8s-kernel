import re

_PYTHON_VERSION_RE = re.compile(r"^3(\.\d+){1,2}$")


def get_base_images(python_version: str = "3.12") -> dict[str, str]:
    if not _PYTHON_VERSION_RE.fullmatch(python_version):
        raise ValueError(f"Invalid python_version format: {python_version!r}")

    return {
        "cpu": f"python:{python_version}-slim",
        "gpu": f"ghcr.io/qubernetes-dev/cuda:12.8.1-r2-py{python_version}",
        "qpu": f"python:{python_version}-slim",
        "hpc": f"python:{python_version}-slim"
    }


BASE_IMAGES = get_base_images()


WORKSPACE = "/app"
