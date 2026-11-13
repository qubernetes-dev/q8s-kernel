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
