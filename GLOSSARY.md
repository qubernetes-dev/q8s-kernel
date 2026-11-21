# q8s workload execution

q8s runs workloads on Kubernetes for the CLI and notebook kernel.

## Language

**Workload run**
One invocation of q8s workload execution. Each run has its own identity and may create a Kubernetes Job and supporting resources. A run can end when q8s acknowledges submission or when it returns an execution result.
