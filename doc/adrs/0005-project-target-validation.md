# 5. Project target validation

Date: 2026-11-16

## Status

Accepted

## Context

[ADR 0004](0004-entry-point-based-execution-targets.md) describes discovering execution target plugins through Python entry points. An installed plugin establishes support for a target, but does not establish that the target belongs to the current project.

Previously, `q8sctl execute` checked plugin support without checking the project's `targets` mapping. A target removed or renamed in the project could still execute using an image remaining in the cache or an explicitly supplied image.

## Decision

Execution requires both a target declared in the current project's `targets` mapping and an installed plugin supporting that target.

`q8sctl execute` must validate project membership before accessing Kubernetes or resolving the execution image. An explicit image does not bypass target validation.

Target names match configuration keys and plugin target names exactly. Configuration keys do not define aliases: `gpu1` does not select a plugin named `gpu`. Supporting aliases would require a separate configuration design and decision.

The observable behavior and acceptance criteria are maintained in the [target validation specification](../specs/target-validation.md).

## Consequences

Project configuration determines which supported targets may execute. Stale cached images and explicit image overrides cannot enable execution of an unconfigured target.

Users must declare the requested target using the name provided by its plugin. An invalid request reports the rejected target and the configured alternatives.

This decision specifies the `execute` command. Applying the same validation to other commands or execution interfaces requires their own specification updates and implementation.
