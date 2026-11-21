---
issue: 72
---

# 6. Graceful cleanup of Kubernetes workload resources

Date: 2026-11-20

## Status

Proposed

## Context

Issue: [#72](https://github.com/qubernetes-dev/q8s-kernel/issues/72)

Specification: [Graceful cleanup of Kubernetes workload resources](../specs/graceful-cleanup-of-kubernetes-workload-resources.md)

> - Track the Kubernetes resources created by each workload run.
> - Clean up those resources if submission fails partway through or the user interrupts the run.
> - Make cleanup safe to retry by treating missing resources as already deleted.
> - Attempt the remaining deletions if one fails, and report cleanup failures alongside the original error.
> - Keep submit-only Jobs running after acknowledgment and use the existing Kubernetes TTL to remove finished Jobs and their dependent resources.

`K8sContext` creates a Job before creating its ConfigMap and Secrets. If one of those later calls fails, the Job can remain pending and never reach the terminal condition that starts the TTL. On interruption, a deletion error can stop cleanup before q8s reaches the Job. Both the CLI and notebook call the same synchronous execution method. [Workload execution](../../packages/q8s/src/q8s/execution.py) · [Kubernetes Job TTL](https://kubernetes.io/docs/concepts/workloads/controllers/ttlafterfinished/)

## Decision

Create a workload run for each `K8sContext.execute_workload()` invocation. The run captures the selected execution settings and owns a synchronous `python-statemachine` `StateChart`, resource creation, submit-only acknowledgment, Job watching, log retrieval, and cleanup. `K8sContext` supplies the Kubernetes clients and configuration. The CLI and notebook render progress updates from the run. Kubernetes continues to manage Job execution and TTL cleanup. [Workload run](../../packages/q8s/src/q8s/workload_run.py)

[Workload state machine diagram](../specs/graceful-cleanup-of-kubernetes-workload-resources.md#proposed-workload-state-machine)

### Library assessment

The assessment weights the three criteria equally and scores each out of five. Higher scores indicate stronger observed adoption, a closer fit to the workload lifecycle, or lower integration effort and risk. The impact scores assume a synchronous refactor behind the existing CLI, notebook, and target plugin interfaces.

| Criterion | `python-statemachine` 3.2.2 | `xstate-statemachine` 0.12.1 |
| --- | --- | --- |
| PyPI usage | **5/5.** 3,253,279 downloads. | **3/5.** 32,552 downloads. |
| Complexity for q8s | **5/5.** Declarative states, events, and guards cover the synchronous workflow, including submit-only and blocking execution. | **4/5.** Its native Python API also covers the workflow. XState JSON, Stately integration, actor spawning, and snapshots would matter if q8s needed a shared TypeScript state chart or actor orchestration. |
| Impact of the change | **4/5.** A localized refactor with one dependency and no transitive dependencies. Keeping Kubernetes calls in the synchronous execution driver preserves error handling despite the library's default conversion of callback exceptions to events. | **4/5.** Its synchronous Python API supports a similarly localized refactor and test scope. Adopting XState JSON would also require maintaining the shared definition and Python bindings. |
| **Total** | **14/15** | **11/15** |

ClickPy measured both packages from 20 October through 18 November 2026 inclusive. Download counts include automated and repeated requests and serve as a proxy for adoption. [PyPI download methodology](https://packaging.python.org/en/latest/guides/analyzing-pypi-package-downloads/) · [ClickPy data source](https://github.com/ClickHouse/clickpy/blob/main/ClickHouse.md#downloads-per-day)

Both versions have dependency-free cores and support q8s's Python 3.10 minimum. `python-statemachine` scores higher on observed usage and fits the synchronous workload lifecycle with fewer concepts for q8s to adopt. [q8s package metadata](../../packages/q8s/pyproject.toml) · [StateChart documentation](https://python-statemachine.readthedocs.io/en/v3.2.2/statechart.html) · [python-statemachine package metadata](https://github.com/fgmacedo/python-statemachine/blob/v3.2.2/pyproject.toml) · [xstate-statemachine on PyPI](https://pypi.org/project/xstate-statemachine/0.12.1/)

## Consequences

The state chart decides when cleanup should run and holds each invocation's resource records. The execution driver updates those records as creation progresses and uses them to attempt cleanup after partial creation or interruption. The driver treats missing resources as already deleted and preserves the original error alongside cleanup failures. Submit-only calls still return after successful resource creation, and finished Jobs remain eligible for Kubernetes TTL cleanup.

The specification defines acceptance criteria for partial creation, interrupted runs, and deletion failures. [Draft specification](../specs/graceful-cleanup-of-kubernetes-workload-resources.md)
