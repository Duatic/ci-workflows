# ci-workflows

Central, versioned GitHub Actions reusable workflows.

## Versioning

Tags follow semver. Pin consumers to the moving major tag:

```yaml
uses: Duatic/ci-workflows/.github/workflows/ci_orchestrator.yml@v1
```

`v1` always points at the latest compatible `v1.x.y` release. Immutable `v1.0.0`-style tags exist
for rollback/bisection. Breaking input changes bump the major (`@v2`).

## What consumers call

Repos only ever call **`ci_orchestrator.yml`** - it owns the distro matrix, the `ROS_REPO` channel
per distro, gating, concurrency, and the draft-PR policy, and internally drives the two leaf
workflows (`reusable_ici.yml`, `pre-commit.yml`) that most repos never reference directly.

### `ci_orchestrator.yml` - consumer-facing entry point

| Input | Required | Default | Description |
|---|---|---|---|
| `ros_distro` | no | `all` | `all` runs the full gated matrix (jazzy, then kilted/lyrical/rolling once jazzy succeeds); a single distro name (e.g. `kilted`) builds only that one. |
| `runner` | no | `ubuntu-latest` | Runner label(s) for the build jobs, e.g. `self-hosted`. |

| Secret | Required | Description |
|---|---|---|
| `CI_PAT` | no | PAT used to clone private upstream dependencies from a `repos.list` file at the repo root. Pass via `secrets: inherit`; omit entirely for public-only repos. |

What's **not** an input, because it's derived or auto-detected rather than repo-specific config:
- **`upstream_workspace`** - auto-detected: `reusable_ici.yml` uses `repos.list` if it exists at the repo root, otherwise nothing.
- **Extra `apt` dependencies** (e.g. `libboost-regex-dev`) - drop a `.github/ci/apt_dependencies` file in the consumer repo (one package per line, `#` comments allowed); picked up automatically. Most repos don't need this file at all.
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

## Leaf workflows (internal, not called directly by product repos)

- **`reusable_ici.yml`** - the upstream `ros-industrial` industrial_ci template, builds one
  distro/channel combination. Auto-detects `repos.list` and `.github/ci/apt_dependencies`.
- **`pre-commit.yml`** - runs `pre-commit` across all files.

## Requirements on consumer repos
- Repos using a private-dependency PAT must have a secret available (repo or org level) and pass `secrets: inherit`.
