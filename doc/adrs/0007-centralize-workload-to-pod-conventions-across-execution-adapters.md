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

CPU, CUDA, HPC CPU, and HPC ROCm each assembled the same Python launch, workspace mount, and image pull settings. The workload run creates the ConfigMap separately. Every adapter must reference that ConfigMap and project its keys to the correct paths.

[ADR 0004](0004-entry-point-based-execution-targets.md) defines discovery through Python entry points. The current adapters share a maintainer, and the extension policy should also serve teams that package and maintain adapters independently of q8s core. [ADR 0006](0006-graceful-cleanup-of-kubernetes-workload-resources.md) defines workload resource ownership.

## Decision

Make `JobPlugin.build_workload_pod_template` a supported, optional API for adapter authors. `JobPlugin` is the base class used by the existing adapters, so authors can discover the builder where they already find shared plugin behavior. The builder owns the common launch, workspace, and pull conventions. Each adapter continues to choose the image, prepare its environment, and define the resource and scheduling settings for its target.

Third parties can publish their own adapter packages and register them through the existing `q8s.targets` entry point group without a q8s core release. Registration, `target_name`, base-image selection, and the documented plugin hooks form the adapter contract. Adapters may return a custom Pod template through `makejob` when their environment requires one. The workload run owns its Kubernetes resources, and adapters own resources they create through their lifecycle hooks.

## Consequences

- q8s core documents the supported builder inputs and template behavior. Release notes announce deprecations and provide migration guidance before incompatible changes to the supported adapter contract.
- An adapter that adopts the builder declares the minimum released q8s version that provides the interface it uses. Publish that core version before releasing an adapter that depends on it.
- Once the builder is released, publish an adapter authoring guide on [qubernetes.dev](https://www.qubernetes.dev/) showing how to package, register, and verify a target for a new computational environment.
