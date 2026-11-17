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

import base64
import copy
import importlib.util
import io
import json
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import parse_qs, unquote, urlsplit

spec = importlib.util.spec_from_file_location(
    "scaffold_issue_docs",
    Path(__file__).resolve().parents[1] / "scaffold-issue-docs.py",
)
scaffold = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scaffold)

REPOSITORY = "qubernetes-dev/q8s-kernel"
PREFIX = f"/repos/{REPOSITORY}"
ISSUE = {
    "number": 123,
    "node_id": "I_issue123",
    "title": "Validate targets",
    "body": "Keep this description.",
    "html_url": f"https://github.com/{REPOSITORY}/issues/123",
    "state": "open",
    "labels": [{"name": "needs-spec"}, {"name": "needs-adr"}],
}
EVENT = {"action": "labeled", "label": {"name": "needs-spec"}, "issue": {"number": 123}}


class FakeGitHub:
    """Small in-memory Git database; all writes stay inside the test."""

    def __init__(self):
        self.issue = copy.deepcopy(ISSUE)
        self.refs = {"main": "base"}
        self.commits = {"base": {"tree": {"sha": "base-tree"}}}
        self.trees = {
            "base-tree": {
                "README.md": "Existing content",
                "doc/adrs/0005-existing.md": "Existing ADR",
            }
        }
        self.pulls = []
        self.linked_refs = []
        self.ahead_by = 1
        self.calls = []
        self.serial = 0
        self.default_branch_name = "123-validate-targets"

    def link_branch(self, branch, sha="base"):
        self.refs[branch] = sha
        self.linked_refs.append(
            {
                "ref": {
                    "name": branch,
                    "repository": {"nameWithOwner": REPOSITORY},
                }
            }
        )

    def files(self, branch):
        return self.trees[self.commits[self.refs[branch]]["tree"]["sha"]]

    def request(self, method, endpoint, payload=None):
        self.calls.append((method, endpoint, copy.deepcopy(payload)))
        path = unquote(endpoint.removeprefix(PREFIX))
        if path == "/graphql":
            if payload["query"] == scaffold.LINKED_BRANCHES_QUERY:
                assert payload["variables"]["owner"] == REPOSITORY.split("/")[0]
                assert payload["variables"]["name"] == REPOSITORY.split("/")[1]
                assert payload["variables"]["number"] == self.issue["number"]
                return {
                    "data": {
                        "repository": {
                            "issue": {
                                "linkedBranches": {
                                    "nodes": copy.deepcopy(self.linked_refs),
                                    "pageInfo": {
                                        "hasNextPage": False,
                                        "endCursor": None,
                                    },
                                }
                            }
                        }
                    }
                }
            if payload["query"] == scaffold.CREATE_LINKED_BRANCH:
                inputs = payload["variables"]["input"]
                name = inputs.get("name", self.default_branch_name)
                if name in self.refs:
                    return {"data": {"createLinkedBranch": {"linkedBranch": None}}}
                self.link_branch(name, inputs["oid"])
                return {
                    "data": {
                        "createLinkedBranch": {
                            "linkedBranch": {
                                "ref": {"name": name},
                            }
                        }
                    }
                }
            raise AssertionError(payload)
        if path == "/issues/123":
            if method == "PATCH":
                self.issue.update(payload)
            return copy.deepcopy(self.issue)
        if path.startswith("/git/ref/heads/"):
            branch = path.removeprefix("/git/ref/heads/")
            if branch not in self.refs:
                raise HTTPError(endpoint, 404, "Missing", {}, None)
            return {"object": {"sha": self.refs[branch]}}
        if path.startswith("/contents/"):
            query = parse_qs(urlsplit(endpoint).query)
            sha = query["ref"][0]
            if sha in self.commits:
                sha = self.commits[sha]["tree"]["sha"]
            name = urlsplit(path).path.removeprefix("/contents/")
            return {
                "encoding": "base64",
                "content": base64.b64encode(self.trees[sha][name].encode()).decode(),
            }
        if path.startswith("/git/trees/"):
            sha = path.split("/")[-1].split("?")[0]
            if sha in self.commits:
                sha = self.commits[sha]["tree"]["sha"]
            return {
                "tree": [{"path": name, "type": "blob"} for name in self.trees[sha]]
            }
        if path.startswith("/git/matching-refs/"):
            return [
                {"ref": f"refs/heads/{branch}", "object": {"sha": sha}}
                for branch, sha in self.refs.items()
            ]
        if method == "GET" and path.startswith("/git/commits/"):
            return self.commits[path.split("/")[-1]]
        if method == "POST" and path == "/git/trees":
            self.serial += 1
            sha = f"tree-{self.serial}"
            files = dict(self.trees[payload["base_tree"]])
            files.update({entry["path"]: entry["content"] for entry in payload["tree"]})
            self.trees[sha] = files
            return {"sha": sha}
        if method == "POST" and path == "/git/commits":
            sha = f"commit-{self.serial}"
            self.commits[sha] = {"tree": {"sha": payload["tree"]}}
            return {"sha": sha}
        if method == "POST" and path == "/git/refs":
            branch = payload["ref"].removeprefix("refs/heads/")
            self.refs[branch] = payload["sha"]
            return {}
        if method == "PATCH" and path.startswith("/git/refs/heads/"):
            assert payload["force"] is False
            self.refs[path.removeprefix("/git/refs/heads/")] = payload["sha"]
            return {}
        if method == "GET" and path.startswith("/compare/"):
            return {"ahead_by": self.ahead_by, "files": [{"filename": "docs.md"}]}
        if method == "GET" and path.startswith("/pulls?"):
            query = parse_qs(urlsplit(endpoint).query)
            return [
                dict(
                    pull, head={"ref": pull["head"], "repo": {"full_name": REPOSITORY}}
                )
                for pull in self.pulls
                if "head" not in query
                or query["head"] == [f"{REPOSITORY.split('/')[0]}:{pull['head']}"]
            ]
        if method == "POST" and path == "/pulls":
            self.pulls.append(copy.deepcopy(payload))
            return payload
        raise AssertionError((method, path, payload))


