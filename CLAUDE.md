# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

`ci-workflows` is the **single source of truth for CI** across every Duatic ROS 2 repository
(`duatic_helpers`, `duatic_dynaarm`, `duatic_duarover`, etc.). It replaces what used to be a
copy-pasted, drift-prone `reusable_ici.yml` / `build-<distro>.yml` / `pre-commit.yml` set of files
duplicated in every repo's `.github/workflows/`. Consumer repos call one workflow from here instead
of authoring their own CI logic.

This repo is **public** (org policy blocks creating org repos as public directly, but the visibility
was changed after creation via the API). Public is deliberate, not incidental: a private version of
this repo had unreliable cross-repo reusable-workflow resolution — GitHub's access-control indexing
for a *newly created* private repo was flaky even with **Settings → Actions → General → Access** set
to "organization" (calls intermittently failed with "workflow was not found" for several minutes
after each change). Making the repo public sidesteps that indexing path entirely and resolved
instantly. There are no secrets in this repo, so public is safe. If this repo is ever made private
again, re-enable that Access setting and expect to re-verify resolution carefully.

## Design principle: push complexity here, not into consumer repos

The whole point of this repo is that a consumer's `.github/workflows/ci.yml` should be almost
nothing — triggers plus one job call. Concretely, a consumer repo should **not** need to know or
configure:
- the distro list or the `ROS_REPO` channel per distro (`rolling` → `testing`, everything else →
  `main` — this mapping lives in `ci_orchestrator.yml`'s `prepare` job and nowhere else)
- which distro gates which (jazzy always builds first; the rest only run if it succeeds)
- whether it has an `UPSTREAM_WORKSPACE` (`reusable_ici.yml` auto-detects a `repos.list` file)
- extra `apt` install steps (auto-detected from an optional `Aptfile` at the consumer repo root, one
  package per line, `#` comments allowed)
- extra `pip` deps that rosdep can't resolve (auto-detected from an optional `requirements.txt` file
  at the consumer repo root, installed with full deps via `AFTER_INSTALL_TARGET_DEPENDENCIES`)
- concurrency/cancellation behavior (declared once, centrally, in `ci_orchestrator.yml`)
- what to do about draft PRs (see below)

When you're asked to add a new capability, default to adding it **here** with a sane built-in
default, not as a new input every consumer has to set. The bar for adding a new `workflow_call`
input is: "does this genuinely vary per repo in a way that can't be inferred?" (e.g. `runner` for the
handful of repos needing `self-hosted`, or `CI_PAT` for repos with private upstream deps) — not "some
repo might someday want to tweak this."

## Architecture: three workflow files, one nesting level

```
.github/workflows/
  ci_orchestrator.yml   # consumer-facing entry point — the ONLY workflow product repos call
  reusable_ici.yml      # leaf: builds ONE distro/channel combination (industrial_ci)
  pre-commit.yml        # leaf: runs pre-commit across all files
```

`ci_orchestrator.yml` calls the two leaves via **local** refs (`uses: ./.github/workflows/reusable_ici.yml`),
which resolve at whatever ref the consumer pinned (e.g. `@v1`) — so a consumer pinned to `v1` always
gets a self-consistent set of all three files, never a mix of versions. `secrets: inherit` chains
consumer → orchestrator → leaf.

`ci_orchestrator.yml` jobs, in order:
1. **`draft_guard`** — runs only if the triggering event is a draft PR; immediately fails with a
   `::error::` message telling the author to mark it ready for review. This exists because the full
   build matrix is expensive, but a draft PR still needs a visibly failing required check so nobody
   mistakes "no CI ran" for "CI passed."
2. **`prepare`** — skipped on drafts. A single bash step computes two JSON matrices (`primary`,
   `secondary`) from the `ros_distro` input. `ros_distro: all` (the default) puts `jazzy` alone in
   `primary` and `kilted`/`lyrical`/`rolling` in `secondary`; a specific distro name puts only that
   distro in `primary` and empties `secondary`. This is also where the `ROS_REPO` channel is decided
   per distro.
3. **`primary`** — matrix over `prepare`'s `primary` output, calls `reusable_ici.yml`.
4. **`secondary`** — `needs: [prepare, primary]`, skipped via `if:` when its matrix is `'[]'` (empty
   matrices are avoided deliberately — GitHub Actions handles a job with zero matrix entries poorly
   in this context, so the job is skipped outright instead of given an empty `include:`). This is the
   gate: it only starts once `primary` (jazzy) has succeeded.
5. **`pre-commit`** — skipped on drafts and on a focused single-distro dispatch (`ros_distro != all`),
   since a targeted manual rebuild of one distro usually isn't about linting.

`reusable_ici.yml` is close to the upstream `ros-industrial/industrial_ci` reusable-workflow
template (see the `original author` comment) — resist the urge to restructure it away from that
shape, since it's the pattern most contributors will already recognize from other ROS orgs.

## Versioning

Semver tags. `v1` is a **lightweight tag pointing directly at a commit** — not at another tag, and
not annotated. This matters: an earlier `v1` was created as a lightweight tag pointing at the
annotated `v1.0.0` tag object (a tag-of-a-tag chain via `git tag v1 v1.0.0`), and GitHub's reusable
workflow resolver could not reliably dereference that chain (`workflow was not found` errors that
had nothing to do with permissions). Always recreate `v1` as `git tag -f v1 <commit-sha>` — never
`git tag -f v1 <another-tag-name>`.

Release flow for a change:
```bash
git tag vX.Y.Z <commit>
git tag -f v1 <commit>       # move the moving major tag (only if this is a v1-compatible change)
git push origin vX.Y.Z
git push -f origin v1
```
Breaking changes to `workflow_call` inputs (removing/renaming an input, changing default behavior in
a way existing consumers rely on) bump the major and get their own `v2` line; don't silently change
`v1`'s behavior underneath existing callers.

## Testing changes

There's no CI on this repo itself (it only ships workflow definitions) — validate by:
1. `python3 -c "import yaml; yaml.safe_load(open('path/to/file.yml'))"` for a quick syntax check.
2. Actually dispatching a consumer workflow against the new commit/tag and watching it with
   `gh run watch <id> --repo Duatic/<consumer-repo> --exit-status`. `duatic_helpers` is the pilot
   repo (`.github/workflows/ci.yml`, PR-based branch `ci/reusable-workflows` was used for the initial
   validation) — cheapest place to test since it has no private deps and a small distro set.
3. When testing something version-sensitive, point the consumer's `uses:` at the exact commit SHA
   first, confirm, then move `v1`/cut a tag — don't debug against a moving tag.

## Known GitHub quirks worth remembering

- `schedule`-triggered runs check out the default branch automatically; don't add a
  `ref_for_scheduled_build`-style input to work around this (an earlier version of `reusable_ici.yml`
  had one — it was removed as dead complexity).
- The `github` context inside a called reusable workflow reflects the **caller** (repository,
  workflow name, ref, and event payload including `github.event.pull_request.draft`), which is what
  makes the central `concurrency:` group and the `draft_guard` job possible without any consumer-side
  code.
- Accessing a missing nested key on the `github.event` object (e.g. `github.event.pull_request.draft`
  when the trigger wasn't a `pull_request`) evaluates to `null`/`false` in an `if:` expression rather
  than erroring — this is relied on throughout `ci_orchestrator.yml`'s `if:` conditions.
