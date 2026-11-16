---
issue: 68
summary: Validate requested execution target against project configuration and installed plugins
---

# Target validation

Status: Implemented

Decision: [ADR 0005: Project target validation](../adrs/0005-project-target-validation.md)

## Scope

This specification defines target validation for `q8sctl execute`. It does not define validation for `build`, `jupyter`, or execution initiated through the notebook kernel.

The project configuration is the `Q8Sproject` file loaded by `Project`. Configured targets are the keys of its `targets` mapping. Supported targets are the names exposed by installed execution target plugins.

## Requirements

1. The requested target must exist in the project's `targets` mapping. This applies to both an explicit `--target` and the default target, `cpu`.
2. If the target is absent, the command must exit with code `1`, identify the rejected target, and list the configured targets in configuration order.
3. Project membership validation must occur before Kubernetes configuration checks, Kubernetes context creation, cached image lookup, or workload submission.
4. Neither a cached image nor an explicit `--image` may bypass project membership validation.
5. A configured target must also be supported by an installed execution target plugin. If it is unsupported, the command must exit with code `1` and report the target and available plugin targets before resolving the image or submitting a workload. Plugin validation currently occurs after Kubernetes context creation.
6. Target names must match configuration keys and plugin target names exactly. Configuration keys do not define aliases.
7. When both checks pass, execution continues with the existing image selection and workload submission behavior. Passing target validation does not guarantee execution succeeds.

## Acceptance scenarios

Unless stated otherwise, the project declares `cpu` and `gpu` in that order, and installed plugins support both targets. These are the valid targets for the scenarios below; `other` is the invalid target used to exercise rejection.

| Scenario                                                  | Expected behavior                                                             |
| --------------------------------------------------------- | ----------------------------------------------------------------------------- |
| Request `other`, even with a supporting plugin installed  | Exit `1` because `other` is absent from the project.                          |
| Request `other`, with an old `other` image in the cache   | Exit `1` without looking up the cached image.                                 |
| Request `other` with `--image custom-other-image`         | Exit `1`; the explicit image does not bypass validation.                      |
| Request `other`, with an invalid Kubernetes configuration | Report the project membership error before checking Kubernetes configuration. |
| Request `gpu`, with its supporting plugin absent          | Exit `1` through plugin validation.                                           |
| Request `cpu`, with a supporting plugin installed         | Pass target validation and continue normal execution.                         |
| Request `gpu`, with a supporting plugin installed         | Pass target validation and continue normal execution.                         |
| Omit `--target`, with `cpu` configured and supported      | Validate the default `cpu` target and continue normal execution.              |
| Omit `--target`, with `cpu` absent from the project       | Exit `1` because the default target is unconfigured.                          |
| Request any target with an empty `targets` mapping        | Exit `1` and report no configured alternatives.                               |

Plugin validation scenarios assume a usable Kubernetes configuration so that execution reaches that check.

For the unconfigured `other` target, the diagnostic is:

```text
Target 'other' not found in Q8Sproject. Configured targets: cpu, gpu
```

## Verification and maintenance

[CLI regression tests](../../packages/q8s/tests/test_cli.py) cover all acceptance scenarios above, including diagnostics, exit codes, rejection before Kubernetes configuration checks and cache lookup, missing plugin support, and successful execution with configured targets. They also verify exact target-name matching and successful execution with an explicit image. Kubernetes access and workload submission are mocked.

For changes to this behavior, update this specification first, derive or update acceptance tests, implement the change, and verify the affected scenarios. Record significant policy or architecture changes in an ADR and link it here.
