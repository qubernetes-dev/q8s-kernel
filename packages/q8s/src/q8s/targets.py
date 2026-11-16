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

from importlib.metadata import entry_points


def get_available_targets():
    """
    Get the available targets from the installed packages entry points.

    They are defined in the entry points of the installed packages under the group "q8s.targets".

    [project.entry-points."q8s.targets"]
    target_name = "path.to.target:TargetClass"

    Returns:
        list: A list of available targets.
    """

    available = []

    for ep in entry_points(group="q8s.targets"):
        try:
            plugin_cls = ep.load()
            plugin = plugin_cls()

            if hasattr(plugin, "target_name"):
                available.append(plugin.target_name)

        except Exception as e:
            print(f"Failed to load plugin {ep.name}: {e}")

    return available
