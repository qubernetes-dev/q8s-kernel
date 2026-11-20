---
issue: 72
---

# 6. Graceful cleanup of Kubernetes workload resources

Date: 2026-11-20

## Status

Proposed

## Context

Issue: [#72](https://github.com/qubernetes-dev/q8s-kernel/issues/72)

Specification: TODO: Link the related document if one is needed.

> - Track the Kubernetes resources created by each workload run.
> - Clean up those resources if submission fails partway through or the user interrupts the run.
> - Make cleanup safe to retry by treating missing resources as already deleted.
> - Attempt the remaining deletions if one fails, and report cleanup failures alongside the original error.
> - Keep submit-only Jobs running after acknowledgment and use the existing Kubernetes TTL to remove finished Jobs and their dependent resources.

TODO: Describe the problem, constraints, and alternatives considered. Use the linked issue as context.

## Decision

TODO: Describe the proposed architectural choice and why it addresses the problem.

## Consequences

TODO: Describe benefits, tradeoffs, compatibility effects, and follow-up work.
