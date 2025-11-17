# 3. Support for project src layout

Date: 2025-11-14

## Status

Accepted

## Context

Python projects have increasingly adopted the "src" layout, where the source code is placed inside a top-level `src/` directory. This structure helps to avoid certain import issues and makes it clearer which code is part of the package versus auxiliary files like tests or configuration. A simplified example of this layout is as follows:

```
src/
└── my_package/
    ├── __init__.py
    ├── utils.py
    └── app.py
tests/
└── test_utils
Q8Sproject
README.md
pyproject.toml
setup.cfg
```

## Decision

The workload functionality will be updated to recognize and support the `src/` layout. The detection of the layout is based on inspecting the `setup.cfg`.

The workload will be executed by the Job container as modules, using the `-m` flag of the Python interpreter. For example, if the entry script is `src/my_package/app.py`, it will be executed as:

```bash
python -m my_package.app
```

## Consequences

The `q8sctl execute` command will now correctly identify and handle projects structured with the `src/` layout, being able to execute workloads using the same interface as before:

```bash
q8sctl execute --target cpu src/my_package/app.py
```

This change will enhance compatibility with modern Python project structures and improve the overall developer experience when working with such projects.
