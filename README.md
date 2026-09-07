# ci-workflows

Central, versioned GitHub Actions reusable workflows.

## Versioning

Tags follow semver. Pin consumers to the moving major tag:

```yaml
uses: Duatic/ci-workflows/.github/workflows/ci_orchestrator.yml@v1
```

`v1` always points at the latest compatible `v1.x.y` release. Immutable `v1.0.0`-style tags exist
for rollback/bisection. Breaking input changes bump the major (`@v2`).

Releases are cut via the **Release** workflow (`workflow_dispatch`, `.github/workflows/release.yml`)
from the [Actions tab](https://github.com/Duatic/ci-workflows/actions/workflows/release.yml): pick
`patch`/`minor`/`major`, and it computes the next version from the latest tag, creates the immutable
`vX.Y.Z` tag, force-moves the corresponding major tag (`vX`) to the same commit, and publishes a
GitHub Release with auto-generated notes.

That is how this and the other tooling repositories version. ROS package repositories release per
package instead, with immutable `<package>/X.Y.Z` tags and no moving major; see
[Package releases](#package-releases).

## What consumers call

For CI, repos only ever call **`ci_orchestrator.yml`** - it owns the distro matrix, the `ROS_REPO`
channel per distro, gating, concurrency, and the draft-PR policy, and internally drives the two leaf
workflows (`reusable_ici.yml`, `pre-commit.yml`) that most repos never reference directly.

**`claude_review.yml`** is the other consumer-facing workflow, and is unrelated to CI: it runs a
Claude code review on a PR when someone comments `@claude review` on it. It's opt-in per repo and
never runs on its own. See [Claude code review](#claude-code-review).

**`reusable_prepare_release.yml`** (one package at a time), **`reusable_prepare_repo_release.yml`**
(every package in the repository together, at one shared version), **`reusable_release_check.yml`**
and **`reusable_release_tag.yml`** carry releases. A repo picks one release mode by which prepare
workflow its own `release.yml` calls; both share the same check and tag workflows. They are opt-in
per repo and unrelated to the CI matrix. See [Package releases](#package-releases).

### `ci_orchestrator.yml` - consumer-facing entry point

| Input | Required | Default | Description |
|---|---|---|---|
| `ros_distro` | no | `all` | `all` runs the full gated matrix (jazzy, then kilted/lyrical/rolling once jazzy succeeds); a single distro name (e.g. `kilted`) builds only that one. |
| `runner` | no | `ubuntu-latest` | Runner label(s) for the build jobs, e.g. `self-hosted`. |
| `badge_gist_id` | no | `''` | Opt-in: gist ID to publish per-distro pass/fail status badges to. Empty disables badge publishing entirely. |
| `devtools_ref` | no | `''` | Opt-in: take `.pre-commit-config.yaml` from this `duatic_devtools` revision, e.g. `v1`, instead of the copy in the calling repository. |

| Secret | Required | Description |
|---|---|---|
| `CI_PAT` | no | PAT used to clone private upstream dependencies from a `repos.list` file at the repo root. Pass via `secrets: inherit`; omit entirely for public-only repos. |
| `GIST_TOKEN` | no | PAT with `gist` scope. Required only if `badge_gist_id` is set. Pass via `secrets: inherit`. |

What's **not** an input, because it's derived or auto-detected rather than repo-specific config:
- **`upstream_workspace`** - auto-detected: `reusable_ici.yml` uses `repos.list` if it exists at the repo root, otherwise nothing.
- **Extra `apt` dependencies** (e.g. `libboost-regex-dev`) - drop an `Aptfile` at the consumer repo root (one package per line, `#` comments allowed); picked up automatically. Most repos don't need this file at all.
- **Extra `pip` dependencies not resolvable via rosdep** (e.g. `open3d`) - drop a `requirements.txt` file at the consumer repo root; `pip install`ed (full dependency tree, `--break-system-packages`) after target dependencies are installed, before build/test. Most repos don't need this file at all.
- **Draft PRs** - the full matrix is too expensive to run on drafts. On a draft PR the orchestrator runs a single job that fails immediately with a message to mark the PR ready for review, instead of building anything. Marking the PR "Ready for review" runs the real matrix.

## Example: library repo, no private deps

This is the *entire* CI file a typical repo needs. The only things meant to be edited per repo are the `cron`/`timezone` and, whether it has a secret to inherit.

```yaml
name: CI
on:
  workflow_dispatch:
    inputs:
      ros_distro:
        description: 'Distro to build'
        type: choice
        options: [all, jazzy, kilted, lyrical, rolling]
        default: all
  pull_request:
    types: [opened, synchronize, reopened, ready_for_review]
  push:
    branches: [main]
  schedule:
    - cron: '0 1 * * *'
      timezone: Europe/Zurich

jobs:
  ci:
    uses: Duatic/ci-workflows/.github/workflows/ci_orchestrator.yml@v1
    with:
      ros_distro: ${{ inputs.ros_distro }}
    secrets: inherit
```

## Example: product repo with a private-dependency PAT, self-hosted runner

Same file, plus `runner: self-hosted`. The `repos.list` file at the repo root and the secret (repo or org level) are all that's needed for private upstream deps - no extra workflow input.

```yaml
jobs:
  ci:
    uses: Duatic/ci-workflows/.github/workflows/ci_orchestrator.yml@v1
    with:
      ros_distro: ${{ inputs.ros_distro }}
      runner: self-hosted
    secrets: inherit
```

## Status badges for private repos (opt-in, gist-backed)

GitHub's native workflow `badge.svg` reports at the workflow-**file** level, so it can't show
one badge per distro, and it won't render for anonymous viewers of a **private** repo's README.
To get per-distro badges that work regardless of repo visibility, the orchestrator can publish
each distro's pass/fail to a gist, which [shields.io's `endpoint`
renderer](https://shields.io/badges/endpoint-badge) then turns into a badge:

1. Create a public gist (any placeholder file) and a PAT with only the `gist` scope.
2. Add the PAT as a repo (or org) secret named `GIST_TOKEN`.
3. Pass `badge_gist_id` and `secrets: inherit` in your `ci.yml`:
   ```yaml
   jobs:
     ci:
       uses: Duatic/ci-workflows/.github/workflows/ci_orchestrator.yml@v1
       with:
         ros_distro: ${{ inputs.ros_distro }}
         badge_gist_id: <your-gist-id>
       secrets: inherit
   ```
4. Point README badges at the gist file, namespaced `<repo-name>-<distro>.json`:
   ```markdown
   [![Jazzy](https://img.shields.io/endpoint?url=https://gist.githubusercontent.com/<user>/<gist-id>/raw/<repo-name>-jazzy.json)](https://github.com/<org>/<repo-name>/actions/workflows/ci.yml)
   ```

Badges are only written on pushes to `main`. Each distro leg renders its own badge JSON and uploads it as an artifact; a `badges` job in the orchestrator downloads every leg's artifact and does a single multi-file gist PATCH per run.

**Use a separate gist per repo**, even though the filename is namespaced (`<repo-name>-<distro>.json`)
and would technically allow sharing one gist across repos. With ~20 repos on the same nightly
cron, concurrent writers hitting the *same* gist trip GitHub's secondary (abuse) rate limit even
after coalescing each repo down to one write. The abuse limit is sensitive to concurrent writes against
one resource, not just total call volume.

## Claude code review

Comment this on any open pull request:

```
@claude review
```

A Claude code review runs against that PR and posts its findings as inline comments on the
lines it has something to say about, plus a summary comment. It's the same reviewer as the
`/code-review` command in the Claude Code CLI, so findings are calibrated the same way as
what you see locally.

Nothing about the request is configurable. The comment takes no arguments, and the workflow
fixes the model to `opus` and the review depth to `medium` effort. `medium` reports only the
findings the reviewer is confident in, which keeps false positives low.

**Reviews are never automatic.** They only run when someone asks, so no PR costs anything
unless a developer wants a review on it. Each run posts a collapsed *Claude review run
details* comment with what Claude Code recorded for it. Note that the
dollar figure is computed locally from token counts at list rates: on subscription auth it's what the review *would* have cost on the API, not a charge.

**The review can only read.** The job's token gets `contents: read`, and Claude is given no
`Edit`, `Write`, or `Bash` tools, so a review cannot modify code, commit, or open a PR.

| Input | Required | Default | Description |
|---|---|---|---|
| `runner` | no | `self-hosted` | Runner label(s) to run the review on, e.g. `ubuntu-latest`. |

| Secret | Required | Description |
|---|---|---|
| `CLAUDE_CODE_OAUTH_TOKEN` | one of | Claude subscription token from `claude setup-token`. Usage draws on that account's plan allowance. |
| `ANTHROPIC_API_KEY` | one of | Claude API key. Billed per token to the Console organization instead. |

Set whichever one you want as a repo secret. If both are set, the API key wins.

## Package releases

Releases go through a pull request titled `release: ...` that a person reviews before anything is
tagged. A repository releases either one package at a time, each on its own version, or every
package together at one shared version - it picks by which prepare workflow its own `release.yml`
calls; the check and tag workflows are the same either way. The scripts behind all of it are in
`release/` in this repository.

**`reusable_prepare_release.yml`** opens the pull request for one package. Dispatched with a
package name, it takes the commits touching the package since its last `<package>/<version>` tag,
writes them as the next version's section in `CHANGELOG.rst`, bumps `<version>` in `package.xml`,
and opens a draft pull request titled `release: <package> <version>` with a summary. Subjects are
read with the grammar the title check enforces: a `!` or a `BREAKING CHANGE` footer makes the bump
major, `feat` makes it minor, anything else a patch; `chore`, `ci`, `test`, `build` and `release`
stay out of the notes. `bump` overrides the derived bump, and the summary reports both. Headers
changed under `include/` are listed for review. The release checks below run before the pull
request is opened, so a bad result never reaches one.

A note worth more than a commit title can be written at any time under an `Upcoming changes`
heading in a package's `CHANGELOG.rst`; the next release carries those bullets first and drops the
heading. Each note is one flat bullet (`*`, `-` or `+`); a nested list under one stops the release
instead of losing the detail silently. This applies to both prepare workflows below.

**`reusable_prepare_repo_release.yml`** opens the pull request for every package in the repository
at once. `bump` is required - there is no single commit history to derive one from - and applies
uniformly: the new version is the highest current version among the included packages, bumped by
that amount, and every one of them moves to it together, converging even if they started at
different versions. A package with no qualifying commit still gets the shared bump, with
`No changes.` as its section's sole bullet, unless it has its own hand-written `Upcoming changes`
note, which is used instead. The whole release is refused if every package would be a no-op.
Packages listed in `release-exclude.txt` at the repository root (one name per line, an optional
trailing reason, `#` comments) are left untouched entirely - not bumped, not noted, not counted
toward the shared version or the no-op check. The pull request is titled `release: <version>`, with
no package name.

**`reusable_release_check.yml`** asserts on every pull request that the `<version>` in
`package.xml`, the section heading in `CHANGELOG.rst`, and whether the title starts with `release:`
all agree, and that every changelog the pull request touches still parses the way bloom reads it.
Checks are per package, so one pull request can release several.

**`reusable_release_tag.yml`** runs when a pull request merges. For each package whose version
changed it creates the tag `<package>/<version>` at the merge commit and publishes a GitHub Release
with that version's changelog section as its notes. Package tags never move. The calling job grants
`contents: write`, and the pull request is squash- or merge-committed; after a rebase merge there is
nothing for it to find.

**`reusable_release_build.yml`** builds a tagged package into a `.deb` with `duatic_devtools`'
builder and uploads it as an artifact. It is not wired into any repository yet: a package's Duatic
dependencies resolve only from the builder's local repository, so the build stops at the first one.
Signing and publishing belong to the archive host.

**`reusable_title_check.yml`** asserts that the pull request title is `<type>(<scope>)?!?: <subject>`
with a type from `feat fix docs chore ci test refactor perf build release`. `main` is squash-merged,
so the title is the commit message that lands there, and `release:` is what the release check
keys on.

Per package:

```yaml
# .github/workflows/release.yml
name: Release
on:
  workflow_dispatch:
    inputs:
      package:
        description: 'Package to release'
        type: choice
        options: [pkg_a, pkg_b]
      bump:
        description: 'Override the bump derived from the commits'
        type: choice
        options: [derived, major, minor, patch]
        default: derived
  pull_request:
    types: [closed]

jobs:
  prepare:
    if: github.event_name == 'workflow_dispatch'
    uses: Duatic/ci-workflows/.github/workflows/reusable_prepare_release.yml@v1
    with:
      package: ${{ inputs.package }}
      bump: ${{ inputs.bump }}
    secrets: inherit

  tag:
    if: github.event_name == 'pull_request' && github.event.pull_request.merged
    permissions:
      contents: write
    uses: Duatic/ci-workflows/.github/workflows/reusable_release_tag.yml@v1
```

Per repo - same `tag:` job, `prepare:` takes only a bump:

```yaml
jobs:
  prepare:
    if: github.event_name == 'workflow_dispatch'
    uses: Duatic/ci-workflows/.github/workflows/reusable_prepare_repo_release.yml@v1
    with:
      bump: ${{ inputs.bump }}   # type: choice, options: [major, minor, patch], no default
    secrets: inherit
```

And in `ci.yml`, beside the orchestrator, for either mode:

```yaml
  release-check:
    if: github.event_name == 'pull_request'
    uses: Duatic/ci-workflows/.github/workflows/reusable_release_check.yml@v1

  title:
    if: github.event_name == 'pull_request'
    uses: Duatic/ci-workflows/.github/workflows/reusable_title_check.yml@v1
```

| Input | Workflow | Required | Default | Description |
|---|---|---|---|---|
| `package` | prepare | yes | | The package to release, by its `package.xml` name. |
| `bump` | prepare | no | `derived` | `major`, `minor` or `patch`; `derived` or empty takes it from the commits. |
| `bump` | prepare-repo | yes | | `major`, `minor` or `patch`. No derivation: applies to every package alike. |
| `tag` | build | yes | | The `<package>/<version>` tag to build. |
| `repository` | build | no | the caller | `owner/name` of the repository holding the tag, for a dispatch from elsewhere. |
| `ros_distro`, `os_version` | build | no | `jazzy`, `noble` | What to build for. |
| `runner` | prepare, prepare-repo, check, tag | no | `ubuntu-latest` | Runner label(s), e.g. `self-hosted`. |

| Secret | Workflow | Required | Description |
|---|---|---|---|
| `RELEASE_PAT` | prepare, prepare-repo | yes | Token with `repo` scope. A pull request opened with `GITHUB_TOKEN` starts no workflows, so it would carry no checks. Pass via `secrets: inherit`. |

## Leaf workflows (internal, not called directly by product repos)

- **`reusable_ici.yml`** - the upstream `ros-industrial` industrial_ci template, builds one distro/channel combination. Auto-detects `repos.list`, `Aptfile`, and `requirements.txt`.
- **`pre-commit.yml`** - runs `pre-commit` across all files.

## Requirements on consumer repos
- Repos using a private-dependency PAT must have a secret available (repo or org level) and pass `secrets: inherit`.
- Repos opting into gist-backed badges must have a `GIST_TOKEN` secret available (repo or org level) and pass `secrets: inherit`.
- Repos opting into `claude_review.yml` must have their own `CLAUDE_CODE_OAUTH_TOKEN` (or `ANTHROPIC_API_KEY`) repo secret and pass `secrets: inherit`.
- Repos releasing packages through `reusable_prepare_release.yml` must have a `RELEASE_PAT` secret available (repo or org level) and pass `secrets: inherit`.
