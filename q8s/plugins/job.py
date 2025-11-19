from kubernetes import client
from git import Repo

import os


from q8s.plugins.utils.git_info import get_git_info


class JobPlugin:

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
