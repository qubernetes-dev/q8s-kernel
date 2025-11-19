# from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Dict, Any
import os

from git import Repo, InvalidGitRepositoryError, NoSuchPathError


@dataclass
class GitInfo:
    commit: Optional[str]
    branch: Optional[str]
    remote_url: Optional[str]
    extra: Dict[str, Any]


def _detect_branch_from_env() -> Optional[str]:
    """
    Try to infer branch name from common CI environment variables.
    Extend this for your CI setup as needed.
    """
    # GitHub Actions
    if ref_name := os.getenv("GITHUB_REF_NAME"):
        return ref_name

    # GitLab CI
    if ref_name := os.getenv("CI_COMMIT_REF_NAME"):
        return ref_name

    # Generic
    return os.getenv("BRANCH_NAME")


def get_git_info(path: str = ".") -> GitInfo:
    """
    Collect commit, branch and remote URL info using GitPython.

    Returns GitInfo with None fields if not in a git repo.
    """
    try:
        repo = Repo(path, search_parent_directories=True)
    except (InvalidGitRepositoryError, NoSuchPathError):
        return GitInfo(
            commit=None,
            branch=None,
            remote_url=None,
            extra={"reason": "not_a_git_repo"},
        )

    # Commit SHA
    try:
        commit = repo.head.commit.hexsha
    except TypeError:
        commit = None

    # Branch (handle detached HEAD, CI environments, etc.)
    if repo.head.is_detached:
        branch = _detect_branch_from_env()
        branch_source = "env" if branch else "detached_head"
    else:
        branch = repo.active_branch.name
        branch_source = "repo"

    # Remote URL
    try:
        origin = repo.remotes.origin
        remote_url = origin.url
        if remote_url.startswith("git@"):
            # git@github.com:org/repo.git -> https://github.com/org/repo.git
            host, _, path = remote_url.partition(":")
            remote_url = f"https://{host.removeprefix('git@')}/{path}"
        elif remote_url.startswith("ssh://"):
            # ssh://git@github.com/org/repo.git -> https://github.com/org/repo.git
            stripped = remote_url.removeprefix("ssh://")
            if stripped.startswith("git@"):
                stripped = stripped.removeprefix("git@")
            host, _, path = stripped.partition("/")
            remote_url = f"https://{host}/{path}"
    except Exception:
        remote_url = None

    extra = {
        "branch_source": branch_source,
        "git_dir": repo.git_dir,
        "working_tree_dir": repo.working_tree_dir,
    }

    return GitInfo(
        commit=commit,
        branch=branch,
        remote_url=remote_url,
        extra=extra,
    )