class TestGitHubRequests(unittest.TestCase):
    def test_linked_branch_http_request_supplies_repository_name(self):
        response = {
            "data": {
                "repository": {
                    "issue": {
                        "linkedBranches": {
                            "nodes": [],
                            "pageInfo": {"hasNextPage": False, "endCursor": None},
                        }
                    }
                }
            }
        }
        with patch.dict("os.environ", {"GITHUB_TOKEN": "test-token"}):
            with patch.object(
                scaffold,
                "urlopen",
                return_value=io.BytesIO(json.dumps(response).encode()),
            ) as urlopen:
                self.assertIsNone(scaffold.linked_issue_branch("vstirbu/test-ddlc", 1))
        request = urlopen.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(request.method, "POST")
        self.assertEqual(payload["query"], scaffold.LINKED_BRANCHES_QUERY)
        self.assertEqual(
            payload["variables"],
            {
                "owner": "vstirbu",
                "name": "test-ddlc",
                "number": 1,
                "cursor": None,
            },
        )

    def test_branch_creation_http_request_uses_number_and_slug(self):
        response = {
            "data": {
                "createLinkedBranch": {
                    "linkedBranch": {
                        "ref": {"name": "123-validate-targets"},
                    }
                }
            }
        }
        with patch.dict("os.environ", {"GITHUB_TOKEN": "test-token"}):
            with patch.object(
                scaffold,
                "urlopen",
                return_value=io.BytesIO(json.dumps(response).encode()),
            ) as urlopen:
                self.assertEqual(
                    scaffold.create_issue_branch(ISSUE, "head-sha"),
                    "123-validate-targets",
                )
        payload = json.loads(urlopen.call_args.args[0].data)
        self.assertEqual(payload["query"], scaffold.CREATE_LINKED_BRANCH)
        self.assertEqual(
            payload["variables"]["input"],
            {
                "issueId": ISSUE["node_id"],
                "oid": "head-sha",
                "name": "123-validate-targets",
            },
        )


