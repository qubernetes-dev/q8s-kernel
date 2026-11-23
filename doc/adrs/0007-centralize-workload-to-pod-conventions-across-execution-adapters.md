---
issue: 74
---

# 7. Centralize workload-to-Pod conventions across execution adapters

Date: 2026-11-23

## Status

Proposed

## Context

Issue: [#74](https://github.com/qubernetes-dev/q8s-kernel/issues/74)

Specification: [centralize-workload-to-pod-conventions-across-execution-adapters.md](../specs/centralize-workload-to-pod-conventions-across-execution-adapters.md)

> ## Goal
> 
> Define the shared conventions for Python launch, workload file mounts, and image pulls in one place so they apply consistently across CPU, CUDA, HPC CPU, and HPC ROCm. Each adapter continues to supply the settings its computational environment requires, and the workload run continues to create the ConfigMap referenced by the Pod template.
> 
> ## Before — Shared rules repeated in adapters
> 
> ```mermaid
> flowchart TB
>     W["Workload<br/>Files and entry point"]
>     W --> A["Four execution adapters"]
>     W --> R["Workload run<br/>Creates the ConfigMap"]
>     A --> D["Repeated rules<br/>Python launch, mounts, and pull settings"]
>     D --> P["Pod template"]
>     R -. "ConfigMap referenced by the Pod" .-> P
> 
>     classDef repeated fill:#fff4ee,stroke:#b44738,color:#76281f
>     class D repeated
> ```
> 
> ## After — Shared rules defined once
> 
> ```mermaid
> flowchart TB
>     W["Workload<br/>Files and entry point"]
>     W --> A["Four execution adapters<br/>Supply target-specific settings"]
>     W --> R["Workload run<br/>Creates the ConfigMap"]
>     A --> S["Shared rules<br/>Python launch, mounts, and pull settings"]
>     S --> P["Pod template"]
>     R -. "ConfigMap referenced by the Pod" .-> P
> 
>     classDef shared fill:#ecfdf5,stroke:#137459,color:#144d41
>     class S shared
> ```
> 
> Specification: [centralize-workload-to-pod-conventions-across-execution-adapters.md](https://github.com/qubernetes-dev/q8s-kernel/blob/74-centralize-workload-to-pod-conventions-across-execution-adapters/doc/specs/centralize-workload-to-pod-conventions-across-execution-adapters.md)

TODO: Describe the problem, constraints, and alternatives considered. Use the linked issue as context.

## Decision

TODO: Describe the proposed architectural choice and why it addresses the problem.

## Consequences

TODO: Describe benefits, tradeoffs, compatibility effects, and follow-up work.
