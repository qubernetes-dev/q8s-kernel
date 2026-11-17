# Documentation automation

## Create specifications and ADRs from issue labels

The `scaffold-issue-docs.yml` workflow generates editable Markdown templates from an issue's title and description. It runs when an issue is opened or reopened with the relevant labels, or when one of those labels is added. It uses no AI service or additional Python dependencies.

| Label | Generated file |
| --- | --- |
| `needs-spec` | `doc/specs/<title-slug>.md` |
| `needs-adr` | `doc/adrs/<next-number>-<title-slug>.md` |

Both labels reuse the branch linked to the issue in GitHub's **Development** section, regardless of its name, and one open pull request into `main`. For example, issue #70 can use `70-sdlc-scaffolding`. If no branch is linked and documents need to be created, the workflow creates and links a branch named `<issue-number>-<title-slug>`, such as `70-sdlc-scaffolding`. It passes this name explicitly to GitHub. Existing linked branches keep their current names; reruns do not rename them. The workflow log states whether a branch was created or reused. Branch discovery uses GitHub's issue association, with the existing scaffolding PR as a fallback, rather than a naming pattern. A new pull request is a draft titled `feat: <issue title>`. The description contains a related issue link and a single TODO, plus a hidden marker for reruns. Reruns preserve existing PR titles. Specifications start as `Draft`; ADRs start as `Proposed`. The issue description is copied as quoted context, and TODO sections identify the requirements and rationale that still need to be written. When both documents are created together they link to each other. When a label is added later, the new document links to its existing counterpart; add the reverse link manually so existing document edits are preserved.

The workflow appends full document URLs to the current issue body, preserving its other content. GitHub automatically links a PR created from an issue-linked branch, replacing the branch association in the issue's **Development** section with the PR. This association allows issue closure on merge even though the generated description only says `Related issue: #123`. The merge link workflow uses GitHub's closing issue associations, including automatic branch associations; it does not require a `Closes` keyword. See [GitHub's linked branch behavior](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/creating-a-branch-for-an-issue). For a documentation-only merge that should leave the issue open, remove the closing association in **Development** first and update the issue's document links manually after merging.

### Setup and use

1. Merge the workflow, script, tests, and templates into `main`. Issue events only trigger workflows present on the default branch; this repository uses `main`.
2. Create the `needs-spec` and `needs-adr` issue labels in the repository.
3. In repository Settings → Actions → General → Workflow permissions, enable **Allow GitHub Actions to create and approve pull requests**. The workflow requests `contents: write`, `issues: write`, and `pull-requests: write` from the built-in `GITHUB_TOKEN`; repository or organization policies must permit them.
4. Optionally create a branch from the issue's **Development → Create a branch** control using any name. Apply either or both labels to the open issue. Open the generated draft PR, complete the TODOs, and continue implementation on the linked branch if appropriate.

For example, adding both labels to issue #70 reuses its linked `70-sdlc-scaffolding` branch and adds a specification and the next available ADR. If several branches in this repository are linked to the issue, the workflow stops before writing files; keep one development branch linked and retry. Deleted branch references and links to other repositories are ignored. A link to `main` is rejected. An existing but unlinked branch is never adopted by guessing its name. The workflow does not create labels automatically. Closed issues, pull requests, and unrelated labels are ignored.

The workflow runs trusted code and templates checked out from `main`. It writes files through the GitHub Git database API without executing code from the feature branch or interpolating issue content into shell commands. Branch updates are fast-forward only, preserving concurrent contributor commits. Specifications and ADRs store their issue association in YAML front matter (`issue: 123`). Specifications use descriptive filenames such as `validate-targets.md`; ADRs retain their sequential number, such as `0006-validate-targets.md`. Reruns find both document types through metadata, preserving edits even when filenames or issue titles change. Preserve the `issue` metadata when editing either document. Legacy filenames containing the issue number remain recognized without automatic renaming. A specification filename already used by another document produces an error rather than overwriting or reusing that document.

ADR allocation checks numbered ADRs across all repository branches, regardless of their names. Workflow runs are serialized to avoid allocating the same number to different issues. Concurrent manual ADR creation is outside this serialization; coordinate its numbering before merging. Deleting an unmerged branch also releases its reserved ADR number.

### Retries and checks

Rerun a failed Actions run, remove and reapply a relevant label, or use the workflow's **Run workflow** button on `main` with `issue_number`. The script reads the issue's current labels, reuses existing documents and the open PR, and repairs missing issue links. It does not remove documents when labels are removed. The linked branch's current contents are preserved; the workflow does not merge `main` into it. If the branch is renamed in GitHub, subsequent runs follow the updated issue association. GitHub removes the original linked branch association when it creates the PR association. When no linked branch is returned, the workflow recovers the branch from the open scaffolding PR. PRs carry a hidden issue marker for this purpose; discovery does not depend on their titles. Keep the hidden marker when editing a generated PR.

If GitHub returns an empty branch creation response, the workflow reports an actionable error instead of assuming creation succeeded. Check the issue's **Development** section and select the intended existing branch before retrying. Do not delete a branch containing your work. The workflow preserves existing documents and uses fast-forward updates when recovering.

The workflow uses `queue: max` to serialize runs while allowing up to 100 pending runs instead of replacing pending issue events. If the queue fills or a run fails, retry it manually. See [GitHub concurrency documentation](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency). A retry after a documentation merge does not open an empty PR when the branch has no remaining changes against `main`.

Writes using `GITHUB_TOKEN` do not trigger the usual branch-push workflows. PR workflow runs created by this token require approval; use **Approve workflows to run** on the generated PR. See [GitHub's token documentation](https://docs.github.com/en/actions/concepts/security/github_token) and [repository Actions settings](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-github-actions-settings-for-a-repository).

Branch discovery and creation use GitHub's [`linkedBranches` field and `createLinkedBranch` mutation](https://docs.github.com/en/graphql/reference/issues). Templates live in [`templates/`](templates/). Run the offline, mocked API tests with:

```sh
python3 -m unittest discover -s .github/scripts/tests -p 'test_*.py'
```

The dedicated [documentation automation test workflow](../workflows/test-doc-automation.yml) runs these tests on Python 3.10–3.13 for branch pushes and pull requests that change `.github/scripts/` or the relevant automation workflows. It also supports manual runs and requires no package installation or write permissions. Package publishing runs independently. The scaffolding workflow also runs the tests before writing anything to GitHub.

## Update links after merging

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
