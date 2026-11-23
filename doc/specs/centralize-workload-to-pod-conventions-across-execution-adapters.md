---
issue: 74
summary: "Centralize workload-to-Pod conventions across execution adapters"
---

# Centralize workload-to-Pod conventions across execution adapters

Status: Implemented

Issue: [#74](https://github.com/qubernetes-dev/q8s-kernel/issues/74)

Decision: [ADR 0007](../adrs/0007-centralize-workload-to-pod-conventions-across-execution-adapters.md)

## Problem Statement

Execution adapters repeat the rules for launching Python, mounting workload files, and configuring image pulls. A change to those rules must be carried across CPU, CUDA, HPC CPU, and HPC ROCm. An author adding a new computational environment also needs a documented way to reuse those rules and distribute the adapter independently.

## Solution

Give adapter authors one supported way to assemble a Pod template with the common workload conventions. Adapters supply their environment's settings. Workload authors select the configured target through the existing q8s workflow, and the workload run manages the resources it creates.

## User Stories

1. As a workload author, I want the same script and arguments to launch consistently across execution targets, so that switching targets preserves how I invoke my workload.
2. As a notebook user, I want my cell code and workload files available on every target, so that I can run the same notebook in different environments.
3. As a workload author, I want relative workload paths preserved under the workspace mount, so that my code can find supporting files.
4. As a user of a private registry, I want each target to use the pull Secret prepared for my run, so that it can pull my image.
5. As an adapter author, I want a documented Pod builder, so that I can reuse q8s workload conventions when adding a computational environment.
6. As an adapter author, I want to specify my target's image, ordered environment, resources, and placement, so that the workload runs with the required software and hardware.
7. As an adapter author, I want to return a custom Pod template when my environment needs one, so that I can use the existing plugin contract for specialised targets.
8. As a third-party maintainer, I want to publish an adapter independently of q8s core, so that I can release support for my environment on my own schedule.
9. As a third-party maintainer, I want to know what q8s versions my adapter supports, so that I can declare the correct dependency and plan upgrades.
10. As an operator, I want the run to continue managing the resources it creates, so that adopting the shared builder preserves the existing workload lifecycle.
11. As a prospective adapter author, I want a published walkthrough, so that I can discover the extension points and verify my first target.

## Implementation Decisions

- Expose the shared builder as `JobPlugin.build_workload_pod_template`. It takes the workload, run name, image, ordered environment, and optional image pull Secret name and returns a Kubernetes Pod template. Its optional target settings are container resources, runtime class, Pod labels and annotations, node selector, and tolerations. The builder reserves the `app` label for the run name.
- Apply the [container conventions](container-conventions.md) consistently for Python launch and the read-only `/app` workspace mount. Preserve workload argument order and the image's working directory. The template projects workload ConfigMap keys to their relative paths, labels the Pod with `app` set to the run name, sets the image pull policy to `Always` and the restart policy to `Never`, and includes the pull Secret reference when supplied.
- Keep base-image selection and environment assembly with each adapter. Preserve CUDA resource requests and limits and the NVIDIA runtime class. Preserve HPC labels, Slurm annotations, node selectors, and tolerations, as well as the existing environment order for each target, including the placement of `PYTHONPATH` in HPC CPU.
- Register separately packaged adapters through `q8s.targets`. The adapter class exposes a `target_name` that matches the project target key and provides base-image selection and the `makejob` hook. The hook may use the shared builder or return a custom template.
- The workload run creates the Job and its supporting resources, including the ConfigMap named in the template. Adapters manage their own resources through `prepare` and `cleanup` when needed.
- Migrate CPU first, then CUDA, HPC CPU, and HPC ROCm. Release the required q8s core API before publishing adapter packages that use it. Each migrated package declares the minimum q8s version it needs.

## Testing Decisions

- Use the existing Pluggy `makejob` hook for template tests. Load each adapter through its package entry point and assert on the returned Kubernetes fields for notebook cells, ordinary scripts, and `src/`-layout workloads. Cover Python arguments, relative paths, the read-only mount, the inherited image working directory, image pull settings, environment order, and target-specific resource and scheduling settings.
- Use the existing submit-only workload run test with a mocked Kubernetes client to verify that the submitted Job's Pod template references the ConfigMap the run creates and that projected keys and paths match the workload data. Verify the pull Secret reference with and without registry credentials across the existing template and submission tests.
- Verify package compatibility by installing a previously released adapter with the updated q8s core and exercising its existing hook. For each migrated adapter, verify discovery and template generation at its declared minimum q8s version.
- Use an installed adapter and a small workload to verify the published walkthrough on a cluster configured for the chosen target.

## Out of Scope

- Correcting the extra `src.` prefix in the module name for `src/`-layout workloads. That follow-up preserves the mounted path under `/app/src` and verifies package-relative imports.
- Provisioning hardware, cluster runtimes, or schedulers for new targets.

## Further Notes

CPU, CUDA, HPC CPU, and HPC ROCm use the shared builder. The migrated adapter packages declare q8s 0.14.3 as their minimum. After the core and adapter releases, the authoring guide will show how to choose an image, register a target, configure it in `Q8Sproject`, and verify a workload on the target.
