# q8s-hpc-rocm

ROCm-based GPU execution target plugin for running q8s jobs on HPC nodes.

This package provides the `hpc-rocm` execution target for q8s and depends on `q8s>=0.14.0`.

## Installation

```bash
pip install q8s-hpc-rocm
```

## Usage

Submit a job using the `hpc-rocm` execution target:

```bash
q8sctl execute app.py --target hpc-rocm --kubeconfig /path/to/kubeconfig
```
