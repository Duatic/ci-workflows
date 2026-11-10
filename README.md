# ci-workflows

Central, versioned GitHub Actions reusable workflows.

## Versioning

Tags follow semver. Pin consumers to the moving major tag:

```yaml
uses: Duatic/ci-workflows/.github/workflows/ci_orchestrator.yml@v2
```

`v2` always points at the latest compatible `v2.x.y` release. Immutable `v2.0.0`-style tags exist
for rollback/bisection. Breaking input changes bump the major (`@v3`).

Releases are cut via the **Self-release** workflow (`workflow_dispatch`,
`.github/workflows/self-release.yml`) from the
[Actions tab](https://github.com/Duatic/ci-workflows/actions/workflows/self-release.yml). It opens a
`release: X.Y.Z` pull request that adds the version's section to `CHANGELOG.rst`, the bump derived
from the commits unless one is picked. Merging it creates the immutable `vX.Y.Z` tag, force-moves
the major tag (`vX`) to the same commit, and publishes a GitHub Release with that section as its
notes. See [Changelog releases](#changelog-releases).

ROS package repositories release per package instead, with immutable `<package>/X.Y.Z` tags and no
moving major; see [Package releases](#package-releases).

## What consumers call

For CI, repos call **`ci_orchestrator.yml`** - it owns the distro matrix, gating,
concurrency, and the draft-PR policy, and internally drives the two leaf workflows
(`reusable_ci.yml`, `pre-commit.yml`) that most repos never reference directly.

**`claude_review.yml`** is the other consumer-facing workflow, and is unrelated to CI: it runs a
Claude code review on a PR when someone comments `@claude review` on it. It's opt-in per repo and
never runs on its own. See [Claude code review](#claude-code-review).

**`reusable_prepare_release.yml`** (one package at a time), **`reusable_prepare_repo_release.yml`**
(every package in the repository together, at one shared version), the **`release-check`** and
**`title-check`** actions, and **`reusable_release_tag.yml`** carry releases. A repo picks one
release mode by which prepare workflow its own `release.yml` calls; both share the same checks and
tag workflows. They are opt-in per repo and unrelated to the CI matrix. See
[Package releases](#package-releases).

**`reusable_prepare_changelog_release.yml`** and **`reusable_changelog_release_tag.yml`** do the
same for a repository that is not itself a ROS package, versioned by its `v<version>` tags with a
`CHANGELOG.rst` at its root. See [Changelog releases](#changelog-releases).

### `ci_orchestrator.yml` - consumer-facing entry point

| Input | Required | Default | Description |
|---|---|---|---|
| `ros_distro` | no | `all` | `all` runs the full gated matrix (jazzy, then kilted/lyrical/rolling once jazzy succeeds); a single distro name (e.g. `kilted`) builds only that one. |
| `extra_distros` | no | `''` | Opt-in: comma-separated distros added to the secondary distros of the `all` matrix, e.g. `humble` for repos that still support it. |
| `gated` | no | `true` | Run the secondary distros only once jazzy succeeded on the same architecture. `false` runs every distro at once, as the nightly orchestrator does. |
| `architectures` | no | `'["amd64","arm64"]'` | JSON list of the architectures every distro builds and tests on, each natively on its own runner and ci image. Private repositories without a self-hosted arm64 runner pass `'["amd64"]'`: hosted minutes are billed for them. |
| `runner` | no | `ubuntu-latest` | Runner label(s) for the amd64 legs and every other job, e.g. `self-hosted`. |
| `runner_arm64` | no | `ubuntu-24.04-arm` | Runner label(s) for the arm64 legs. |
| `devtools_ref` | no | `''` | Opt-in: take `.pre-commit-config.yaml` from this `duatic_devtools` revision, e.g. `v1`, instead of the copy in the calling repository. |
| `paths_ignore` | no | docs and images | Comma-separated shell patterns (`*` also matches `/`). A push or pull request that changes only matching files skips building and testing; the skipped legs pass required checks. The default covers `*.md`, `docs/*`, `LICENSE*`, images and the issue and pull request templates. |

| Secret | Required | Description |
|---|---|---|
| `CI_PAT` | no | PAT used to clone private upstream dependencies from a `repos.list` file at the repo root. Pass via `secrets: inherit`; omit entirely for public-only repos. |

What's **not** an input, because it's derived or auto-detected rather than repo-specific config:
- **Dependencies** - each distro builds and tests on the repo's ci image from the
  [image factory](https://github.com/Duatic/duatic_ros2_docker_images), the same pipeline as the nightly
  product images. It holds the git repositories `repos.list` collects recursively, compiled, and
  every dependency the `package.xml`, `Aptfile` and `requirements.txt` files declare. The factory
  pins every upstream branch to its commit and keys the image on that, the repo's own dependency
  manifests and the day, and reuses a published image with the same key: within a day, a run
  rebuilds it only when a dependency or an upstream commit changed. Each leg fails when the
  image lists unresolved dependencies, the same gate the robot image holds.
- **Architectures** - each distro builds and tests once per architecture in `architectures`, on that architecture's runner and ci image; its badge passes only when every architecture passed.
- **Draft PRs** - the full matrix is too expensive to run on drafts. On a draft PR the orchestrator builds only the primary distro (jazzy, or the single `ros_distro` chosen) and skips the secondary distros and pre-commit. Marking the PR "Ready for review" runs the full matrix.
- **Version-only changes** - a push or pull request that changes nothing but added or modified `CHANGELOG.rst` files and the `<version>` of existing `package.xml` files, as a release pull request does, skips building and testing like an ignored change. Pre-commit still runs.
- **Already tested trees** - a push to the default branch does not build its tree again when a run of the same workflow on that tree, within the last 24 hours, passed every distro and architecture this push would build and failed no job, either on the pushed commit or on the head of the pull request it merged. A pull request merged while up to date with the default branch has the same tree as its head. Otherwise, or when the lookup fails, the push builds. Pre-commit still runs, and the badges show passing, as in the run that tested the tree. The lookup needs `actions: read` and `pull-requests: read`; a caller that sets `permissions` must grant both.

## Example: library repo, no private deps

This is the *entire* CI file a typical repo needs. The only things meant to be edited per repo are the `cron`/`timezone` and, whether it has a secret to inherit. A repo with nightly images drops the `schedule` trigger here and schedules `reusable_nightly_orchestrator.yml` instead.

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
    - cron: '30 0 * * *'
      timezone: Europe/Zurich

jobs:
  ci:
    permissions:
      contents: write   # badges branch
      packages: write
    uses: Duatic/ci-workflows/.github/workflows/ci_orchestrator.yml@v2
    with:
      ros_distro: ${{ inputs.ros_distro }}
    secrets: inherit
```

## Example: product repo with a private-dependency PAT, self-hosted runner

Same file, plus `runner: self-hosted`. The `repos.list` file at the repo root and the secret (repo or org level) are all that's needed for private upstream deps - no extra workflow input.

```yaml
jobs:
  ci:
    permissions:
      contents: write   # badges branch
      packages: write
    uses: Duatic/ci-workflows/.github/workflows/ci_orchestrator.yml@v2
    with:
      ros_distro: ${{ inputs.ros_distro }}
      runner: self-hosted
    secrets: inherit
```

## Example: product repo with nightly images

`reusable_nightly_orchestrator.yml` runs `ci_orchestrator.yml` over the full, ungated matrix with
status badges, then the image factory's `reusable_nightly_image.yml`. The images build after CI
whatever its result, so they reuse the day's ci images instead of building them again; a dev image falls back
to a lean one when the workspace does not compile.

| Input | Required | Default | Description |
|---|---|---|---|
| `ros_distro` | no | `''` | A single distro to test and build, e.g. `kilted`. Empty runs every distro. |
| `publish` | no | `false` | Push the images to ghcr.io and publish their badges to the `image-badges` branch. |
| `runner` | no | `ubuntu-latest` | Runner label(s) for the amd64 CI legs and image builds, and every other job. |
| `runner_arm64` | no | `ubuntu-24.04-arm` | Runner label(s) for the arm64 CI legs and image builds. |
| `architectures` | no | `'["amd64","arm64"]'` | JSON list of the architectures CI tests and the images build for. |
| `extra_distros` | no | `''` | Comma-separated distros to test and build besides the default set when `ros_distro` is empty, e.g. `humble`. |

Secrets come through `secrets: inherit`: `CI_PAT` for CI, and `GH_PAT`, `DOCKERHUB_USERNAME` and
`DOCKERHUB_TOKEN` for the images. The repo's `ci.yml` keeps its `pull_request` and `push` triggers
and has no `schedule`.

```yaml
name: Nightly
on:
  workflow_dispatch:
    inputs:
      ros_distro:
        description: 'Distro to build, empty for all'
        default: ''
      publish:
        description: 'Push the images to ghcr.io'
        type: boolean
        default: false
  schedule:
    - cron: '30 0 * * *'
      timezone: Europe/Zurich

jobs:
  nightly:
    permissions:
      contents: write   # badges and image-badges branches
      packages: write
    uses: Duatic/ci-workflows/.github/workflows/reusable_nightly_orchestrator.yml@v2
    with:
      ros_distro: ${{ inputs.ros_distro }}
      publish: ${{ github.event_name == 'schedule' || inputs.publish }}
    secrets: inherit
```

## Status badges (`badges` branch)

The orchestrator commits one SVG per distro to a `badges` branch of the calling repository,
using the job's `GITHUB_TOKEN`, so the caller grants `contents: write`. No PAT or gist is needed,
and badges of private repos stay private.

After the first run on the default branch has created the branch, point README badges at it:

```markdown
[![Jazzy](https://github.com/<org>/<repo-name>/raw/badges/jazzy.svg)](https://github.com/<org>/<repo-name>/actions?query=branch%3Amain)
```

The link lists every workflow's runs on the default branch, because both the CI workflow and the
nightly orchestrator write the badges.

Badges are only written for runs on the default branch. A run that builds a single distro updates only that
distro's badge. The build and pre-commit jobs run with `contents: read`; only the badges job uses
the `contents` write permission.

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
package together at one shared version - it picks by which prepare and tag workflow its own
`release.yml` calls; the `release-check` action validates a pull request from either mode
unchanged. The scripts behind all of it are in `release/` in this repository.

**`reusable_prepare_release.yml`** opens the pull request for one package. Dispatched with a
package name, it takes the commits touching the package since its last `<package>/<version>` tag,
writes them as the next version's section in `CHANGELOG.rst`, bumps `<version>` in `package.xml`,
and opens a draft pull request titled `release: <package> <version>` with a summary. Subjects are
read with the grammar the title check enforces: a `!` or a `BREAKING CHANGE` footer makes the bump
major, `feat` (or `feature`) or `deprecate` makes it minor, anything else a patch; `chore`, `ci`, `test`, `build`
and `release` stay out of the notes. `bump` overrides the derived bump, and the summary reports both. Headers
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

**`actions/release-check`** is a composite action, not a reusable workflow: a job calling a
`workflow_call` reusable workflow hosted in this repository cannot use a self-hosted runner group
under a plain `pull_request` trigger (opened/synchronize/reopened), only under `workflow_dispatch`
or `pull_request: closed`. As a composite action it runs as a step inside a job the consumer repo
owns instead, keeping checks on self-hosted while sidestepping that restriction. It asserts that
the `<version>` in `package.xml`, the section heading in `CHANGELOG.rst`, and whether the title
starts with `release:` all agree, and that every changelog the pull request touches still parses
the way bloom reads it. Checks are per package, so one pull request can release several. Requires
the caller to have already checked out the repository with full history (`fetch-depth: 0`).

**`reusable_release_tag.yml`** runs when a per-package release pull request merges, and does
nothing for a pull request whose title does not start with `release:`. For each
package whose version changed it creates the tag `<package>/<version>` at the merge commit and
publishes a GitHub Release with that version's changelog section as its notes. A repo-wide pull
request also bumps several packages at once, but is tagged by the workflow below instead, so that
a whole repo release reads as one thing rather than as many simultaneous per-package ones. Package
tags never move. The calling job grants `contents: write`, and the pull request is squash- or
merge-committed; after a rebase merge there is nothing for it to find. It then builds the `.deb`s
of every released package that declares `<duatic_archive_root>`, with `reusable_release_build.yml`,
for each distro in `ros_distros` (default jazzy, kilted, lyrical and rolling) on amd64 and
arm64. A distro or architecture that does not build is a warning on the run and uploads nothing; a
released package without a root is not built, also with a warning. What built is then handed, with a
`repository_dispatch`, to the private publisher repository the organization variable
`RELEASE_PUBLISHER` names (or the `publisher` input), which publishes it into the apt archive's
`stable` channel from a self-hosted runner: self-hosted runners never take jobs from public repositories. The tag job passes
`secrets: inherit` so that `RELEASE_APP_ID` and `RELEASE_APP_PRIVATE_KEY` reach the dispatch; without
them, or with no publisher named, the run warns that nothing was published. The App reads the run's
artifacts, which needs Actions read on the repository, and dispatches, which needs Contents write
on the publisher. Its `released` output lists
`{package, version, tag, root}` for what it tagged, `[]` otherwise.

**`reusable_repo_release_tag.yml`** runs when a repo-wide release pull request merges. Every
included package shares one version by construction, so one tag, `v<version>`, is created at the
merge commit, and one GitHub Release is published under it with every package's changelog section
under its own heading. The same version-sharing requirement `check_release_pr.py` already enforces
on the pull request is checked again here, in case a merge ever bypasses that check.

**`reusable_edge_build.yml`** runs on a push to the default branch. It builds every package that
declares `<duatic_archive_root>`, like the tag workflow, at `<version>+git<commit time>.<commit>`
(the committer time in UTC, as `YYYYMMDDHHMMSS`), which sorts after the release it follows and
before the next one. For a squash- or merge-committed
main, that is the order commits landed in. What built is handed to the publisher for the archive's `edge` channel, which
keeps the newest builds of each package. `nightly` is not built: once a day the publisher switches
it to what `edge` publishes. It takes the same inputs as the tag workflow and needs
`secrets: inherit` the same way.

Both take `runner`, `arm64_runner`, `architectures`, `publisher`, `ros_distros` and
`private_roots`, and pass the build workflow below each package's own root.

A package declaring `<duatic_package_kind>system</duatic_package_kind>` in its `<export>`, named
`duatic_*`, needs no ROS and carries no distro in its name, so both build it once per Ubuntu release a distro in
`ros_distros` is on, in plain `ubuntu:<codename>` rather than a ROS image. It is published through
that release's system distro: humble on jammy, jazzy on noble, lyrical on resolute.

```yaml
# .github/workflows/edge.yml
name: Edge
on:
  push:
    branches: [main]
concurrency:
  group: edge-${{ github.ref }}
  cancel-in-progress: true
jobs:
  edge:
    uses: Duatic/ci-workflows/.github/workflows/reusable_edge_build.yml@v1
    secrets: inherit
```

**`reusable_release_build.yml`** builds one package into a `.deb` with `duatic_devtools`' builder,
once for amd64 on `runner` and once for arm64 on `arm64_runner` (default `ubuntu-24.04-arm`), both
native, or only for the architectures listed in `architectures`, e.g. `'["amd64"]'`. Each
architecture is uploaded as its own artifact, `<artifact>-<arch>`, holding the `.deb`, its debug
symbols and, when the package declares `<duatic_publish_source>`, its source tarball.
It takes a tag to check out and the package to build inside it, and a `version_suffix` appended to
the `package.xml` version for a build of main. The package is named explicitly, whether the tag is
a `<package>/<version>` tag, a repo-wide `v<version>` tag or a commit, so the build does not need to
guess it from the tag's shape. A dependency on a package already published resolves from the
archive the organization variable `ARCHIVE_URL` names, read from the channels in
`archive_channels`: `stable` for a release, `edge stable` for a build of main, so a dependency
without a build of main comes from its release. The archive's key is fetched from it and used only
when its fingerprint is `ARCHIVE_KEY_FINGERPRINT`. Without `ARCHIVE_URL` the build resolves no
such dependency and fails at the first one. Signing and publishing belong to the archive host.

A package in a private root also reads that root, and every root listed in `private_roots`, from
under the organization variable `ARCHIVE_PRIVATE_URL`, presenting the client certificate in the
secrets `ARCHIVE_CLIENT_CERT` and `ARCHIVE_CLIENT_KEY` (PEM, ECDSA P-256). Without any of the three
such a build fails before it starts. The certificate is written to the runner's temporary directory
for the build and removed after it, whether the build passed or not.
Files stored in Git LFS are fetched with the checkout.

**`reusable_release_publish.yml`** takes one of those artifacts and publishes it into a signed archive root,
by delivering it to the publish host and calling `duatic_devtools`' archive tooling there. The
signing key is never on the runner. It is `workflow_call` only and reads the artifact from the same
run, so it is called after the build job, once per architecture, rather than dispatched on its own.
`channel` names the archive channel, `stable` by default. The package name and
version are read from the `.deb` filename rather than taken as inputs, and both are refused unless
they match a conservative character set, because they reach a command run on the host that holds the
key. Needs `PUBLISH_HOST`, `PUBLISH_USER`, `PUBLISH_SSH_KEY`, `PUBLISH_HOST_KEY` and
`EXPECTED_KEY_FPR`, and expects a `duatic_devtools` checkout at `~/duatic_devtools` on that host.

**`actions/title-check`**, also a composite action for the same reason, asserts that the pull
request title is `<type>(<scope>)?!?: <subject>` with a type from `feat feature deprecate fix docs
chore ci test refactor perf build release` (`feature` is an alias for `feat`). `main` is
squash-merged, so the title is the commit message that
lands there, and `release:` is what the release check keys on. It also runs the version half of
the release check: a `package.xml` version may only change in a `release:` pull request. A package
new to the repository is not a release until a `release:` pull request ships it. Requires
`permissions: pull-requests: read` on the calling job and a checkout of the repository before it.

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

Per repo:

```yaml
jobs:
  prepare:
    if: github.event_name == 'workflow_dispatch'
    uses: Duatic/ci-workflows/.github/workflows/reusable_prepare_repo_release.yml@v1
    with:
      bump: ${{ inputs.bump }}   # type: choice, options: [major, minor, patch], no default
    secrets: inherit

  tag:
    if: github.event_name == 'pull_request' && github.event.pull_request.merged
    permissions:
      contents: write
    uses: Duatic/ci-workflows/.github/workflows/reusable_repo_release_tag.yml@v1
```

And in `ci.yml`, beside the orchestrator, for either mode:

```yaml
  checks:
    if: github.event_name == 'pull_request'
    runs-on: self-hosted
    permissions:
      pull-requests: read
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: Duatic/ci-workflows/actions/release-check@v1
      - uses: Duatic/ci-workflows/actions/title-check@v1
```

| Input | Workflow | Required | Default | Description |
|---|---|---|---|---|
| `package` | prepare | yes | | The package to release, by its `package.xml` name. |
| `bump` | prepare | no | `derived` | `major`, `minor` or `patch`; `derived` or empty takes it from the commits. |
| `bump` | prepare-repo | yes | | `major`, `minor` or `patch`. No derivation: applies to every package alike. |
| `tag` | build | yes | | The tag or ref to build from. |
| `package` | build | yes | | The package to build, by its `package.xml` name. |
| `repository` | build | no | the caller | `owner/name` of the repository holding the tag, for a dispatch from elsewhere. |
| `ros_distro` | build | no | `jazzy` | Distro to build for. The Ubuntu base is not an input; it's derived from this instead. |
| `version_suffix` | build | no | | Appended to the `package.xml` version, starting with `+` or `~`. The build fails if the `.deb` does not carry it. |
| `archive_channels` | build | no | `stable` | Archive channels the build's dependencies are read from, e.g. `edge stable`. |
| `channel` | publish | no | `stable` | Archive channel to publish into: `stable` or `edge`. |
| `runner` | prepare, prepare-repo, tag, repo-tag, build | no | `ubuntu-latest` | Runner label(s), e.g. `self-hosted`. |

| Secret | Workflow | Required | Description |
|---|---|---|---|
| `RELEASE_APP_ID`, `RELEASE_APP_PRIVATE_KEY` | prepare, prepare-repo, prepare-changelog | yes | The release GitHub App, which opens the pull request. It needs Contents and Pull requests read and write on the repository. A pull request opened with `GITHUB_TOKEN` starts no workflows, so it would carry no checks. Pass via `secrets: inherit`. |

## Changelog releases

A repository with no `package.xml` at its root releases as a whole. Its version is its highest
`v<version>` tag, and its notes live in `CHANGELOG.rst` at the root, in the same format as a
package's, `Upcoming changes` included. A `package.xml` deeper in it, such as a test fixture, is not
released.

**`reusable_prepare_changelog_release.yml`** opens the pull request. It takes every commit since
the last `v<version>` tag, or the whole history before the first one, writes them as the next
version's section in `CHANGELOG.rst` (creating the file on the first release), and opens a draft
pull request titled `release: <version>`. The bump is derived from the commits the same way as for
a package, and `bump` overrides it. Only `CHANGELOG.rst` changes: there is no version file.

**`reusable_changelog_release_tag.yml`** runs when that pull request merges. It tags the merge
commit `v<version>`, moves `v<major>` to it unless `move_major_tag` is `false`, and publishes a
GitHub Release with the version's section as its notes. A pull request whose title does not start
with `release:` is left alone.

Once that `CHANGELOG.rst` exists, the `release-check` and `title-check` actions check the repository
on it:
a new version section needs a `release:` title naming it, must come after the last tag, and a
`release:` title needs a new section. A section for a version already tagged is history, which any
pull request may add.

```yaml
# .github/workflows/release.yml
name: Release
on:
  workflow_dispatch:
    inputs:
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
    uses: Duatic/ci-workflows/.github/workflows/reusable_prepare_changelog_release.yml@v1
    with:
      bump: ${{ inputs.bump }}
    secrets: inherit

  tag:
    if: github.event_name == 'pull_request' && github.event.pull_request.merged
    permissions:
      contents: write
    uses: Duatic/ci-workflows/.github/workflows/reusable_changelog_release_tag.yml@v1
```

| Input | Workflow | Required | Default | Description |
|---|---|---|---|---|
| `bump` | prepare | no | `derived` | `major`, `minor` or `patch`; `derived` or empty takes it from the commits. |
| `move_major_tag` | tag | no | `true` | Move `v<major>` to the release, for callers pinning the major version. |
| `runner` | prepare, tag | no | `ubuntu-latest` | Runner label(s), e.g. `self-hosted`. |

The prepare workflow needs the release App's credentials, as above.

`release.yml`, which tags straight from a dispatch with auto-generated notes and no changelog,
remains callable for repositories not yet moved to these.

## Leaf workflows (internal, not called directly by product repos)

- **`reusable_ci.yml`** - gets one distro's ci image from the image factory's `reusable_build_image.yml`, builds and tests the repo on it, and writes that distro's badge.
- **`pre-commit.yml`** - runs `pre-commit` across all files.

## Requirements on consumer repos
- Repos using a private-dependency PAT must have a secret available (repo or org level) and pass `secrets: inherit`.
- Repos grant `packages: write` to the CI job, which pushes each distro's ci image to ghcr.io for the test job to pull. A pull request from a fork cannot push it, so its CI fails unless a ci image with the same key is already published.
- Repos keep a schedule, on `ci_orchestrator.yml` or `reusable_nightly_orchestrator.yml`: a scheduled run deletes the repo's ci images built before today, and nothing else does.
- Repos whose CI workflow sets `permissions` must grant `actions: read` and `pull-requests: read`, or every push to the default branch builds.
- Repos opting into `claude_review.yml` must have their own `CLAUDE_CODE_OAUTH_TOKEN` (or `ANTHROPIC_API_KEY`) repo secret and pass `secrets: inherit`.
- Repos releasing through a prepare workflow must have the release App's `RELEASE_APP_ID` and `RELEASE_APP_PRIVATE_KEY` available and pass `secrets: inherit`. A repository that organization secrets do not reach holds them as repository secrets.
