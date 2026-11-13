# q8s

[![PyPI version](https://img.shields.io/pypi/v/q8s.svg)](https://pypi.org/project/q8s/)
[![Python versions](https://img.shields.io/pypi/pyversions/q8s.svg)](https://pypi.org/project/q8s/)
[![codecov](https://codecov.io/github/qubernetes-dev/q8s-kernel/graph/badge.svg?token=5JQ4ALSUZJ)](https://codecov.io/github/qubernetes-dev/q8s-kernel)
[![PyPI Downloads](https://static.pepy.tech/personalized-badge/q8s?period=total&units=INTERNATIONAL_SYSTEM&left_color=GREY&right_color=GREEN&left_text=downloads)](https://pepy.tech/projects/q8s)

Toolset for executing quantum jobs on [Qubernetes](https://www.qubernetes.dev).

## Installation

Install the core package:

```bash
pip install q8s
```

The default installation includes the built-in `cpu` execution target.

Additional execution targets are provided by plugin packages:

```bash
pip install q8s-cuda
pip install q8s-hpc-cpu
pip install q8s-hpc-rocm
```

## Usage

### CLI

Submit a job to the Qubernetes cluster:

```bash
q8sctl execute app.py --kubeconfig /path/to/kubeconfig
```

For more options, run:

```bash
q8sctl execute --help
```

### Jupyter Notebook

Install the `q8s-kernel`:

```bash
q8sctl jupyter --install
```

Start the jupyter notebook server:

```bash
jupyter notebook
```

or the jupyter lab server:

```bash
jupyter lab
```

Select the `Q8s kernel` when creating a new notebook.

## Development

### Prerequisites

The development environment requires the following tools to be installed:

* [Docker](https://www.docker.com/get-started)

### Setup

Install the core package in editable mode:

```bash
pip install -e packages/q8s
```

Install plugin packages in editable mode as needed:

```bash
pip install -e packages/q8s-cuda
pip install -e packages/q8s-hpc-cpu
pip install -e packages/q8s-hpc-rocm
```

If the project is installed in a virtual environment, the `q8s-kernel` can be installed by running the following command:

```bash
q8sctl jupyter --install
```

### Publishing packages

Each package has its own version in `packages/<package>/pyproject.toml` and
is released with a tag named `<package>-v<version>`:

| Package | Example tag |
| --- | --- |
| `q8s` | `q8s-v0.14.0` |
| `q8s-cuda` | `q8s-cuda-v0.1.0` |
| `q8s-hpc-cpu` | `q8s-hpc-cpu-v0.1.0` |
| `q8s-hpc-rocm` | `q8s-hpc-rocm-v0.1.0` |

Before the first release of each plugin, register a pending Trusted Publisher
at <https://pypi.org/manage/account/publishing/> using the package name, this
repository's GitHub owner and name, workflow filename `publish.yml`, and
environment `pypi`. Keep the existing publisher configuration for `q8s`.

To release, update the selected package's version, merge the change, and push
the matching tag. For example, to publish `q8s-cuda` version `0.1.0`:

```bash
git tag q8s-cuda-v0.1.0
git push origin q8s-cuda-v0.1.0
```

The workflow verifies that the tag matches the package metadata, tests all
packages, and builds and checks each package's wheel and source archive. It
publishes only the tagged package to PyPI and attaches its signed distributions
to a GitHub release. Legacy tags such as `v0.14.0` do not trigger publication.
When a plugin requires a new core version, publish `q8s` first.

Pull requests run tests and builds without publishing. Branch pushes also
publish all four packages to TestPyPI using the existing `testpypi`
environment, skipping distributions that have already been uploaded. Before
the first plugin upload, register a pending Trusted Publisher for each plugin
at <https://test.pypi.org/manage/account/publishing/> with the same GitHub
owner, repository, and workflow filename, but environment `testpypi`.
Keep the existing TestPyPI publisher configuration for `q8s`.
