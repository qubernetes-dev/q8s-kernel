# Lab CPU execution adapter

This example shows how to package and register a custom q8s execution adapter. The `lab-cpu` adapter routes workloads to a labelled Kubernetes CPU node pool. A Bell-state circuit demonstrates how to build and run a workload on that target.

- `q8s-lab-cpu/` contains the Python package and its `q8s.targets` entry point.
- `workload/` contains the `Q8Sproject` configuration, `requirements-dev.txt`, and the Bell-state circuit.

## Prerequisites

- Python 3.10 or newer and Docker authenticated to Docker Hub.
- A Kubernetes cluster with an amd64 node labelled `q8s.example.com/pool=lab-cpu`, with capacity for a Pod requesting one CPU and 1 GiB of memory.
- A kubeconfig with access to submit q8s jobs. Save it as `workload/kubeconfig`.

## Run the example

In `workload/Q8Sproject`, set `docker.username` to your Docker Hub username. Use a registry repository the cluster can pull from.

From `examples/lab-cpu/`, run these commands in your Python environment.

```bash
cd workload
python -m pip install -r requirements-dev.txt
q8sctl build --init --target lab-cpu
q8sctl execute --target lab-cpu --kubeconfig ./kubeconfig demo.py
```

To try the example using q8s core from this checkout, run `python -m pip install -e ../../../packages/q8s -r requirements-dev.txt` from `workload/` as the installation step.

The simulator prints counts for `00` and `11`, with a roughly even split over 1,024 shots. To inspect scheduling, rerun the execute command with `--submit` and check the Pod before the Job expires.
