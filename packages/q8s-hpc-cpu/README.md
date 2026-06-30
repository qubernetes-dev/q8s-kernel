# q8s-hpc-cpu

CPU execution target plugin for running q8s jobs on HPC nodes.

This package provides the `hpc-cpu` execution target for q8s and depends on `q8s>=0.14.0`.

## Installation

```bash
pip install q8s-hpc-cpu
```

## Usage

Submit a job using the `hpc-cpu` execution target:

```bash
q8sctl execute app.py --target hpc-cpu --kubeconfig /path/to/kubeconfig
```