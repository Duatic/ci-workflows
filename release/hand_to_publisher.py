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

"""Hand what this run built to the publisher repository, for one channel.

Reads its inputs from the environment, as the release workflows set them:

    BUILD           JSON list of {package, version, tag, root} that were built
    DISTROS         JSON list of the ROS distros they were built for
    CHANNEL         archive channel to publish into: stable for releases, edge for builds of main
    PUBLISHER       owner/name of the publisher repository
    GH_TOKEN        reads this run's artifacts
    DISPATCH_TOKEN  dispatches to the publisher

Only the artifacts this run uploaded are handed over: a leg that failed uploaded nothing.
"""

import json
import os
import sys
import urllib.request


def call(url, token, body=None):
    req = urllib.request.Request(url, data=body, headers={
        "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read() or b"null")


def main():
    e = os.environ
    api, repo, run = e["GITHUB_API_URL"], e["GITHUB_REPOSITORY"], e["GITHUB_RUN_ID"]

    built, page = set(), 1
    while True:
        got = call(f"{api}/repos/{repo}/actions/runs/{run}/artifacts?per_page=100&page={page}",
                   e["GH_TOKEN"])["artifacts"]
        built |= {a["name"] for a in got}
        if len(got) < 100:
            break
        page += 1

    # Named as reusable_release_build.yml names them.
    artifacts = []
    for release in json.loads(e["BUILD"]):
        for distro in json.loads(e["DISTROS"]):
            for arch in ("amd64", "arm64"):
                name = f'{release["package"]}-{release["tag"].replace("/", "-")}-{distro}-{arch}'
                if name in built:
                    artifacts.append({"artifact": name, "package": release["package"],
                                      "version": release["version"], "tag": release["tag"],
                                      "root": release["root"], "distro": distro, "arch": arch})
    if not artifacts:
        print("::warning::nothing built, so nothing was handed to the publisher")
        return 0
    payload = {"repository": repo, "run_id": run, "channel": e["CHANNEL"], "artifacts": artifacts}
    call(f'{api}/repos/{e["PUBLISHER"]}/dispatches', e["DISPATCH_TOKEN"],
         json.dumps({"event_type": "publish", "client_payload": payload}).encode())
    for a in artifacts:
        print(f'handed {a["artifact"]} to {e["PUBLISHER"]} for {e["CHANNEL"]}')
    return 0


if __name__ == "__main__":
    sys.exit(main())
