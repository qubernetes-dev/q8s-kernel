from typing import Dict

import pluggy
from kubernetes import client

# from q8s.enums import Target
from q8s.workload import Workload

hookspec = pluggy.HookspecMarker("q8s")
hookimpl = pluggy.HookimplMarker("q8s")


class JobTemplatePluginSpec:

    @hookspec
    def prepare(
        self,
        target: str,
        name: str,
        namespace: str,
        env: Dict[
            str,
            str | None,
        ],
    ) -> None:
        pass

    @hookspec
    def makejob(
        self,
        name: str,
        registry_pat: str | None,
        registry_credentials_secret_name: str,
        container_image: str,
        workload: Workload,
        env: list[client.V1EnvVar],
        target: str,
    ) -> client.V1PodTemplateSpec:
        return None

    @hookspec
    def cleanup(self, name: str, namespace: str) -> None:
        pass
