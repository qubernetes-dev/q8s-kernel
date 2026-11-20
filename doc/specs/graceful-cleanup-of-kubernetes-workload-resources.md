---
issue: 72
summary: "Graceful cleanup of Kubernetes workload resources"
---

# Graceful cleanup of Kubernetes workload resources

Status: Draft

Issue: [#72](https://github.com/qubernetes-dev/q8s-kernel/issues/72)

Decision: [0006-graceful-cleanup-of-kubernetes-workload-resources.md](../adrs/0006-graceful-cleanup-of-kubernetes-workload-resources.md)

## Issue description

> - Track the Kubernetes resources created by each workload run.
> - Clean up those resources if submission fails partway through or the user interrupts the run.
> - Make cleanup safe to retry by treating missing resources as already deleted.
> - Attempt the remaining deletions if one fails, and report cleanup failures alongside the original error.
> - Keep submit-only Jobs running after acknowledgment and use the existing Kubernetes TTL to remove finished Jobs and their dependent resources.

## Scope

TODO: Define the behavior covered by this change and explicit exclusions. Use the linked issue as context.

## Requirements

1. TODO: Describe an observable, testable requirement, including defaults and diagnostics where relevant.

## Acceptance scenarios

| Scenario | Expected behavior |
| --- | --- |
| TODO: Successful request | TODO: Expected result |
| TODO: Invalid input or boundary case | TODO: Expected diagnostic and outcome |

## Verification and maintenance

TODO: Link the tests covering the acceptance scenarios and record any manual verification needed. Update this specification when the behavior changes.
