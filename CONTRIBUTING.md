# Contributing to q8s

Contributions to the core library, execution target plugins, tests, and documentation are welcome.

See the [development process](doc/development-process.md) for the workflow from an issue through specifications, architecture decisions, implementation, review, and release.

## Reporting bugs and proposing changes

Search the [existing issues](https://github.com/qubernetes-dev/q8s-kernel/issues) before opening a new one. For a bug report, include:

- A minimal example and steps to reproduce the problem.
- Expected behavior and actual behavior, including relevant error output.
- Your operating system, Python version, q8s and plugin versions, and execution target. Include cluster details when they affect the problem.

Remove credentials, tokens, and private cluster information from examples and logs. For substantial features or changes to execution behavior, open an issue to discuss the design before implementing it. Small fixes and documentation improvements can go straight to a pull request.

## Setting up development

Use Git and Python 3.10 or newer. CI runs on Python 3.10, 3.11, 3.12, and 3.13. Fork and clone the repository if you do not have write access, then create a branch for your change.

Run these commands from the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e "packages/q8s[development]"
python -m pip install -e packages/q8s-cuda -e packages/q8s-hpc-cpu -e packages/q8s-hpc-rocm
pre-commit install
```

On Windows PowerShell, activate the environment with `.venv\Scripts\Activate.ps1` instead. Editable installs use your local source changes without reinstalling. Install all three plugins to exercise the full test suite.

Unit tests mock external services. Testing actual job execution requires Docker and access to a Qubernetes cluster with a valid kubeconfig. For notebook work, register the kernel from the activated environment:

```bash
q8sctl jupyter --install
```

## Finding the right package

| Directory | Responsibility |
| --- | --- |
| `packages/q8s/` | Core library, CLI, Jupyter kernel, and built-in `cpu` target |
| `packages/q8s-cuda/` | CUDA plugin providing the `gpu` target |
| `packages/q8s-hpc-cpu/` | HPC CPU plugin providing the `hpc-cpu` target |
| `packages/q8s-hpc-rocm/` | HPC ROCm plugin providing the `hpc-rocm` target |

Each package has its own `pyproject.toml`, `src/`, and `tests/`. Put source changes and tests in the package responsible for the behavior.

Execution target plugins are discovered through the `q8s.targets` Python entry point group. Use the existing plugin packages and the [plugin hook specification](packages/q8s/src/q8s/plugins/job_template_spec.py) as references when adding or changing a target.

Adapters can be packaged and maintained independently. In your `makejob` hook, use [`JobPlugin.build_workload_pod_template`](packages/q8s/src/q8s/plugins/job.py) to apply the shared Python launch, workspace mount, and image pull conventions. Pass the run name, resolved image, ordered environment, and pull Secret name when applicable. The builder also accepts container resources, a runtime class, Pod labels and annotations, node selectors, and tolerations. The run name supplies the reserved `app` label. Adapters can also return a custom Pod template through the same hook. Declare the minimum q8s version that provides the API your adapter uses. [Adapter specification](doc/specs/centralize-workload-to-pod-conventions-across-execution-adapters.md)

To scaffold documents from an issue, apply `needs-spec` or `needs-adr`. Both labels reuse the issue's linked branch, regardless of its name, and a shared draft PR. Create a branch from the issue's **Development** section first to use your preferred name; otherwise, the automation creates and links one. Complete the generated TODOs before implementation; see the [automation guide](https://github.com/qubernetes-dev/sdlc-action#operations).

Read the relevant [architecture decisions](doc/adrs/) and [feature specifications](doc/specs/) before changing behavior. Update affected specifications and document significant architectural decisions in a new ADR, following the existing format. Update user documentation and examples when the CLI, configuration, or execution behavior changes.

## Testing and code checks

Add or update tests for behavior changes. Bug fixes should include a regression test that reproduces the failure. Keep unit tests independent of live clusters and credentials by mocking external services.

From the repository root, run a focused test while developing:

```bash
python -m pytest packages/q8s/tests/test_cli.py
```

Before submitting, run the full suite with coverage, matching CI:

```bash
python -m pytest packages --cov=q8s --cov-report=xml
```

For packaging changes, build and validate the affected package. For example:

```bash
python -m pip install build twine
cd packages/q8s
python -m build
python -m twine check --strict dist/*
cd ../..
```

## Using pre-commit

The core package's `development` extra installs pre-commit. From the repository root, with your virtual environment activated, install the Git hook once per clone:

```bash
pre-commit install
```

The hook runs automatically on staged files when you run `git commit`. Its configuration lives in [`.pre-commit-config.yaml`](.pre-commit-config.yaml) and includes:

- Black for Python formatting and isort for import ordering.
- Flake8 for Python lint checks, using the settings in [`.flake8`](.flake8).
- Copyright and license header checks with addlicense.
- Checks for whitespace, final newlines, mixed line endings, merge conflicts, large files, Python syntax, debug statements, YAML, and XML.

Follow [`.editorconfig`](.editorconfig) and the existing code style. Run all hooks against all tracked files before opening a pull request:

```bash
pre-commit run --all-files
```

For a shorter feedback cycle, check staged files or run a single hook:

```bash
pre-commit run
pre-commit run flake8 --all-files
```

The first run downloads the configured hooks and creates their environments, so it needs internet access and may take longer than later runs.

If a hook modifies files, review the diff, stage the fixes with `git add`, and retry the commit. For failures that cannot be fixed automatically, such as lint errors, correct the reported issues and rerun the checks. A failed hook stops the commit until the issues are resolved.

If `pre-commit` is not found, activate your virtual environment and reinstall the development dependencies with `python -m pip install -e "packages/q8s[development]"`. If you recreate the virtual environment, run `pre-commit install` again so the Git hook uses the new environment.

## Submitting a pull request

Keep each pull request focused on one change and use a title that describes the resulting behavior. In the description, explain the problem, the solution, and how you verified it. Link related issues and call out compatibility changes or any checks you could not run. For cluster-dependent changes, include the target and environment used for manual verification.

Review the diff before submitting. Include relevant tests and documentation, and leave out generated build artifacts, coverage reports, local environments, and credentials. Keep review discussions respectful and focused on the work.

The [CI workflow](.github/workflows/publish.yml) tests all four packages across the supported Python versions, then builds and validates each package's wheel and source distribution. Pull requests do not publish packages. Address failed checks and review feedback before merging.

Documentation automation is maintained and tested in the shared [SDLC action repository](https://github.com/qubernetes-dev/sdlc-action). This repository keeps only its caller workflows; update both pinned action references together when adopting a new version.

## Releases and licensing

Packages are versioned and released independently. Follow the [publishing instructions](README.md#publishing-packages) for version updates, release tags, and publishing configuration. Branch pushes run the workflow's TestPyPI publication jobs; package release tags trigger PyPI publication.

Contributions are made under the project's [Apache License 2.0](LICENSE). Preserve applicable copyright and license notices.
