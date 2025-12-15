def get_base_images(python_version: str = "3.12") -> dict[str, str]:
    return {
        "cpu": f"python:{python_version}-slim",
        "gpu": f"ghcr.io/qubernetes-dev/cuda:12.8.1-r2-py{python_version}",
        "qpu": f"python:{python_version}-slim",
    }


BASE_IMAGES = get_base_images()
# BASE_IMAGES = {
#     "cpu": "python:3.12-slim",
#     "gpu": "ghcr.io/qubernetes-dev/cuda:12.8.1",
#     "qpu": "python:3.12-slim",
# }


WORKSPACE = "/app"
