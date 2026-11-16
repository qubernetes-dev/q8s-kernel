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

"""Promote documentation links in a merged PR's linked issues to main."""

import argparse
import json
import os
import re
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

LINKED_ISSUES_QUERY = """
query($owner: String!, $name: String!, $number: Int!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      closingIssuesReferences(first: 100, after: $cursor) {
        nodes { number repository { nameWithOwner } }
        pageInfo { hasNextPage endCursor }
      }
    }
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
        result = json.load(response)
    if isinstance(result, dict) and result.get("errors"):
        raise RuntimeError("GitHub GraphQL request failed")
    return result


def linked_issues(repository, number):
    owner, name = repository.split("/")
    cursor = None
    while True:
        result = api_request(
            "POST",
            "/graphql",
            {
                "query": LINKED_ISSUES_QUERY,
                "variables": {
                    "owner": owner,
                    "name": name,
                    "number": number,
                    "cursor": cursor,
                },
            },
        )
        connection = result["data"]["repository"]["pullRequest"][
            "closingIssuesReferences"
        ]
        for issue in connection["nodes"]:
            # The workflow token is scoped to this repository.
            if issue["repository"]["nameWithOwner"] == repository:
                yield issue["number"]
        if not connection["pageInfo"]["hasNextPage"]:
            return
        cursor = connection["pageInfo"]["endCursor"]


def rewrite_links(body, pull_request, server_url="https://github.com"):
    base_repo = pull_request["base"]["repo"]["full_name"]
    head = pull_request["head"]
    repositories = {base_repo}
    if head.get("repo"):
        repositories.add(head["repo"]["full_name"])
    # GitHub links can contain literal or percent-encoded slashes in branch names.
    refs = {quote(head["ref"], safe="/"), quote(head["ref"], safe="")}
    prefixes = [
        f"{server_url.rstrip('/')}/{repository}/blob/{ref}/"
        for repository in repositories
        for ref in refs
    ]
    pattern = re.compile(
        r"(?<![\w/])(?:"
        + "|".join(re.escape(prefix) for prefix in prefixes)
        + r")(?=doc/(?:specs|adrs)/)"
    )
    destination = f"{server_url.rstrip('/')}/{base_repo}/blob/main/"
    return pattern.sub(lambda match: destination, body)


def update_issues(event, dry_run=False):
    pull_request = event.get("pull_request", {})
    if (
        event.get("action") != "closed"
        or not pull_request.get("merged")
        or pull_request["base"]["ref"] != "main"
    ):
        print("Skipping: pull request was not merged into main.")
        return

    repository = pull_request["base"]["repo"]["full_name"]
    for number in linked_issues(repository, pull_request["number"]):
        endpoint = f"/repos/{repository}/issues/{number}"
        # Read the current body instead of overwriting it with an event snapshot.
        issue = api_request("GET", endpoint)
        body = issue.get("body") or ""
        updated = rewrite_links(
            body,
            pull_request,
            os.environ.get("GITHUB_SERVER_URL", "https://github.com"),
        )
        if updated == body:
            print(f"Issue #{number}: no matching links.")
            continue
        if not dry_run:
            api_request("PATCH", endpoint, {"body": updated})
        print(f"Issue #{number}: {'would update' if dry_run else 'updated'} links.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="Report updates without editing issues"
    )
    args = parser.parse_args()
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    update_issues(event, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
