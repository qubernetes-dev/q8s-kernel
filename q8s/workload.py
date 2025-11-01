from pathlib import Path
import os

from .multifiles import collect_imported_files


class Workload:
    """
    Represents a mutifile workload consisting of an entry script and its imported files
    """

    def __init__(self, entry_script: Path | str = None, code: str = None):
        if entry_script is not None:
            self.__entry_script = Path(os.path.abspath(entry_script))
            self.__base_path = self.__entry_script.parent

            self.__files = collect_imported_files(self.__entry_script)
            self.__data = {
                self.__path_mapping(f): open(f, "r").read() for f in self.__files
            }
        elif code is not None:
            self.__entry_script = Path(os.path.abspath("main.py"))
            self.__base_path = os.getcwd()
            self.__files = [Path(self.__entry_script)]

            self.__data = {self.__path_mapping(self.__entry_script): code}
        else:
            raise ValueError("Either entry_script or code must be provided.")

    @classmethod
    def from_code(cls, code: str):
        """
        Create a Workload from code string
        """
        return cls(code=code)

    @classmethod
    def from_entry_script(cls, entry_script: Path | str):
        """
        Create a Workload from an entry script file path
        """
        return cls(entry_script=entry_script)

    @property
    def files(self) -> list[Path]:
        """
        List of all files in the workload
        """
        return self.__files

    @property
    def entry_script(self) -> Path:
        """
        Entry script path relative to base path
        """
        return self.__relative_path(self.__entry_script)

    @property
    def data(self) -> dict[str, str]:
        """
        Dictionary mapping file paths to their contents
        """
        return self.__data

    @property
    def mappings(self):
        """
        Dictionary mapping relative file paths to their unique path mappings
        """
        return {self.__path_mapping(f): self.__relative_path(f) for f in self.__files}

    def __relative_path(self, file: Path | str) -> str:
        """
        Get the relative path of a file with respect to the base path
        """
        return os.path.relpath(os.path.abspath(file), self.__base_path)

    def __path_mapping(self, file: Path | str) -> str:
        """
        Get the unique path mapping for a file
        """
        return self.__relative_path(file).replace("/", "__")
