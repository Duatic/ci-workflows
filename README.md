# ci-workflows

Central, versioned GitHub Actions reusable workflows for the [Duatic](https://github.com/Duatic)
organization's ROS 2 repositories. Consolidates what used to be copy-pasted, drift-prone
`reusable_ici.yml` / `build-<distro>.yml` / `pre-commit.yml` files across every product and
library repo into two maintained-in-one-place workflows.

## Versioning

Tags follow semver. Pin consumers to the moving major tag:

```yaml
uses: Duatic/ci-workflows/.github/workflows/ros_ici.yml@v1
```

`v1` always points at the latest compatible `v1.x.y` release. Immutable `v1.0.0`-style tags exist
for rollback/bisection. Breaking input changes bump the major (`@v2`).

## Workflows

### `ros_ici.yml` — ROS industrial_ci build

Wraps [`ros-industrial/industrial_ci`](https://github.com/ros-industrial/industrial_ci).

| Input | Required | Default | Description |
|---|---|---|---|
| `ros_distro` | yes | — | `ROS_DISTRO` for industrial_ci |
| `ros_repo` | no | `main` | `ROS_REPO` for industrial_ci (`main` or `testing`) |
| `upstream_workspace` | no | `''` | `UPSTREAM_WORKSPACE`, usually a path to a `.repos` file |
| `before_install_upstream_dependencies` | no | `''` | `BEFORE_INSTALL_UPSTREAM_DEPENDENCIES` |
| `ref_for_scheduled_build` | no | `''` | Ref checked out on `schedule`-triggered runs |
| `timeout_minutes` | no | `30` | Job timeout |
| `ccache_dir` | no | `.ccache` | ccache dir, relative to `github.workspace` |
| `runner` | no | `ubuntu-latest` | Runner label(s), e.g. `self-hosted` |

| Secret | Required | Description |
|---|---|---|
| `CI_PAT` | no | PAT used to clone private upstream dependencies. When set (pass via `secrets: inherit` or explicitly), the workflow injects a `git config --global url.insteadOf` rewrite so private `github.com` repos in `upstream_workspace` clone over HTTPS with the token. Omit entirely for public-only repos. |

### `pre-commit.yml` — pre-commit hooks

| Input | Required | Default | Description |
|---|---|---|---|
| `runner` | no | `ubuntu-latest` | Runner label(s) |
| `python_version` | no | `3.13` | Python version used to run pre-commit |

## Example: library repo, no private deps

```yaml
name: CI
on:
  workflow_dispatch:
  pull_request:
  push:
    branches: [main]
  schedule:
    - cron: '0 1 * * *'
      timezone: Europe/Zurich

jobs:
  jazzy:
    uses: Duatic/ci-workflows/.github/workflows/ros_ici.yml@v1
    with:
      ros_distro: jazzy
      ref_for_scheduled_build: main
    secrets: inherit

  other_distros:
    needs: jazzy
    strategy:
      fail-fast: false
      matrix:
        ros_distro: [kilted, lyrical, rolling]
    uses: Duatic/ci-workflows/.github/workflows/ros_ici.yml@v1
    with:
      ros_distro: ${{ matrix.ros_distro }}
      ref_for_scheduled_build: main
    secrets: inherit

  pre-commit:
    uses: Duatic/ci-workflows/.github/workflows/pre-commit.yml@v1
```

`jazzy` is treated as the primary distro: the other distros only run once it succeeds, so a broken
canonical build fails fast instead of burning CI minutes across the whole matrix.

## Example: product repo with a private-dependency PAT, self-hosted runner

```yaml
jobs:
  jazzy:
    uses: Duatic/ci-workflows/.github/workflows/ros_ici.yml@v1
    with:
      ros_distro: jazzy
      upstream_workspace: repos.list
      ref_for_scheduled_build: main
      runner: self-hosted
    secrets: inherit   # forwards CI_PAT
```

## Requirements on consumer repos

- If this repo is ever made private, each organization repo needs
  **Settings → Actions → General → Access** to allow "repositories in the Duatic organization" —
  otherwise `uses: Duatic/ci-workflows/...` won't resolve.
- Repos using a private-dependency PAT must have a `CI_PAT` secret available (repo or org level)
  and pass `secrets: inherit`.
