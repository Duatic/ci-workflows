# Contributing

We encourage community contributions to this repository. Feel free to open an issue or provide a pull request.

# Licensing

Any contribution to this repository will be under the BSD License.

## Tooling

Please make sure for any pull request that it passes the `pre-commit` checks (see Tooling section).

### pre-commit

The [pre-commit](https://pre-commit.com/) tool is used for running certain checks and formatters every time before a commit is done.
Please use it on any pull requests for this repository. It also runs automatically in CI via `.github/workflows/self-check.yml`.

__Installation:__

`apt install pipx && pipx install pre-commit`. Open a new terminal afterwards.

__Usage:__
In the repository folder run: `pre-commit run --all`. This can be automated with `pre-commit install`, so all checks are run every time a commit is done.

## Testing workflow changes

Beyond `pre-commit` (which lints the YAML itself via `actionlint`), workflow *behavior* changes still
need to be validated against a real consumer, since this repo has no build/test of its own:

1. Actually dispatch a consumer workflow against your branch/commit and watch it run, e.g.
   `gh run watch <id> --repo Duatic/<consumer-repo> --exit-status`.
2. When testing something version-sensitive, point the consumer's `uses:` at the exact commit SHA
   first, confirm it works, then move a tag - don't debug against a moving tag.