class TestPlanning(unittest.TestCase):
    def test_templates_follow_conventions_and_cross_link(self):
        docs, additions = scaffold.plan_documents(
            ISSUE, ["spec", "adr"], set(), {"doc/adrs/0012-existing.md"}, "2026-11-17"
        )
        self.assertEqual(docs["spec"], "doc/specs/validate-targets.md")
        self.assertEqual(docs["adr"], "doc/adrs/0013-validate-targets.md")
        self.assertIn('summary: "Validate targets"', additions[docs["spec"]])
        self.assertIn("Status: Draft", additions[docs["spec"]])
        self.assertIn("../adrs/0013-validate-targets.md", additions[docs["spec"]])
        self.assertIn("../specs/validate-targets.md", additions[docs["adr"]])
        self.assertIn("Date: 2026-11-17", additions[docs["adr"]])
        self.assertIn("Proposed", additions[docs["adr"]])

    def test_title_changes_do_not_duplicate_existing_documents(self):
        paths = {"doc/specs/original.md", "doc/adrs/0006-original.md"}
        docs, additions = scaffold.plan_documents(
            ISSUE,
            ["spec", "adr"],
            paths,
            paths,
            "today",
            {"doc/adrs/0006-original.md": 123, "doc/specs/original.md": 123},
        )
        self.assertEqual(set(docs.values()), paths)
        self.assertEqual(additions, {})

    def test_new_adrs_store_issue_in_metadata_instead_of_filename(self):
        docs, additions = scaffold.plan_documents(ISSUE, ["adr"], set(), set(), "today")
        self.assertEqual(docs["adr"], "doc/adrs/0001-validate-targets.md")
        self.assertTrue(additions[docs["adr"]].startswith("---\nissue: 123\n---\n"))

    def test_legacy_adr_filenames_remain_recognized_without_renaming(self):
        path = "doc/adrs/0006-issue-123-original.md"
        docs, additions = scaffold.plan_documents(
            ISSUE, ["adr"], {path}, {path}, "today"
        )
        self.assertEqual(docs["adr"], path)
        self.assertEqual(additions, {})

    def test_multiple_adrs_for_same_issue_fail_instead_of_picking_one(self):
        paths = {"doc/adrs/0006-first.md", "doc/adrs/0007-second.md"}
        with self.assertRaisesRegex(RuntimeError, "Multiple adr documents"):
            scaffold.plan_documents(
                ISSUE, ["adr"], paths, paths, "today", {path: 123 for path in paths}
            )

    def test_new_specs_use_metadata_without_issue_number_in_filename(self):
        docs, additions = scaffold.plan_documents(
            ISSUE, ["spec"], set(), set(), "today"
        )
        self.assertEqual(docs["spec"], "doc/specs/validate-targets.md")
        self.assertTrue(additions[docs["spec"]].startswith("---\nissue: 123\n"))

    def test_legacy_spec_filenames_remain_recognized(self):
        path = "doc/specs/123-original.md"
        docs, additions = scaffold.plan_documents(
            ISSUE, ["spec"], {path}, {path}, "today"
        )
        self.assertEqual(docs["spec"], path)
        self.assertEqual(additions, {})

    def test_spec_filename_collision_does_not_reuse_another_issues_document(self):
        path = "doc/specs/validate-targets.md"
        for metadata in ({}, {path: 456}):
            with self.subTest(metadata=metadata):
                with self.assertRaisesRegex(RuntimeError, "filename is already in use"):
                    scaffold.plan_documents(
                        ISSUE, ["spec"], {path}, {path}, "today", metadata
                    )

    def test_slug_and_summary_treat_title_as_data(self):
        issue = dict(ISSUE, title='Fix "target": $(echo dangerous) `command`')
        docs, additions = scaffold.plan_documents(
            issue, ["spec"], set(), set(), "today"
        )
        summary = additions[docs["spec"]].splitlines()[2].removeprefix("summary: ")
        self.assertEqual(json.loads(summary), issue["title"])
        self.assertEqual(scaffold.slugify("!!!"), "change")
        self.assertNotIn("$", docs["spec"])

    def test_issue_links_preserve_body_and_are_idempotent(self):
        docs = {"spec": "doc/specs/123-test.md"}
        body = scaffold.add_issue_links(
            "Original", docs, REPOSITORY, "123-validate-targets", "https://github.com"
        )
        self.assertTrue(body.startswith("Original\n\n"))
        self.assertIn("/blob/123-validate-targets/doc/specs/123-test.md", body)
        self.assertEqual(
            body,
            scaffold.add_issue_links(
                body, docs, REPOSITORY, "123-validate-targets", "https://github.com"
            ),
        )


