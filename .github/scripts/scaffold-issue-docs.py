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

"""Scaffold issue documentation on its linked branch using the GitHub API."""

import base64
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from string import Template
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

TEMPLATES = Path(__file__).with_name("templates")
LABELS = {"needs-spec": "spec", "needs-adr": "adr"}


LINKED_BRANCHES_QUERY = """
query($owner: String!, $name: String!, $number: Int!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    issue(number: $number) {
      linkedBranches(first: 100, after: $cursor) {
        nodes { ref { name repository { nameWithOwner } } }
        pageInfo { hasNextPage endCursor }
      }
    }
  }
}
"""

CREATE_LINKED_BRANCH = """
mutation($input: CreateLinkedBranchInput!) {
  createLinkedBranch(input: $input) {
    linkedBranch { ref { name } }
  }
}
"""


def api_request(method, path, payload=None):
    request = Request(
        os.environ.get("GITHUB_API_URL", "https://api.github.com") + path,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={
            "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
        },
        method=method,
    )
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def optional_get(path):
    try:
        return api_request("GET", path)
    except HTTPError as error:
        if error.code != 404:
            raise
        return None


def graphql(query, variables):
    result = api_request("POST", "/graphql", {"query": query, "variables": variables})
    if result.get("errors"):
        raise RuntimeError(f"GitHub GraphQL request failed: {result['errors']}")
    return result["data"]


def linked_issue_branch(repository, number):
    owner, name = repository.split("/")
    cursor = None
    branches = set()
    while True:
        data = graphql(
            LINKED_BRANCHES_QUERY,
            {
                "owner": owner,
                "name": name,
                "number": number,
                "cursor": cursor,
            },
        )
        connection = data["repository"]["issue"]["linkedBranches"]
        for node in connection["nodes"]:
            ref = node["ref"]
            if ref and ref["repository"]["nameWithOwner"] == repository:
                branches.add(ref["name"])
        if not connection["pageInfo"]["hasNextPage"]:
            break
        cursor = connection["pageInfo"]["endCursor"]
    if "main" in branches:
        raise RuntimeError(
            "The issue is linked to main; link a development branch instead"
        )
    if len(branches) > 1:
        raise RuntimeError(
            "Multiple branches are linked to this issue: "
            + ", ".join(sorted(branches))
            + ". Keep one development branch linked before retrying."
        )
    return next(iter(branches), None)


def pull_request_marker(number):
    return f"<!-- q8s-scaffolding issue={number} -->"


def scaffold_pr_branch(repository, number):
    """Recover the existing scaffolding PR when no branch association is returned."""
    branches = set()
    page = 1
    while True:
        query = urlencode(
            {"state": "open", "base": "main", "per_page": 100, "page": page}
        )
        pulls = api_request("GET", f"/repos/{repository}/pulls?{query}")
        for pull in pulls:
            body = pull.get("body") or ""
            if pull_request_marker(number) not in body:
                continue
            head = pull["head"]
            if (head.get("repo") or {}).get("full_name") == repository and head[
                "ref"
            ] != "main":
                branches.add(head["ref"])
        if len(pulls) < 100:
            break
        page += 1
    if len(branches) > 1:
        raise RuntimeError(
            "Multiple scaffolding PR branches found for this issue; resolve them first"
        )
    return next(iter(branches), None)


def create_issue_branch(issue, sha):
    name = f"{issue['number']}-{slugify(issue['title'])}"
    data = graphql(
        CREATE_LINKED_BRANCH,
        {
            "input": {
                "issueId": issue["node_id"],
                "oid": sha,
                "name": name,
            }
        },
    )
    created = (data or {}).get("createLinkedBranch") or {}
    linked = created.get("linkedBranch") or {}
    ref = linked.get("ref") or {}
    if not ref.get("name"):
        raise RuntimeError(
            f"GitHub did not return a branch for issue #{issue['number']}. "
            "The branch may already exist. Select the intended existing branch in the "
            "issue's Development section, then rerun the workflow."
        )
    print(f"Issue #{issue['number']}: created branch {ref['name']}")
    return ref["name"]


def tree_paths(prefix, sha):
    tree = api_request("GET", f"{prefix}/git/trees/{sha}?recursive=1")
    if tree.get("truncated"):
        raise RuntimeError(
            "Repository tree is truncated; refusing incomplete document discovery"
        )
    return {entry["path"] for entry in tree["tree"] if entry["type"] == "blob"}


