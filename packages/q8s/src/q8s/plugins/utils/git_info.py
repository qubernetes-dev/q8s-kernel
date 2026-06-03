import os
from dataclasses import dataclass
from typing import Optional

from git import InvalidGitRepositoryError, NoSuchPathError, Repo


@dataclass
class GitExtraInfo:
    """Additional Git information dataclass"""

    branch_source: Optional[str]
    git_dir: Optional[str]
    working_tree_dir: Optional[str]


@dataclass
class GitExtraReason:
    """Reason for missing Git information"""

    reason: str


@dataclass
class GitInfo:
    """Git information dataclass"""

    commit: Optional[str]
    branch: Optional[str]
    remote_url: Optional[str]
    extra: GitExtraInfo | GitExtraReason


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
            extra=GitExtraReason(reason="not_a_git_repo"),
        )

    # Commit SHA
    try:
        commit = repo.head.commit.hexsha
    except ValueError:
        commit = None

    # Branch (handle detached HEAD, CI environments, etc.)
    branch = None
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
            host, _, url_path = remote_url.partition(":")
            remote_url = f"https://{host.removeprefix('git@')}/{url_path}"
        elif remote_url.startswith("ssh://"):
            # ssh://git@github.com/org/repo.git -> https://github.com/org/repo.git
            stripped = remote_url.removeprefix("ssh://")
            if stripped.startswith("git@"):
                stripped = stripped.removeprefix("git@")
            host, _, url_path = stripped.partition("/")
            remote_url = f"https://{host}/{url_path}"
    except (AttributeError, IndexError, ValueError):
        remote_url = None

    extra = GitExtraInfo(
        branch_source=branch_source,
        git_dir=repo.git_dir,
        working_tree_dir=repo.working_tree_dir,
    )

    return GitInfo(
        commit=commit,
        branch=branch,
        remote_url=remote_url,
        extra=extra,
    )
