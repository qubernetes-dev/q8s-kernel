from kubernetes import client
from git import Repo

import os


def get_git_info(path="."):
    repo = Repo(path, search_parent_directories=False)

    commit = repo.head.commit.hexsha
    branch = repo.active_branch.name if not repo.head.is_detached else None

    # remote may be missing (e.g., local-only repo)
    try:
        remote_url = repo.remotes.origin.url
    except Exception:
        remote_url = None

    return {
        "commit": commit,
        "branch": branch,
        "remote_url": remote_url,
    }


class JobPlugin:

    def patch_environment(self, env: list[client.V1EnvVar]) -> list[client.V1EnvVar]:
        """
        Patch environment variables for the job

        Args:
            env (list[client.V1EnvVar]): Original environment variables
        Returns:
            list[client.V1EnvVar]: Patched environment variables
        """

        git_info = get_git_info(os.getcwd())

        env.append(client.V1EnvVar(name="MLFLOW_GIT_COMMIT", value=git_info["commit"]))

        env.append(client.V1EnvVar(name="MLFLOW_GIT_BRANCH", value=git_info["branch"]))

        env.append(
            client.V1EnvVar(name="MLFLOW_GIT_REPO_URL", value=git_info["remote_url"])
        )
        env.append(client.V1EnvVar(name="GIT_PYTHON_REFRESH", value="quiet"))

        return env
