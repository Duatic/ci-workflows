#!/usr/bin/env bash
# Copyright 2026 Duatic AG
#
# Redistribution and use in source and binary forms, with or without modification, are permitted provided that
# the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, this list of conditions, and
#    the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice, this list of conditions, and
#    the following disclaimer in the documentation and/or other materials provided with the distribution.
#
# 3. Neither the name of the copyright holder nor the names of its contributors may be used to endorse or
#    promote products derived from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED
# WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A
# PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR
# ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED
# TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION)
# HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
# NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

# Drive tested_tree.py's lookup through its cases, against a fake GitHub API.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHONPATH="$HERE" exec python3 - <<'PY'
from datetime import datetime, timedelta, timezone

from tested_tree import find_tested_run

NOW = datetime(2026, 11, 4, 12, tzinfo=timezone.utc)
REPO, CURRENT, SHA, HEAD = "o/r", 9, "merge", "prhead"
passed = failed = 0


def run(id, event="pull_request", hours=1):
    at = (NOW - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"id": id, "event": event, "run_started_at": at, "html_url": f"run/{id}"}


LEGS = {("jazzy", "amd64"), ("jazzy", "arm64"), ("rolling", "amd64"), ("rolling", "arm64")}


def leg(level, distro, arch, conclusion="success"):
    return {"name": f"ci / {level} ({distro}, {arch}) / {distro} ({arch})", "conclusion": conclusion}


FULL = [leg("primary", "jazzy", a) for a in ("amd64", "arm64")] + [
    leg("secondary", "rolling", a) for a in ("amd64", "arm64")
]


def jobs(*js):
    return {"total_count": len(js), "jobs": list(js)}


def check(label, want, runs=None, jobs_of=None, head_tree="T", merged=True):
    runs = runs or {}
    jobs_of = jobs_of or {}
    routes = {
        f"/repos/{REPO}/actions/runs/{CURRENT}": {"workflow_id": 7},
        f"/repos/{REPO}/git/commits/{SHA}": {"tree": {"sha": "T"}},
        f"/repos/{REPO}/git/commits/{HEAD}": {"tree": {"sha": head_tree}},
        f"/repos/{REPO}/commits/{SHA}/pulls": [
            {"head": {"sha": HEAD}, "merged_at": "x" if merged else None}
        ],
    }
    for sha in (SHA, HEAD):
        routes[f"/repos/{REPO}/actions/workflows/7/runs?head_sha={sha}&status=success&per_page=100"] = {
            "workflow_runs": runs.get(sha, [])
        }
    for sha_runs in runs.values():
        for r in sha_runs:
            routes[f"/repos/{REPO}/actions/runs/{r['id']}/jobs?per_page=100"] = jobs_of.get(
                r["id"], jobs(*FULL)
            )
    found = find_tested_run(routes.__getitem__, REPO, str(CURRENT), SHA, LEGS, NOW)
    got = found["id"] if found else None
    global passed, failed
    if got == want:
        print(f"  PASS  {label:<56}")
        passed += 1
    else:
        print(f"  FAIL  {label:<56}\n          want: {want}\n          got:  {got}")
        failed += 1


check("no earlier run builds", None)
check("a full run on the pull request head counts", 1, runs={HEAD: [run(1)]})
check("a full run on the commit itself counts", 2, runs={SHA: [run(2, "push")]})
check("a head with another tree does not count", None, runs={HEAD: [run(1)]}, head_tree="U")
check("an unmerged pull request does not count", None, runs={HEAD: [run(1)]}, merged=False)
check("a run older than a day does not count", None, runs={HEAD: [run(1, hours=25)]})
check("the current run does not count", None, runs={SHA: [run(CURRENT, "push")]})
check("a dispatched run does not count", None, runs={SHA: [run(3, "workflow_dispatch")]})
check("a run that skipped a leg does not count", None,
      runs={HEAD: [run(1)]},
      jobs_of={1: jobs(*FULL[:3], leg("secondary", "rolling", "arm64", "skipped"))})
check("a run missing a leg does not count", None,
      runs={HEAD: [run(1)]}, jobs_of={1: jobs(*FULL[:2])})
check("a run with a failed job does not count", None,
      runs={HEAD: [run(1)]},
      jobs_of={1: jobs(*FULL, {"name": "ci / pre-commit / Format", "conclusion": "failure"})})
check("skipped jobs outside the legs still count", 1,
      runs={HEAD: [run(1)]},
      jobs_of={1: jobs(*FULL, {"name": "ci / Publish status badges", "conclusion": "skipped"},
                       {"name": "ci / pre-commit / Format", "conclusion": "skipped"})})
check("extra legs beyond this run's still count", 1,
      runs={HEAD: [run(1)]}, jobs_of={1: jobs(*FULL, leg("secondary", "kilted", "amd64"))})
check("a run with more jobs than listed does not count", None,
      runs={HEAD: [run(1)]}, jobs_of={1: {"total_count": 150, "jobs": FULL}})
check("a later full run counts past a partial one", 4,
      runs={HEAD: [run(1), run(4)]}, jobs_of={1: jobs(*FULL[:1])})

print(f"\n  {passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
PY
