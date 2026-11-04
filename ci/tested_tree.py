#!/usr/bin/env python3
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

"""Print true when the tree of the commit being built already passed a full run of this workflow.

A run counts when it is a successful run of the same workflow, started within the last 24 hours, on
a commit with the same tree: the commit itself, or the head of a merged pull request it belongs to.
Every job of the run must have succeeded, so a run that skipped part of the matrix, such as on a
draft pull request, does not count. Anything else, an API error included, prints false.

Usage:  tested_tree.py
Reads GITHUB_API_URL, GITHUB_REPOSITORY, GITHUB_RUN_ID, GITHUB_SHA and GITHUB_TOKEN.
"""

import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

MAX_AGE = timedelta(hours=24)
COUNTED_EVENTS = {"pull_request", "push", "schedule", "merge_group"}
# Publishes badges only on the default branch, so it is skipped on pull requests.
OPTIONAL_JOB = "Publish status badges"


def started(run):
    return datetime.fromisoformat(run["run_started_at"].replace("Z", "+00:00"))


def is_full(get, repo, run):
    data = get(f"/repos/{repo}/actions/runs/{run['id']}/jobs?per_page=100")
    jobs = data["jobs"]
    if data["total_count"] > len(jobs):
        return False
    return all(j["conclusion"] == "success" or j["name"].endswith(OPTIONAL_JOB) for j in jobs)


def find_tested_run(get, repo, run_id, sha, now):
    """The run that already tested sha's tree, or None."""
    workflow = get(f"/repos/{repo}/actions/runs/{run_id}")["workflow_id"]
    tree = get(f"/repos/{repo}/git/commits/{sha}")["tree"]["sha"]
    pulls = get(f"/repos/{repo}/commits/{sha}/pulls")
    heads = [sha] + [p["head"]["sha"] for p in pulls if p.get("merged_at")]
    for head in dict.fromkeys(heads):
        if head != sha and get(f"/repos/{repo}/git/commits/{head}")["tree"]["sha"] != tree:
            continue
        runs = get(
            f"/repos/{repo}/actions/workflows/{workflow}/runs"
            f"?head_sha={head}&status=success&per_page=100"
        )["workflow_runs"]
        for run in runs:
            if (
                run["id"] != int(run_id)
                and run["event"] in COUNTED_EVENTS
                and now - started(run) <= MAX_AGE
                and is_full(get, repo, run)
            ):
                return run
    return None


def api(base, token):
    def get(path):
        req = urllib.request.Request(
            base + path,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)

    return get


def main():
    env = os.environ
    get = api(env.get("GITHUB_API_URL", "https://api.github.com"), env["GITHUB_TOKEN"])
    try:
        run = find_tested_run(
            get, env["GITHUB_REPOSITORY"], env["GITHUB_RUN_ID"], env["GITHUB_SHA"],
            datetime.now(timezone.utc),
        )
    except OSError as e:
        print(f"::warning::Could not look up earlier runs, building: {e}", file=sys.stderr)
        run = None
    if run:
        print(f"Tree already passed in {run['html_url']}, not building again.", file=sys.stderr)
    print("true" if run else "false")
    return 0


if __name__ == "__main__":
    sys.exit(main())