class TestScaffolding(unittest.TestCase):
    def setUp(self):
        self.github = FakeGitHub()
        self.env = patch.dict("os.environ", {"GITHUB_REPOSITORY": REPOSITORY})
        self.api = patch.object(
            scaffold, "api_request", side_effect=self.github.request
        )
        self.env.start()
        self.api.start()
        self.addCleanup(self.env.stop)
        self.addCleanup(self.api.stop)

    def test_branch_creation_explicitly_uses_number_and_slug(self):
        self.github.default_branch_name = "123-GitHub-selected-name"
        scaffold.scaffold(EVENT)
        self.assertIn("123-validate-targets", self.github.refs)
        self.assertEqual(self.github.pulls[0]["head"], "123-validate-targets")
        mutations = [
            payload
            for _, _, payload in self.github.calls
            if payload and payload.get("query") == scaffold.CREATE_LINKED_BRANCH
        ]
        self.assertEqual(len(mutations), 1)
        self.assertEqual(
            mutations[0]["variables"]["input"],
            {
                "issueId": ISSUE["node_id"],
                "oid": "base",
                "name": "123-validate-targets",
            },
        )

    def test_both_labels_create_shared_branch_and_one_draft_pr(self):
        scaffold.scaffold(EVENT)
        files = self.github.files("123-validate-targets")
        self.assertIn("doc/specs/validate-targets.md", files)
        self.assertIn("doc/adrs/0006-validate-targets.md", files)
        self.assertEqual(files["README.md"], "Existing content")
        pr = self.github.pulls[0]
        self.assertEqual(pr["head"], "123-validate-targets")
        self.assertEqual(pr["base"], "main")
        self.assertEqual(pr["title"], "feat: Validate targets")
        self.assertTrue(pr["draft"])
        self.assertIn(f"Related issue: [#123]({ISSUE['html_url']})", pr["body"])
        self.assertIn("TODO: Describe the changes.", pr["body"])
        self.assertNotRegex(pr["body"].lower(), r"(?:closes|fixes|resolves) #123")
        self.assertIn("Specification:", self.github.issue["body"])
        self.assertIn("ADR:", self.github.issue["body"])
        self.assertEqual(self.github.issue["state"], "open")

    def test_reuses_issue_linked_branch_regardless_of_its_name(self):
        for branch in (
            "70-sdlc-scaffolding",
            "work/quantum#validation",
            "arbitrary-name",
        ):
            with self.subTest(branch=branch):
                github = FakeGitHub()
                github.link_branch(branch)
                with patch.object(scaffold, "api_request", side_effect=github.request):
                    scaffold.scaffold(EVENT)
                self.assertEqual(set(github.refs), {"main", branch})
                self.assertIn("doc/specs/validate-targets.md", github.files(branch))
                self.assertEqual(github.pulls[0]["head"], branch)
                self.assertFalse(
                    any(
                        payload
                        and payload.get("query") == scaffold.CREATE_LINKED_BRANCH
                        for _, _, payload in github.calls
                    )
                )

    def test_renaming_linked_branch_preserves_document_edits_and_pr(self):
        scaffold.scaffold(EVENT)
        github = self.github
        files = github.files("123-validate-targets")
        files["doc/specs/validate-targets.md"] = (
            "---\nissue: 123\n---\nEdited before rename"
        )
        github.refs["new-branch-name"] = github.refs.pop("123-validate-targets")
        github.linked_refs[0]["ref"]["name"] = "new-branch-name"
        github.pulls[0]["head"] = "new-branch-name"
        scaffold.scaffold(EVENT)
        self.assertEqual(
            files["doc/specs/validate-targets.md"],
            "---\nissue: 123\n---\nEdited before rename",
        )
        self.assertEqual(len(github.pulls), 1)
        self.assertIn("/blob/new-branch-name/", github.issue["body"])

    def test_renamed_adr_is_found_by_metadata_and_preserved(self):
        scaffold.scaffold(EVENT)
        files = self.github.files("123-validate-targets")
        old = "doc/adrs/0006-validate-targets.md"
        renamed = "doc/adrs/0006-reviewers-preferred-title.md"
        files[renamed] = files.pop(old) + "\nReviewed content\n"
        self.github.issue["title"] = "Different issue title"
        scaffold.scaffold(EVENT)
        self.assertNotIn(old, files)
        self.assertTrue(files[renamed].endswith("Reviewed content\n"))
        self.assertEqual(
            len([path for path in files if path.startswith("doc/adrs/0006-")]), 1
        )

    def test_invalid_adr_issue_metadata_stops_instead_of_creating_duplicate(self):
        self.github.trees["base-tree"][
            "doc/adrs/0006-original.md"
        ] = "---\nissue: not-a-number\n---\nDecision"
        with self.assertRaisesRegex(
            RuntimeError, "single positive integer issue field"
        ):
            scaffold.scaffold(EVENT)
        self.assertEqual(self.github.serial, 0)

    def test_renamed_spec_is_found_by_metadata_and_preserved(self):
        scaffold.scaffold(EVENT)
        files = self.github.files("123-validate-targets")
        old = "doc/specs/validate-targets.md"
        renamed = "doc/specs/custom-specification-name.md"
        files[renamed] = files.pop(old) + "\nReviewed specification\n"
        self.github.issue["title"] = "New feature name"
        scaffold.scaffold(EVENT)
        self.assertNotIn(old, files)
        self.assertNotIn("doc/specs/new-feature-name.md", files)
        self.assertTrue(files[renamed].endswith("Reviewed specification\n"))
        self.assertIn(
            "/doc/specs/custom-specification-name.md", self.github.issue["body"]
        )

    def test_existing_spec_on_main_is_recognized_from_metadata(self):
        files = self.github.trees["base-tree"]
        files["doc/specs/target-validation.md"] = (
            "---\nissue: 123\n---\nExisting behavior"
        )
        self.github.issue["labels"] = [{"name": "needs-spec"}]
        scaffold.scaffold(EVENT)
        self.assertEqual(self.github.serial, 0)
        self.assertFalse(self.github.pulls)
        self.assertIn(
            "/blob/main/doc/specs/target-validation.md", self.github.issue["body"]
        )

    def test_multiple_linked_branches_fail_before_any_files_are_written(self):
        self.github.link_branch("first-branch")
        self.github.link_branch("second-branch")
        with self.assertRaisesRegex(RuntimeError, "Multiple branches"):
            scaffold.scaffold(EVENT)
        self.assertEqual(self.github.serial, 0)
        self.assertFalse(self.github.pulls)
        self.assertEqual(self.github.issue["body"], ISSUE["body"])

    def test_link_to_main_is_rejected_before_writing(self):
        self.github.link_branch("main")
        with self.assertRaisesRegex(RuntimeError, "linked to main"):
            scaffold.scaffold(EVENT)
        self.assertEqual(self.github.serial, 0)

    def test_unlinked_branch_with_same_generated_name_is_not_overwritten(self):
        self.github.refs["123-validate-targets"] = "base"
        with self.assertRaisesRegex(
            RuntimeError, "Select the intended existing branch"
        ):
            scaffold.scaffold(EVENT)
        self.assertEqual(self.github.refs["123-validate-targets"], "base")
        self.assertEqual(self.github.serial, 0)

    def test_second_label_recovers_existing_pr_when_branch_association_is_missing(self):
        self.github.issue["labels"] = [{"name": "needs-spec"}]
        self.github.link_branch("work/any-name")
        scaffold.scaffold(EVENT)
        files = self.github.files("work/any-name")
        files["doc/specs/validate-targets.md"] = "---\nissue: 123\n---\nEdited"
        self.github.linked_refs = []
        self.github.issue["labels"].append({"name": "needs-adr"})
        self.github.issue["title"] = "New issue title"
        self.github.pulls[0]["title"] = "Contributor updated PR title"
        self.github.calls.clear()
        scaffold.scaffold(dict(EVENT, label={"name": "needs-adr"}))
        files = self.github.files("work/any-name")
        self.assertEqual(
            files["doc/specs/validate-targets.md"], "---\nissue: 123\n---\nEdited"
        )
        self.assertIn("doc/adrs/0006-new-issue-title.md", files)
        self.assertEqual(len(self.github.pulls), 1)
        self.assertEqual(self.github.pulls[0]["title"], "Contributor updated PR title")
        self.assertFalse(
            any(
                payload and payload.get("query") == scaffold.CREATE_LINKED_BRANCH
                for _, _, payload in self.github.calls
            )
        )

    def test_null_branch_creation_payloads_report_actionable_error(self):
        for result in (
            {"createLinkedBranch": None},
            {"createLinkedBranch": {"linkedBranch": None}},
            {"createLinkedBranch": {"linkedBranch": {"ref": None}}},
            {"createLinkedBranch": {"linkedBranch": {"ref": {"name": None}}}},
        ):
            with self.subTest(result=result):
                with patch.object(scaffold, "graphql", return_value=result):
                    with self.assertRaisesRegex(
                        RuntimeError, "GitHub did not return a branch"
                    ):
                        scaffold.create_issue_branch(ISSUE, "base")

    def test_pr_recovery_ignores_unrelated_issue_references(self):
        self.github.pulls.append(
            {
                "title": "Unrelated change",
                "head": "unrelated-branch",
                "base": "main",
                "body": "Related issue: #123",
            }
        )
        self.assertIsNone(scaffold.scaffold_pr_branch(REPOSITORY, 123))

    def test_multiple_scaffolding_prs_fail_before_any_files_are_written(self):
        for branch in ("first-branch", "second-branch"):
            self.github.pulls.append(
                {
                    "title": "Draft",
                    "head": branch,
                    "base": "main",
                    "body": scaffold.pull_request_marker(123),
                }
            )
        with self.assertRaisesRegex(RuntimeError, "Multiple scaffolding PR"):
            scaffold.scaffold(EVENT)
        self.assertEqual(self.github.serial, 0)

    def test_pr_recovery_paginates_and_ignores_foreign_heads(self):
        unrelated = {"body": "Unrelated", "head": {"ref": "irrelevant"}}
        foreign = {
            "body": scaffold.pull_request_marker(123),
            "head": {"ref": "fork-branch", "repo": {"full_name": "someone/fork"}},
        }
        local = {
            "body": scaffold.pull_request_marker(123),
            "head": {"ref": "70-sdlc-scaffolding", "repo": {"full_name": REPOSITORY}},
        }
        with patch.object(
            scaffold,
            "api_request",
            side_effect=[
                [unrelated] * 99 + [foreign],
                [local],
            ],
        ) as api:
            self.assertEqual(
                scaffold.scaffold_pr_branch(REPOSITORY, 123), "70-sdlc-scaffolding"
            )
        self.assertIn("page=2", api.call_args_list[1].args[1])

    def test_reapplying_labels_does_not_write_or_overwrite_edits(self):
        scaffold.scaffold(EVENT)
        self.github.pulls[0]["title"] = "fix: contributor-chosen title"
        files = self.github.files("123-validate-targets")
        files["doc/specs/validate-targets.md"] = (
            "---\nissue: 123\n---\nContributor edits"
        )
        self.github.calls.clear()
        scaffold.scaffold(EVENT)
        writes = [
            call
            for call in self.github.calls
            if call[0] != "GET"
            and not (
                call[1] == "/graphql"
                and call[2]["query"] == scaffold.LINKED_BRANCHES_QUERY
            )
        ]
        self.assertEqual(writes, [])
        self.assertEqual(
            files["doc/specs/validate-targets.md"],
            "---\nissue: 123\n---\nContributor edits",
        )
        self.assertEqual(len(self.github.pulls), 1)

    def test_adding_second_label_reuses_branch_pr_and_preserves_first_document(self):
        self.github.issue["labels"] = [{"name": "needs-spec"}]
        scaffold.scaffold(EVENT)
        self.github.files("123-validate-targets")[
            "doc/specs/validate-targets.md"
        ] = "---\nissue: 123\n---\nEdited"
        self.github.issue["labels"].append({"name": "needs-adr"})
        self.github.issue["title"] = "Updated title"
        scaffold.scaffold(EVENT)
        files = self.github.files("123-validate-targets")
        self.assertEqual(
            files["doc/specs/validate-targets.md"], "---\nissue: 123\n---\nEdited"
        )
        self.assertIn(
            "../specs/validate-targets.md",
            files["doc/adrs/0006-updated-title.md"],
        )
        self.assertEqual(len(self.github.pulls), 1)

    def test_adr_first_then_spec_preserves_adr_and_reuses_its_number(self):
        self.github.issue["labels"] = [{"name": "needs-adr"}]
        scaffold.scaffold(dict(EVENT, label={"name": "needs-adr"}))
        files = self.github.files("123-validate-targets")
        adr = "doc/adrs/0006-validate-targets.md"
        files[adr] = "---\nissue: 123\n---\nReviewed architectural decision"
        self.github.issue["labels"].append({"name": "needs-spec"})
        scaffold.scaffold(EVENT)
        files = self.github.files("123-validate-targets")
        self.assertEqual(
            files[adr], "---\nissue: 123\n---\nReviewed architectural decision"
        )
        self.assertIn(
            "../adrs/0006-validate-targets.md",
            files["doc/specs/validate-targets.md"],
        )
        self.assertIn(
            "> Keep this description.", files["doc/specs/validate-targets.md"]
        )
        self.assertEqual(len(self.github.pulls), 1)

    def test_retry_after_pr_creation_failure_reuses_committed_documents(self):
        def fail_pr(method, path, payload=None):
            if method == "POST" and path == f"{PREFIX}/pulls":
                raise HTTPError(path, 403, "PR creation disabled", {}, None)
            return self.github.request(method, path, payload)

        with patch.object(scaffold, "api_request", side_effect=fail_pr):
            with self.assertRaises(HTTPError):
                scaffold.scaffold(EVENT)
        sha = self.github.refs["123-validate-targets"]
        scaffold.scaffold(EVENT)
        self.assertEqual(self.github.refs["123-validate-targets"], sha)
        self.assertEqual(len(self.github.pulls), 1)
        self.assertIn("Specification:", self.github.issue["body"])

    def test_concurrent_branch_edit_fails_without_force_update_or_issue_patch(self):
        self.github.issue["labels"] = [{"name": "needs-spec"}]
        scaffold.scaffold(EVENT)
        sha = self.github.refs["123-validate-targets"]
        self.github.issue["labels"].append({"name": "needs-adr"})
        self.github.calls.clear()

        def reject_update(method, path, payload=None):
            if method == "PATCH" and "/git/refs/" in path:
                self.assertIs(payload["force"], False)
                raise HTTPError(path, 422, "Not a fast forward", {}, None)
            return self.github.request(method, path, payload)

        with patch.object(scaffold, "api_request", side_effect=reject_update):
            with self.assertRaises(HTTPError):
                scaffold.scaffold(EVENT)
        self.assertEqual(self.github.refs["123-validate-targets"], sha)
        self.assertFalse(any(method == "PATCH" for method, _, _ in self.github.calls))

    def test_adr_allocation_accounts_for_main_and_unmerged_issue_branches(self):
        self.github.refs["architecture/new-runtime"] = "other"
        self.github.commits["other"] = {"tree": {"sha": "other-tree"}}
        self.github.trees["other-tree"] = {"doc/adrs/0009-other.md": "Reserved"}
        scaffold.scaffold(EVENT)
        self.assertIn(
            "doc/adrs/0010-validate-targets.md",
            self.github.files("123-validate-targets"),
        )

    def test_manual_retry_repairs_issue_links_without_duplicate_commit_or_pr(self):
        scaffold.scaffold(EVENT)
        self.github.issue["body"] = "Updated issue text"
        sha = self.github.refs["123-validate-targets"]
        scaffold.scaffold({}, "123")
        self.assertEqual(self.github.refs["123-validate-targets"], sha)
        self.assertEqual(len(self.github.pulls), 1)
        self.assertTrue(self.github.issue["body"].startswith("Updated issue text"))
        self.assertIn("ADR:", self.github.issue["body"])

    def test_documents_already_on_main_do_not_create_empty_pr(self):
        self.github.trees["base-tree"].update(
            {
                "doc/specs/existing.md": "---\nissue: 123\n---\nImplemented spec",
                "doc/adrs/0006-existing.md": "---\nissue: 123\n---\nAccepted ADR",
            }
        )
        scaffold.scaffold(EVENT)
        self.assertEqual(self.github.refs, {"main": "base"})
        self.assertFalse(self.github.pulls)
        self.assertIn("/blob/main/doc/specs/existing.md", self.github.issue["body"])

    def test_merged_branch_is_not_reopened_when_it_has_no_new_changes(self):
        scaffold.scaffold(EVENT)
        self.github.pulls.clear()
        self.github.ahead_by = 0
        scaffold.scaffold(EVENT)
        self.assertFalse(self.github.pulls)
        self.assertIn(
            "/blob/main/doc/specs/validate-targets.md", self.github.issue["body"]
        )

    def test_ignores_other_events_unrelated_labels_closed_issues_and_prs(self):
        scaffold.scaffold({})
        scaffold.scaffold(dict(EVENT, label={"name": "bug"}))
        self.assertFalse(self.github.calls)
        for issue in (
            dict(ISSUE, state="closed"),
            dict(ISSUE, pull_request={}),
            dict(ISSUE, labels=[]),
        ):
            self.github.issue = issue
            self.github.calls.clear()
            scaffold.scaffold(EVENT)
            self.assertEqual([method for method, _, _ in self.github.calls], ["GET"])

    def test_linked_branch_query_paginates_and_ignores_deleted_and_foreign_refs(self):
        def connection(nodes, has_next, cursor):
            return {
                "data": {
                    "repository": {
                        "issue": {
                            "linkedBranches": {
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

        foreign = {
            "ref": {"name": "fork-work", "repository": {"nameWithOwner": "fork/repo"}}
        }
        local = {
            "ref": {
                "name": "70-sdlc-scaffolding",
                "repository": {"nameWithOwner": REPOSITORY},
            }
        }
        with patch.object(
            scaffold,
            "api_request",
            side_effect=[
                connection([{"ref": None}, foreign], True, "next-page"),
                connection([local], False, None),
            ],
        ) as api:
            self.assertEqual(
                scaffold.linked_issue_branch(REPOSITORY, 123), "70-sdlc-scaffolding"
            )
        self.assertIsNone(api.call_args_list[0].args[2]["variables"]["cursor"])
        self.assertEqual(
            api.call_args_list[1].args[2]["variables"]["cursor"], "next-page"
        )

    def test_graphql_errors_stop_branch_discovery(self):
        with patch.object(
            scaffold, "api_request", return_value={"errors": [{"message": "Denied"}]}
        ):
            with self.assertRaisesRegex(RuntimeError, "GraphQL request failed"):
                scaffold.linked_issue_branch(REPOSITORY, 123)

    def test_permission_errors_are_not_treated_as_missing_branch(self):
        with patch.object(
            scaffold,
            "api_request",
            side_effect=HTTPError("url", 403, "Forbidden", {}, None),
        ):
            with self.assertRaises(HTTPError):
                scaffold.optional_get("/ref")

    def test_truncated_trees_fail_instead_of_overwriting_undiscovered_files(self):
        with patch.object(scaffold, "api_request", return_value={"truncated": True}):
            with self.assertRaises(RuntimeError):
                scaffold.tree_paths(PREFIX, "sha")


if __name__ == "__main__":
    unittest.main()
