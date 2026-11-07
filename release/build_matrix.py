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

"""Print the build matrix for a list of packages, as JSON for a matrix's include.

Reads its inputs from the environment, as the release workflows set them:

    BUILD    JSON list of packages to build, each with a kind of ros or system
    DISTROS  JSON list of the ROS distros to build for

A ROS package builds once per distro. A system package carries no distro in its name, so it builds
once per Ubuntu release any listed distro is on, for that release's system distro, the one the
archive routes its system packages through. Each entry is the package's own fields plus ros_distro.
"""

import json
import os
import sys

# The Ubuntu release each ROS distro is built on (REP 2000).
UBUNTU = {
    "humble": "jammy",
    "jazzy": "noble",
    "kilted": "noble",
    "lyrical": "resolute",
    "rolling": "resolute",
}
SYSTEM_DISTRO = {"jammy": "humble", "noble": "jazzy", "resolute": "lyrical"}


def main():
    build = json.loads(os.environ["BUILD"])
    distros = json.loads(os.environ["DISTROS"])
    for d in distros:
        if d not in UBUNTU:
            raise SystemExit(f"no Ubuntu release known for ROS distro '{d}'")
    include = []
    for package in build:
        kind = package.get("kind", "ros")
        if kind not in ("ros", "system"):
            raise SystemExit(f'{package["package"]}: kind is \'{kind}\', not ros or system')
        if kind == "ros":
            include += [{**package, "ros_distro": d} for d in distros]
            continue
        for u in dict.fromkeys(UBUNTU[d] for d in distros):
            include.append({**package, "ros_distro": SYSTEM_DISTRO[u]})
    print(json.dumps(include))
    return 0


if __name__ == "__main__":
    sys.exit(main())
