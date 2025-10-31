from pathlib import Path
import os

from .multifiles import collect_imported_files


class Workload:
    """
    Represents a mutifile workload consisting of an entry script and its imported files
    """

    def __init__(self, entry_script: Path | str):
        self.__entry_script = Path(os.path.abspath(entry_script))
        self.__base_path = self.__entry_script.parent

        self.__files = collect_imported_files(self.__entry_script)

    @property
    def files(self) -> list[Path]:
        return self.__files

    @property
    def entry_script(self) -> Path:
        return self.__relative_path(self.__entry_script)

    @property
    def data(self) -> dict[str, str]:
        return {self.__path_mapping(f): open(f, "r").read() for f in self.__files}

    @property
    def mappings(self):
        return {self.__path_mapping(f): self.__relative_path(f) for f in self.__files}

    def __relative_path(self, file: Path | str) -> str:
        return os.path.relpath(os.path.abspath(file), self.__base_path)

    def __path_mapping(self, file: Path | str) -> str:
        return self.__relative_path(file).replace("/", "__")
