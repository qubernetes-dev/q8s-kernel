# 4. Entry point based execution targets

Date: 2026-06-30

## Status

Proposed

## Context

Execution targets were previously registered by the core package. This made the core package responsible for knowing which targets are available and where their implementations are located.

As new execution targets are added, this approach makes the core package harder to extend and maintain.

## Decision

Execution targets will be discovered through Python entry points.

The core `q8s` package will provide the built-in `cpu` target. Additional targets will be provided by separate plugin packages and discovered through the `q8s.targets` entry point group.

The initial external target packages are:

* `q8s-cuda`, providing the `gpu` target
* `q8s-hpc-cpu`, providing the `hpc-cpu` target
* `q8s-hpc-rocm`, providing the `hpc-rocm` target

## Consequences

The core package no longer needs to hard-code all supported execution targets.

New execution targets can be added by installing additional plugin packages. Users can install only the target plugins they need.
