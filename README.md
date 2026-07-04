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

## What consumers call

Repos only ever call **`ci_orchestrator.yml`** - it owns the distro matrix, the `ROS_REPO` channel
per distro, gating, concurrency, and the draft-PR policy, and internally drives the two leaf
workflows (`reusable_ici.yml`, `pre-commit.yml`) that most repos never reference directly.

### `ci_orchestrator.yml` - consumer-facing entry point

| Input | Required | Default | Description |
|---|---|---|---|
| `ros_distro` | no | `all` | `all` runs the full gated matrix (jazzy, then kilted/lyrical/rolling once jazzy succeeds); a single distro name (e.g. `kilted`) builds only that one. |
| `runner` | no | `ubuntu-latest` | Runner label(s) for the build jobs, e.g. `self-hosted`. |
| `badge_gist_id` | no | `''` | Opt-in: gist ID to publish per-distro pass/fail status badges to. Empty disables badge publishing entirely. |

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

Badges are only written on pushes to `main` (matching the old `?branch=main` badge semantics) —
pull request runs never touch them. A single gist can hold badges for multiple repos since the
filename is namespaced per repo.

## Leaf workflows (internal, not called directly by product repos)

- **`reusable_ici.yml`** - the upstream `ros-industrial` industrial_ci template, builds one distro/channel combination. Auto-detects `repos.list`, `Aptfile`, and `requirements.txt`.
- **`pre-commit.yml`** - runs `pre-commit` across all files.

## Requirements on consumer repos
- Repos using a private-dependency PAT must have a secret available (repo or org level) and pass `secrets: inherit`.
- Repos opting into gist-backed badges must have a `GIST_TOKEN` secret available (repo or org level) and pass `secrets: inherit`.
