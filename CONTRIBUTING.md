# Contributing

We encourage community contributions to this repository. Feel free to open an issue or provide a pull request.

# Licensing

Any contribution to this repository will be under the BSD License.

## Testing changes

This repo has no CI of its own — it only ships workflow definitions. Before opening a pull request:

1. Run a quick syntax check on any changed workflow file:
   `python3 -c "import yaml; yaml.safe_load(open('path/to/file.yml'))"`.
2. Actually dispatch a consumer workflow against your branch/commit and watch it run, e.g.
   `gh run watch <id> --repo Duatic/<consumer-repo> --exit-status`.
3. When testing something version-sensitive, point the consumer's `uses:` at the exact commit SHA
   first, confirm it works, then move a tag — don't debug against a moving tag.
