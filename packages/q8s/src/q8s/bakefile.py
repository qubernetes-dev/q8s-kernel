from dataclasses import dataclass
from enum import Enum

# Dataclasses representing the structure of a Docker bake file


# class BakeTargetName(str, Enum):
#     cpu = "cpu"
#     gpu = "gpu"
#     qpu = "qpu"
#     hpc = "hpc"
#     hpc_rocm = "hpc_rocm"


class BuildPlatform(str, Enum):
    linux_amd64 = "linux/amd64"
    linux_arm64 = "linux/arm64"


@dataclass
class Group:
    targets: list[str]


@dataclass
class Groups:
    default: Group


@dataclass
class BakeTargetData:
    context: str
    dockerfile: str
    tags: list[str]
    platforms: list[BuildPlatform]


@dataclass
class Bakefile:
    group: Groups
    target: dict[str, BakeTargetData]

    def __init__(self):
        self.group = Groups(default=Group(targets=[]))
        self.target = {}

    def add_target(
        self,
        name: str,
        tags: list[str],
        platforms: list[BuildPlatform | str],
    ):
        bake_target = name

        self.target[bake_target] = BakeTargetData(
            context=f"./{bake_target}",
            dockerfile="Dockerfile",
            tags=tags,
            platforms=[BuildPlatform(p) for p in platforms],
        )

        self.group.default.targets.append(bake_target)
