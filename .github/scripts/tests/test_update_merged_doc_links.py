# Copyright 2024-2026 Qubernetes
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import copy
import importlib.util
import unittest
from pathlib import Path
from unittest.mock import call, patch

spec = importlib.util.spec_from_file_location(
    "update_merged_doc_links",
    Path(__file__).resolve().parents[1] / "update-merged-doc-links.py",
)
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)

REPOSITORY = "qubernetes-dev/q8s-kernel"
ROOT = f"https://github.com/{REPOSITORY}/blob/"
PR = {
    "number": 42,
    "merged": True,
    "base": {"ref": "main", "repo": {"full_name": REPOSITORY}},
    "head": {"ref": "feature/targets", "repo": {"full_name": REPOSITORY}},
}


class TestRewriteLinks(unittest.TestCase):
    def test_updates_specs_and_adrs_preserving_markdown_and_anchors(self):
        body = (
            f"Problem description\n[Spec]({ROOT}feature/targets/"
            "doc/specs/target-validation.md#requirements)\n"
            f"[ADR]({ROOT}feature/targets/doc/adrs/0005-project-target-validation.md)"
        )
        expected = body.replace(f"{ROOT}feature/targets/", f"{ROOT}main/")
        self.assertEqual(sync.rewrite_links(body, PR), expected)
        self.assertEqual(sync.rewrite_links(expected, PR), expected)

    def test_updates_percent_encoded_branch_and_reference_style_links(self):
        body = f"[spec]: {ROOT}feature%2Ftargets/doc/specs/target-validation.md"
        self.assertEqual(
            sync.rewrite_links(body, PR),
            f"[spec]: {ROOT}main/doc/specs/target-validation.md",
        )

    def test_updates_fork_links_to_base_repository(self):
        pull_request = copy.deepcopy(PR)
        pull_request["head"]["repo"]["full_name"] = "contributor/q8s-kernel"
        body = (
            "https://github.com/contributor/q8s-kernel/blob/feature/targets/"
            "doc/specs/target-validation.md"
        )
        self.assertEqual(
            sync.rewrite_links(body, pull_request),
            f"{ROOT}main/doc/specs/target-validation.md",
        )

    def test_preserves_other_links_and_text(self):
        links = [
            f"{ROOT}main/doc/specs/target-validation.md",
            f"{ROOT}unrelated/doc/adrs/0005.md",
            f"{ROOT}feature/targets-extra/doc/specs/target-validation.md",
            f"{ROOT}feature/targets/README.md",
            f"{ROOT}feature/targets/packages/q8s/src/q8s/cli.py",
            "https://github.com/another/repo/blob/feature/targets/doc/specs/test.md",
            f"https://example.com/{ROOT}feature/targets/doc/specs/test.md",
            "Text mentioning feature/targets and doc/specs/target-validation.md",
        ]
        body = "\n".join(links)
        self.assertEqual(sync.rewrite_links(body, PR), body)

    def test_handles_deleted_head_repository(self):
        pull_request = copy.deepcopy(PR)
        pull_request["head"]["repo"] = None
        self.assertEqual(
            sync.rewrite_links(
                f"{ROOT}feature/targets/doc/specs/test.md", pull_request
            ),
            f"{ROOT}main/doc/specs/test.md",
        )


class TestIssueUpdates(unittest.TestCase):
    @patch.object(sync, "api_request")
    def test_paginates_linked_issues_and_ignores_other_repositories(self, api):
        def page(nodes, has_next, cursor):
            return {
                "data": {
                    "repository": {
                        "pullRequest": {
                            "closingIssuesReferences": {
                                "nodes": nodes,
                                "pageInfo": {
                                    "hasNextPage": has_next,
                                    "endCursor": cursor,
                                },
                            }
                        }
                    }
                }
            }

        api.side_effect = [
            page(
                [
                    {"number": 1, "repository": {"nameWithOwner": REPOSITORY}},
                    {"number": 2, "repository": {"nameWithOwner": "another/repo"}},
                ],
                True,
                "next",
            ),
            page(
                [
                    {"number": 3, "repository": {"nameWithOwner": REPOSITORY}},
                ],
                False,
                None,
            ),
        ]
        self.assertEqual(list(sync.linked_issues(REPOSITORY, 42)), [1, 3])
        self.assertIsNone(api.call_args_list[0].args[2]["variables"]["cursor"])
        self.assertEqual(api.call_args_list[1].args[2]["variables"]["cursor"], "next")

    @patch.object(sync, "api_request")
    @patch.object(sync, "linked_issues", return_value=[123])
    def test_patches_only_body_of_linked_issue(self, issues, api):
        body = f"Summary\n{ROOT}feature/targets/doc/specs/test.md"
        api.return_value = {"body": body}

        sync.update_issues({"action": "closed", "pull_request": PR})

        issues.assert_called_once_with(REPOSITORY, 42)
        self.assertEqual(
            api.call_args_list,
            [
                call("GET", f"/repos/{REPOSITORY}/issues/123"),
                call(
                    "PATCH",
                    f"/repos/{REPOSITORY}/issues/123",
                    {"body": f"Summary\n{ROOT}main/doc/specs/test.md"},
                ),
            ],
        )

    @patch.object(sync, "api_request")
    @patch.object(sync, "linked_issues", return_value=[123])
    def test_dry_run_does_not_write(self, issues, api):
        api.return_value = {"body": f"{ROOT}feature/targets/doc/adrs/test.md"}
        sync.update_issues({"action": "closed", "pull_request": PR}, dry_run=True)
        api.assert_called_once_with("GET", f"/repos/{REPOSITORY}/issues/123")

    @patch.object(sync, "api_request")
    @patch.object(sync, "linked_issues", return_value=[123])
    def test_does_not_patch_unchanged_or_empty_body(self, issues, api):
        for body in (None, "Description", f"{ROOT}main/doc/specs/test.md"):
            with self.subTest(body=body):
                api.reset_mock()
                api.return_value = {"body": body}
                sync.update_issues({"action": "closed", "pull_request": PR})
                api.assert_called_once_with("GET", f"/repos/{REPOSITORY}/issues/123")

    @patch.object(sync, "linked_issues")
    def test_skips_unmerged_prs_other_branches_and_other_events(self, issues):
        unmerged = copy.deepcopy(PR)
        unmerged["merged"] = False
        other_base = copy.deepcopy(PR)
        other_base["base"]["ref"] = "release"
        for event in (
            {"action": "closed", "pull_request": unmerged},
            {"action": "closed", "pull_request": other_base},
            {"action": "opened", "pull_request": PR},
            {},
        ):
            with self.subTest(event=event):
                sync.update_issues(event)
        issues.assert_not_called()


if __name__ == "__main__":
    unittest.main()
