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

"""List the packages a build of main publishes, as JSON.

Every package.xml at --head that declares <duatic_archive_root> is built, at a version that sorts
after the release it follows and before the next one:

    [{"package": ..., "version": "<version>+git<commit time>.<commit>", "suffix": "+git...",
      "tag": "<commit>", "root": ...}]

The commit time is the committer time in UTC, as YYYYMMDDHHMMSS, so later commits on main sort
later. tag is the commit the build checks out, as reusable_release_build.yml takes it.

Usage:  edge_packages.py [--head REF]
"""

import argparse
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET


def git(*args):
    r = subprocess.run(["git", *args], capture_output=True, text=True,
                       env={**os.environ, "TZ": "UTC"})
    if r.returncode:
        raise SystemExit(f'git {" ".join(args)}: {r.stderr.strip()}')
    return r.stdout


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--head", default="HEAD")
    args = ap.parse_args()

    commit = git("rev-parse", f"{args.head}^{{commit}}").strip()
    stamp = git("show", "-s", "--format=%cd", "--date=format-local:%Y%m%d%H%M%S", commit).strip()
    suffix = f"+git{stamp}.{commit[:7]}"

    packages = []
    for path in git("ls-tree", "-r", "--name-only", commit).split():
        if os.path.basename(path) != "package.xml":
            continue
        try:
            root = ET.fromstring(git("show", f"{commit}:{path}"))
        except ET.ParseError:
            print(f"::warning::{path} is not valid XML; not built", file=sys.stderr)
            continue
        export = root.find("export")
        archive_root = (export.findtext("duatic_archive_root") or "").strip() if export is not None else ""
        if not archive_root:
            continue
        name = (root.findtext("name") or "").strip()
        version = (root.findtext("version") or "").strip()
        packages.append({"package": name, "version": version + suffix, "suffix": suffix,
                         "tag": commit, "root": archive_root})
        print(f"{name} {version}{suffix} -> {archive_root}", file=sys.stderr)
    print(json.dumps(sorted(packages, key=lambda p: p["package"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
