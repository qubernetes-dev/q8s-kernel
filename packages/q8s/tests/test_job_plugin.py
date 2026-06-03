import unittest
from unittest.mock import patch

from kubernetes import client

from q8s.plugins.job import JobPlugin
from q8s.plugins.utils.git_info import GitInfo


class TestJobPlugin(unittest.TestCase):

    @patch("q8s.plugins.job.get_git_info")
    @patch("q8s.plugins.job.os.getcwd")
    def test_patch_environment_appends_git_metadata(
        self,
        mock_getcwd,
        mock_get_git_info,
    ):
        mock_getcwd.return_value = "/tmp/repo"
        mock_get_git_info.return_value = GitInfo(
            commit="abc123",
            branch="main",
            remote_url="https://example.com/repo.git",
            extra={},
        )
        env = [client.V1EnvVar(name="EXISTING", value="1")]

        plugin = JobPlugin()
        result = plugin.patch_environment_with_git_info(env)

        self.assertIs(result, env)
        mock_get_git_info.assert_called_once_with("/tmp/repo")
        env_pairs = {(var.name, var.value) for var in env}
        self.assertIn(("Q8S_GIT_COMMIT", "abc123"), env_pairs)
        self.assertIn(("MLFLOW_GIT_COMMIT", "abc123"), env_pairs)
        self.assertIn(("Q8S_GIT_BRANCH", "main"), env_pairs)
        self.assertIn(("MLFLOW_GIT_BRANCH", "main"), env_pairs)
        self.assertIn(("Q8S_GIT_REPO_URL", "https://example.com/repo.git"), env_pairs)
        self.assertIn(
            ("MLFLOW_GIT_REPO_URL", "https://example.com/repo.git"), env_pairs
        )
        self.assertIn(("GIT_PYTHON_REFRESH", "quiet"), env_pairs)

    @patch("q8s.plugins.job.get_git_info")
    def test_patch_environment_handles_missing_git_metadata(self, mock_get_git_info):
        mock_get_git_info.return_value = GitInfo(
            commit=None,
            branch=None,
            remote_url=None,
            extra={"reason": "Not a git repository"},
        )
        env: list[client.V1EnvVar] = []

        plugin = JobPlugin()
        result = plugin.patch_environment_with_git_info(env)

        self.assertIs(result, env)
        self.assertEqual(
            [(var.name, var.value) for var in env], [("GIT_PYTHON_REFRESH", "quiet")]
        )


if __name__ == "__main__":
    unittest.main()
