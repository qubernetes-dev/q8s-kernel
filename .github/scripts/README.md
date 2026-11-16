# Documentation link automation

The `update-merged-doc-links.yml` workflow runs when a pull request is merged into `main`. It updates specification and ADR links in the bodies of issues linked for closure by that PR, including manually linked issues and references such as `Closes #123` in the PR description. A plain issue mention does not establish a closing link.

To use it:

1. Put full GitHub file URLs in the issue, pointing to the PR's source branch under `doc/specs/` or `doc/adrs/`.
2. Link the issue for closure from the PR.
3. Merge the PR into `main`.

For example, merging branch `feature/targets` changes:

```text
https://github.com/qubernetes-dev/q8s-kernel/blob/feature/targets/doc/specs/target-validation.md#requirements
```

to:

```text
https://github.com/qubernetes-dev/q8s-kernel/blob/main/doc/specs/target-validation.md#requirements
```

ADR links receive the same treatment. Links into a PR's fork are redirected to the base repository. Markdown labels, anchors, and other issue content are preserved. Other branches, commit permalinks, unrelated paths, comments, and issues in other repositories are not updated. Relative links are not rewritten. Re-running the script does not edit issues whose links already point to `main`.

The workflow executes code from `main`, uses the built-in `GITHUB_TOKEN`, and requires no additional secrets or Python dependencies. It must be present on the default branch for GitHub to trigger it. The referenced documents must exist at the same paths on `main` after merging; this script does not validate their existence or update renamed paths.

To preview changes locally, supply a saved GitHub pull request event payload and a token with access to read the repository and linked issues:

```sh
GITHUB_EVENT_PATH=/tmp/pr-event.json GITHUB_TOKEN=... \
  python3 .github/scripts/update-merged-doc-links.py --dry-run
```

The dry run reads GitHub data and reports which issues would change without writing to GitHub. Omit `--dry-run` to apply updates with a token that can write issues.

Run the automation tests with:

```sh
python3 -m unittest discover -s .github/scripts/tests -p 'test_*.py'
```
