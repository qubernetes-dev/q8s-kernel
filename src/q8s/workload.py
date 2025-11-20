import configparser
import os
from pathlib import Path

from .multifiles import collect_imported_files


class Workload:
    """
    Represents a multifile workload consisting of an entry script and its imported files
    """

    def __init__(self, entry_script: Path | str = None, code: str = None):
        self.__pyproject_root: Path | None = None
        self.__args: list[str] = []

        if entry_script is not None:

            self.__entry_script = Path(os.path.abspath(entry_script))

            if self.__detect_and_set_src_layout():
                self.__base_path = self.__pyproject_root

                self.__files = collect_imported_files(
                    self.__entry_script, is_project=True
                )
            else:
                self.__base_path = self.__entry_script.parent

                self.__files = collect_imported_files(
                    self.__entry_script, is_project=False
                )

            self.__data = {}
            for f in self.__files:
                with open(f, "r", encoding="utf-8") as file:
                    self.__data[self.__path_mapping(f)] = file.read()

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
    def is_src_project(self) -> bool:
        """
        Whether the project uses a src/ layout
        """
        return self.__pyproject_root is not None

    @property
    def entry_module(self) -> str:
        """
        Entry script module name
        """
        return self.entry_script.replace(os.path.sep, ".")[:-3]  # strip .py

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

    @property
    def args(self) -> list[str]:
        """
        Additional arguments for the workload
        """
        return self.__args

    def set_args(self, args: list[str]) -> None:
        """
        Set additional arguments for the workload
        """
        self.__args = args

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

    def __find_pyproject_root(self) -> Path | None:
        """
        Find the project root by looking for setup.cfg or pyproject.toml
        """

        if (
            Path(os.path.join(os.getcwd(), "setup.cfg")).exists()
            or Path(os.path.join(os.getcwd(), "pyproject.toml")).exists()
        ):
            return Path(os.getcwd()).resolve()

        return None

    def __detect_and_set_src_layout(self) -> bool:
        """
        Determine if the project uses a src/ layout
        """
        root = self.__find_pyproject_root()

        if root is None:
            return False

        cfg_path = root / "setup.cfg"
        if not cfg_path.exists():
            return False

        config = configparser.ConfigParser()
        config.read(cfg_path)

        # Very simple heuristic: [options.packages.find] where = src
        if config.has_section("options.packages.find"):
            where = config.get("options.packages.find", "where", fallback="").strip()
            if where == "src":
                self.__pyproject_root = root
                return True

        # You could add similar checks for pyproject.toml if you use that
        return False
