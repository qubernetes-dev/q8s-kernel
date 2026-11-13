# Copyright 2024-2026 Qubernetes
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Validate a package release tag and write the package to GitHub Actions outputs."""

import os
import tomllib
from pathlib import Path

packages = {"q8s", "q8s-cuda", "q8s-hpc-cpu", "q8s-hpc-rocm"}
tag = os.environ["RELEASE_TAG"]
package, separator, version = tag.rpartition("-v")
if package not in packages or not separator or not version:
    raise SystemExit(f"Invalid release tag: {tag}")
metadata = tomllib.loads(Path(f"packages/{package}/pyproject.toml").read_text())
project = metadata["project"]
if project["name"] != package or project["version"] != version:
    raise SystemExit(
        f"Tag {tag} does not match {project['name']} version {project['version']}"
    )
with open(os.environ["GITHUB_OUTPUT"], "a") as output:
    print(f"package={package}", file=output)
