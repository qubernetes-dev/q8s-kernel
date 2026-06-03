import os

from kubernetes import client

from q8s.plugins.utils.git_info import get_git_info


class JobPlugin:
    """
    Base class for job template plugins.
    This class provides functionality to patch job environment variables with Git information,
    such as commit hash, branch name, and remote repository URL. It is intended to be extended
    by specific job plugins that require Git metadata in their execution environment.
    The following environment variables are added:
        - Q8S_GIT_COMMIT, MLFLOW_GIT_COMMIT: The current Git commit hash.
        - Q8S_GIT_BRANCH, MLFLOW_GIT_BRANCH: The current Git branch name.
        - Q8S_GIT_REPO_URL, MLFLOW_GIT_REPO_URL: The remote repository URL.
        - GIT_PYTHON_REFRESH: Set to "quiet" to suppress GitPython refresh warnings.
    """

    def patch_environment_with_git_info(
        self, env: list[client.V1EnvVar]
    ) -> list[client.V1EnvVar]:
        """
        Patch environment variables for the job with Git information

        Args:
            env (list[client.V1EnvVar]): Original environment variables
        Returns:
            list[client.V1EnvVar]: Patched environment variables
        """

        # Get Git information from the q8sctl current working directory
        git_info = get_git_info(os.getcwd())

        if git_info.commit:
            env.append(client.V1EnvVar(name="Q8S_GIT_COMMIT", value=git_info.commit))
            env.append(client.V1EnvVar(name="MLFLOW_GIT_COMMIT", value=git_info.commit))

        if git_info.branch:
            env.append(client.V1EnvVar(name="Q8S_GIT_BRANCH", value=git_info.branch))
            env.append(client.V1EnvVar(name="MLFLOW_GIT_BRANCH", value=git_info.branch))

        if git_info.remote_url:
            env.append(
                client.V1EnvVar(name="Q8S_GIT_REPO_URL", value=git_info.remote_url)
            )
            env.append(
                client.V1EnvVar(name="MLFLOW_GIT_REPO_URL", value=git_info.remote_url)
            )

        env.append(client.V1EnvVar(name="GIT_PYTHON_REFRESH", value="quiet"))

        return env
