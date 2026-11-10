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

"""Rerun scheduled workflow runs that failed on a transient cause.

Scans every non-archived repository of an organisation for scheduled runs that finished failed
between one and three hours ago. A run's failed jobs are rerun when the log of any of them matches a
transient signature: GitHub unreachable, the Ubuntu or ROS package mirrors unreachable, or the build
container or runner dying. Only a run's first attempt is retried, so a run that fails transiently
again stays failed.

Usage:  retry_transient.py --org ORG [--dry-run]
        retry_transient.py --classify LOG_FILE

Needs `gh`, authenticated through GH_TOKEN with read access to the repositories' actions and,
unless --dry-run, write access to rerun them. --classify prints the transient cause of a job log,
or nothing, and needs neither. The CI orchestrator classifies with it too, to hold a failed
first attempt's badges for the retry.
"""

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone

# A network failure as git, curl, apt, docker and pip word it: name resolution, connection, timeout,
# or a server error.
_NETWORK_FAILURE = (
    r"(could not resolve|temporary failure (in name resolution|resolving)|name or service not known"
    r"|no such host|(could not|unable to|failed to) connect|connection (timed out|refused|reset)"
    r"|timed out|i/o timeout|tls handshake timeout|network is unreachable|no route to host"
    r"|bad gateway|service unavailable|gateway time-?out"
    r"|(error|status|http/[\d.]+)\D{0,40}\b5\d\d\b)"
)


def _on_line(host: str, failure: str) -> str:
    """Build a pattern for a log line that names a host and a failure, in either order.

    :param host: Pattern for the host names.
    :param failure: Pattern for the failure.
    :returns: A case-insensitive pattern that matches a line containing both.
    """
    return rf"(?im)^(?=.*\b{host})(?=.*{failure})"


TRANSIENT = {
    "github unreachable": [
        _on_line(r"(github\.com|githubusercontent\.com|ghcr\.io)", _NETWORK_FAILURE),
        # Git transfers and action downloads, whose messages name no host.
        r"error: RPC failed|fatal: early EOF|fetch-pack: unexpected disconnect",
        r"Failed to (download action|resolve action download info)",
    ],
    "package mirror unreachable": [
        _on_line(r"(ubuntu\.com|ros\.org|ros2\.org)", _NETWORK_FAILURE),
        # apt failing to fetch from these archives for any reason: a 404 or a size or hash mismatch
        # there means the mirror is mid-sync.
        r"(?i)Failed to fetch \S*\b(ubuntu\.com|ros\.org|ros2\.org)/",
    ],
    "container or runner died": [
        r"error waiting for container",
        r"The runner has received a shutdown signal",
    ],
}

# Swept hourly, a run gets about two chances to be seen even when a scheduled sweep is delayed.
MIN_AGE = timedelta(hours=1)
MAX_AGE = timedelta(hours=3)
# Server-side prefilter on creation time, wide enough for the longest nightly run.
CREATED_LOOKBACK = timedelta(hours=12)

_ANSI = re.compile(r"\x1b\[[0-9;]*[mK]")


def classify(log: str) -> str | None:
    """Name the transient cause a job log shows.

    :param log: The job's full log text, ANSI colour codes included or not.
    :returns: A key of TRANSIENT, the first whose signature matches, or None when the log shows no
        transient cause.
    """
    log = _ANSI.sub("", log)
    for cause, patterns in TRANSIENT.items():
        if any(re.search(p, log) for p in patterns):
            return cause
    return None


def gh(*args: str) -> str:
    """Run a `gh` command.

    :param args: Arguments after `gh`.
    :returns: The command's standard output.
    :raises subprocess.CalledProcessError: When `gh` exits non-zero; its stderr is in `stderr`.
    """
    return subprocess.run(["gh", *args], capture_output=True, text=True, check=True).stdout


def failed_runs(org: str, repo: str, now: datetime) -> list[dict]:
    """List a repository's first-attempt scheduled runs that finished failed MIN_AGE to MAX_AGE ago.

    :param org: Organisation that owns the repository.
    :param repo: Repository name.
    :param now: Current time, UTC.
    :returns: The runs as returned by the GitHub API.
    :raises subprocess.CalledProcessError: When the API request fails.
    """
    out = gh(
        "api", "-X", "GET", "--paginate", f"repos/{org}/{repo}/actions/runs",
        "-f", "event=schedule", "-f", "status=failure", "-f", "per_page=100",
        "-f", f"created=>={now - CREATED_LOOKBACK:%Y-%m-%dT%H:%M:%SZ}",
        "-q", ".workflow_runs[]",
    )  # fmt: skip
    runs = [json.loads(line) for line in out.splitlines() if line]
    oldest, newest = (f"{now - age:%Y-%m-%dT%H:%M:%SZ}" for age in (MAX_AGE, MIN_AGE))
    return [r for r in runs if r["run_attempt"] == 1 and oldest <= r["updated_at"] <= newest]


def transient_cause(org: str, repo: str, run_id: int) -> str | None:
    """Find a transient cause among a run's failed jobs.

    :param org: Organisation that owns the repository.
    :param repo: Repository name.
    :param run_id: Workflow run ID.
    :returns: The cause and the failed job that shows it, as "<cause> in <job name>", or None when
        no failed job's log shows a transient cause.
    :raises subprocess.CalledProcessError: When listing the jobs fails. A job whose log cannot be
        read counts as showing no transient cause.
    """
    out = gh(
        "api", "--paginate", f"repos/{org}/{repo}/actions/runs/{run_id}/jobs?per_page=100",
        "-q", '.jobs[] | select(.conclusion == "failure") | {id, name}',
    )  # fmt: skip
    for job in (json.loads(line) for line in out.splitlines() if line):
        try:
            log = gh("api", f"repos/{org}/{repo}/actions/jobs/{job['id']}/logs")
        except subprocess.CalledProcessError:
            continue
        cause = classify(log)
        if cause:
            return f"{cause} in {job['name']}"
    return None


def main() -> int:
    """Classify a log, or sweep an organisation and rerun what failed transiently.

    :returns: The process exit status: 1 when a repository could not be scanned or a rerun request
        failed, otherwise 0.
    """
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--org")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--classify", metavar="LOG_FILE")
    a = p.parse_args()

    if a.classify:
        with open(a.classify, encoding="utf-8", errors="replace") as f:
            print(classify(f.read()) or "")
        return 0
    if not a.org:
        p.error("--org is required unless --classify is given")

    now = datetime.now(timezone.utc)
    repos = gh(
        "api", "--paginate", f"orgs/{a.org}/repos", "-q", ".[] | select(.archived | not) | .name"
    ).split()  # fmt: skip
    status = 0
    for repo in repos:
        try:
            runs = failed_runs(a.org, repo, now)
            for run in runs:
                cause = transient_cause(a.org, repo, run["id"])
                if not cause:
                    continue
                print(f"{repo}: {run['name']} {run['html_url']}: {cause}")
                if not a.dry_run:
                    gh(
                        "api",
                        "-X",
                        "POST",
                        f"repos/{a.org}/{repo}/actions/runs/{run['id']}/rerun-failed-jobs",
                    )
        except subprocess.CalledProcessError as e:
            print(f"::warning::{repo}: {e.stderr.strip()}", file=sys.stderr)
            status = 1
    return status


if __name__ == "__main__":
    sys.exit(main())
