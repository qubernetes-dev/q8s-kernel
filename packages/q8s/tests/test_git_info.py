import os
import tempfile
import unittest
from pathlib import Path

from git import Actor, Repo

from q8s.plugins.utils.git_info import (
    GitExtraInfo,
    GitExtraReason,
    _detect_branch_from_env,
    get_git_info,
)


class TestDetectBranchFromEnv(unittest.TestCase):

    def test_prefers_github_ref_name(self):
        with unittest.mock.patch.dict(
            os.environ,
            {
                "GITHUB_REF_NAME": "github-branch",
                "CI_COMMIT_REF_NAME": "gitlab-branch",
                "BRANCH_NAME": "generic-branch",
            },
            clear=True,
        ):
            self.assertEqual(_detect_branch_from_env(), "github-branch")

    def test_uses_gitlab_commit_ref_when_github_missing(self):
        with unittest.mock.patch.dict(
            os.environ,
            {"CI_COMMIT_REF_NAME": "gitlab-branch", "BRANCH_NAME": "generic-branch"},
            clear=True,
        ):
            self.assertEqual(_detect_branch_from_env(), "gitlab-branch")

    def test_falls_back_to_generic_branch_name(self):
        with unittest.mock.patch.dict(
            os.environ,
            {"BRANCH_NAME": "generic-branch"},
            clear=True,
        ):
            self.assertEqual(_detect_branch_from_env(), "generic-branch")

    def test_returns_none_when_no_env_vars_set(self):
        with unittest.mock.patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(_detect_branch_from_env())


class TestGetGitInfo(unittest.TestCase):

    def _create_repo_with_commit(self):
        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)
        repo = Repo.init(tempdir.name)
        file_path = Path(tempdir.name) / "tracked.txt"
        file_path.write_text("data\n", encoding="utf-8")
        repo.index.add([str(file_path)])
        actor = Actor("Tester", "tester@example.com")
        repo.index.commit("initial", author=actor, committer=actor)
        return tempdir.name, repo

    def test_returns_reason_when_path_not_repo(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            info = get_git_info(tmpdir)

        self.assertIsNone(info.commit)
        self.assertIsNone(info.branch)
        self.assertIsNone(info.remote_url)
        self.assertEqual(type(info.extra), GitExtraReason)
        self.assertEqual(info.extra.reason, "not_a_git_repo")

    def test_collects_repo_branch_commit_and_remote(self):
        path, repo = self._create_repo_with_commit()
        repo.create_remote("origin", "git@github.com:org/project.git")

        info = get_git_info(path)

        self.assertEqual(info.commit, repo.head.commit.hexsha)
        self.assertEqual(info.branch, repo.active_branch.name)
        self.assertEqual(info.remote_url, "https://github.com/org/project.git")
        self.assertEqual(type(info.extra), GitExtraInfo)
        self.assertEqual(info.extra.branch_source, "repo")
        self.assertEqual(info.extra.git_dir, repo.git_dir)
        self.assertEqual(info.extra.working_tree_dir, repo.working_tree_dir)

    def test_detached_head_uses_env_branch(self):
        path, repo = self._create_repo_with_commit()
        repo.git.checkout(repo.head.commit.hexsha)  # detach HEAD

        with unittest.mock.patch.dict(
            os.environ, {"GITHUB_REF_NAME": "ci-branch"}, clear=True
        ):
            info = get_git_info(path)

        self.assertEqual(info.branch, "ci-branch")
        self.assertEqual(info.extra.branch_source, "env")


if __name__ == "__main__":
    unittest.main()