def document_issue_metadata(prefix, sha, paths):
    issues = {}
    for path in sorted(paths):
        if not re.fullmatch(r"doc/(?:adrs/\d+-|specs/)[^/]+\.md", path):
            continue
        query = urlencode({"ref": sha})
        document = api_request(
            "GET", f"{prefix}/contents/{quote(path, safe='/')}?{query}"
        )
        if document.get("encoding") != "base64":
            raise RuntimeError(f"Cannot read document metadata from {path}")
        text = base64.b64decode(document["content"]).decode("utf-8-sig")
        front_matter = re.match(r"---\r?\n(.*?)\r?\n---(?:\r?\n|$)", text, re.DOTALL)
        if front_matter is None:
            continue
        issue_fields = re.findall(r"^issue:[ \t]*(.*)$", front_matter[1], re.MULTILINE)
        if not issue_fields:
            continue
        if len(issue_fields) != 1 or not re.fullmatch(
            r"[1-9]\d*", issue_fields[0].strip()
        ):
            raise RuntimeError(
                f"Document {path} must have a single positive integer issue field"
            )
        issues[path] = int(issue_fields[0])
    return issues


def slugify(title):
    return (
        re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:80].rstrip("-")
        or "change"
    )


def find_document(paths, kind, number, document_issues=None):
    if kind == "spec":
        pattern = rf"doc/specs/{number}-[^/]+\.md"
    else:
        pattern = rf"doc/adrs/\d+-issue-{number}-[^/]+\.md"
    directory = "doc/specs/" if kind == "spec" else "doc/adrs/"
    matches = sorted(
        path
        for path in paths
        if (path.startswith(directory) and (document_issues or {}).get(path) == number)
        or (path not in (document_issues or {}) and re.fullmatch(pattern, path))
    )
    if len(matches) > 1:
        raise RuntimeError(f"Multiple {kind} documents found for issue #{number}")
    return matches[0] if matches else None


def next_adr_number(paths):
    numbers = [
        int(match[1])
        for path in paths
        if (match := re.fullmatch(r"doc/adrs/(\d+)-[^/]+\.md", path))
    ]
    return max(numbers, default=0) + 1


def plan_documents(issue, kinds, paths, reserved_paths, today, document_issues=None):
    number = issue["number"]
    slug = slugify(issue["title"])
    documents = {
        kind: find_document(paths, kind, number, document_issues)
        for kind in ("spec", "adr")
    }
    for kind in kinds:
        if documents[kind] is None:
            documents[kind] = (
                f"doc/specs/{slug}.md"
                if kind == "spec"
                else f"doc/adrs/{next_adr_number(reserved_paths):04d}-{slug}.md"
            )
            if documents[kind] in paths:
                raise RuntimeError(
                    f"Cannot create {documents[kind]}: the filename is already in use by another "
                    "document. Choose a different title or correct the document's issue metadata."
                )
    additions = {}
    for kind in kinds:
        path = documents[kind]
        if path in paths:
            continue
        other = documents["adr" if kind == "spec" else "spec"]
        related = (
            f"[{Path(other).name}](../{Path(other).parent.name}/{Path(other).name})"
            if other
            else "TODO: Link the related document if one is needed."
        )
        values = {
            "number": str(number),
            "title": " ".join(issue["title"].splitlines()),
            "summary": json.dumps(issue["title"], ensure_ascii=False),
            "issue_url": issue["html_url"],
            "date": today,
            "adr_number": (
                str(int(Path(path).name.split("-", 1)[0])) if kind == "adr" else ""
            ),
            "related": related,
            "description": "\n".join(
                "> " + line
                for line in (
                    issue.get("body") or "No description provided."
                ).splitlines()
            ),
        }
        additions[path] = Template((TEMPLATES / f"{kind}.md").read_text()).substitute(
            values
        )
    return {kind: path for kind, path in documents.items() if path}, additions


def add_issue_links(body, documents, repository, branch, server_url):
    updated = body or ""
    for kind, path in sorted(documents.items()):
        url = f"{server_url.rstrip('/')}/{repository}/blob/{quote(branch, safe='/')}/{path}"
        if url not in updated:
            label = "Specification" if kind == "spec" else "ADR"
            updated = updated.rstrip() + f"\n\n{label}: [{Path(path).name}]({url})"
    return updated.lstrip("\n")


