# 2. Workloads with multiple files

Date: 2025-11-01

## Status

Accepted

## Context

Current implementation of the `execute` command only supports single file workloads. However, real-life quantum workloads often consist of multiple files. To effectively manage and execute these workloads in a Kubernetes environment, we need a way to package and reference multiple files as part of a single workload.

## Decision

We will introduce a `Workload` class that encapsulates multiple files required for execution. This class will handle the collection of files, their mappings, and any metadata that is necessary to be able to inject the files into the Job.

The `Workload` class will provide methods to:

- Collect all files related to the workload, by starting from the entry file. The mechanism traverses all the imports and dependencies to gather all necessary files, supporting also relative imports.
- Create a mapping of file paths to their contents or locations.
- Load the contents of the files into memory or prepare them for injection into the Kubernetes Job as ConfigMaps.

## Consequences

The `execute` command will be updated to build the `Workload` instance from the entry file that is provided via the same `file` parameter as for the single file.
