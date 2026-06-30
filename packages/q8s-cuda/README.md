# q8s-cuda

CUDA-based GPU execution target plugin for q8s.

This package provides the `gpu` execution target for q8s and depends on `q8s>=0.14.0`.

## Installation

```bash
pip install q8s-cuda
```

## Usage

Submit a job using the `gpu` execution target:

```bash
q8sctl execute app.py --target gpu --kubeconfig /path/to/kubeconfig
```