def scaffold(event, issue_number=None):
    if issue_number is None:
        if event.get("action") not in {"labeled", "opened", "reopened"}:
            return
        if (
            event.get("action") == "labeled"
            and event.get("label", {}).get("name") not in LABELS
        ):
            return
        issue_number = event["issue"]["number"]
    issue_number = int(issue_number)
    if issue_number < 1:
        raise ValueError("Issue number must be positive")
    repository = os.environ["GITHUB_REPOSITORY"]
    prefix = f"/repos/{repository}"
    # Read current state: another label may have arrived since the event was queued.
    issue = api_request("GET", f"{prefix}/issues/{issue_number}")
    if "pull_request" in issue or issue["state"] != "open":
        return
    labels = {item["name"] for item in issue["labels"]}
    kinds = [kind for label, kind in LABELS.items() if label in labels]
    if not kinds:
        return
    branch = linked_issue_branch(repository, issue_number)
    if branch:
        print(f"Issue #{issue_number}: reusing issue-linked branch {branch}")
    else:
        branch = scaffold_pr_branch(repository, issue_number)
        if branch:
            print(f"Issue #{issue_number}: reusing scaffolding PR branch {branch}")
    base_ref = api_request("GET", f"{prefix}/git/ref/heads/main")
    branch_ref = None
    if branch:
        branch_ref = optional_get(f"{prefix}/git/ref/heads/{quote(branch, safe='')}")
        if branch_ref is None:
            raise RuntimeError(
                "The linked branch no longer exists; update the issue's branch link"
            )
    head_sha = (branch_ref or base_ref)["object"]["sha"]
    paths = tree_paths(prefix, head_sha)
    document_issues = document_issue_metadata(prefix, head_sha, paths)
    # All repository branches reserve ADR numbers, regardless of their naming convention.
    reserved = paths | tree_paths(prefix, base_ref["object"]["sha"])
    if (
        "adr" in kinds
        and find_document(paths, "adr", issue_number, document_issues) is None
    ):
        seen = {head_sha, base_ref["object"]["sha"]}
        for ref in api_request("GET", f"{prefix}/git/matching-refs/heads/"):
            sha = ref["object"]["sha"]
            if sha not in seen:
                reserved |= tree_paths(prefix, sha)
                seen.add(sha)
    documents, additions = plan_documents(
        issue,
        kinds,
        paths,
        reserved,
        datetime.now(timezone.utc).date().isoformat(),
        document_issues,
    )
    if additions:
        if branch is None:
            branch = create_issue_branch(issue, head_sha)
        commit = api_request("GET", f"{prefix}/git/commits/{head_sha}")
        tree = api_request(
            "POST",
            f"{prefix}/git/trees",
            {
                "base_tree": commit["tree"]["sha"],
                "tree": [
                    {"path": path, "mode": "100644", "type": "blob", "content": content}
                    for path, content in additions.items()
                ],
            },
        )
        new_commit = api_request(
            "POST",
            f"{prefix}/git/commits",
            {
                "message": f"docs: scaffold documentation for issue #{issue_number}",
                "tree": tree["sha"],
                "parents": [head_sha],
            },
        )
        # Fast-forward only: fail rather than overwrite concurrent contributor changes.
        api_request(
            "PATCH",
            f"{prefix}/git/refs/heads/{quote(branch, safe='')}",
            {"sha": new_commit["sha"], "force": False},
        )
    pulls = []
    if branch:
        owner = repository.split("/")[0]
        query = urlencode(
            {"state": "open", "head": f"{owner}:{branch}", "base": "main"}
        )
        pulls = api_request("GET", f"{prefix}/pulls?{query}")
    has_diff = bool(additions)
    if not pulls and branch_ref and not additions:
        comparison = api_request(
            "GET", f"{prefix}/compare/main...{quote(branch, safe='')}"
        )
        has_diff = comparison["ahead_by"] > 0 and bool(comparison["files"])
    pr_title = "feat: " + " ".join(issue["title"].splitlines())
    if not pulls and has_diff:
        # GitHub can link this PR through its issue branch without a closing keyword.
        api_request(
            "POST",
            f"{prefix}/pulls",
            {
                "title": pr_title,
                "head": branch,
                "base": "main",
                "draft": True,
                "body": (
                    f"Related issue: [#{issue_number}]({issue['html_url']})\n\n"
                    "TODO: Describe the changes.\n\n"
                    f"{pull_request_marker(issue_number)}"
                ),
            },
        )
    # Preserve edits made while documents and the PR were being created.
    latest = api_request("GET", f"{prefix}/issues/{issue_number}")
    destination = branch if pulls or has_diff else "main"
    body = add_issue_links(
        latest.get("body"),
        documents,
        repository,
        destination,
        os.environ.get("GITHUB_SERVER_URL", "https://github.com"),
    )
    if body != (latest.get("body") or ""):
        api_request("PATCH", f"{prefix}/issues/{issue_number}", {"body": body})
    print(f"Issue #{issue_number}: documentation ready on {destination}")


def main():
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    scaffold(event, event.get("inputs", {}).get("issue_number"))


if __name__ == "__main__":
    main()
