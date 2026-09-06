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

"""List the packages a range of commits releases.

One line per package whose <version> changed between --base and --head:

    <name> <version> <directory>

A package that moved directories at the same version is not a release. check_release_pr.py
judges whether a release is consistent; this only reports it, for the workflow that tags a merged
release pull request.

Usage:  released_packages.py --base REF --head REF
Exit 0, with nothing printed when no version changed.
"""

import argparse
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def git(*args, allow_fail=False):
    r = subprocess.run(["git", *args], capture_output=True, text=True)
    if r.returncode and not allow_fail:
        raise SystemExit(f'git {" ".join(args)}: {r.stderr.strip()}')
    return r.stdout


def manifest_at(ref, path):
    """(name, version) from a package.xml at a ref, or None if it did not exist there."""
    blob = git("show", f"{ref}:{path}", allow_fail=True)
    if not blob.strip():
        return None
    try:
        root = ET.fromstring(blob)
    except ET.ParseError:
        return None
    return (root.findtext("name") or "").strip(), (root.findtext("version") or "").strip()


def versions_at(ref):
    """{name: version} over every package.xml in the tree at ref."""
    versions = {}
    for path in git("ls-tree", "-r", "--name-only", ref).split():
        if os.path.basename(path) == "package.xml":
            m = manifest_at(ref, path)
            if m:
                versions[m[0]] = m[1]
    return versions


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--head", default="HEAD")
    args = ap.parse_args()

    merge_base = git("merge-base", args.base, args.head).strip() or args.base
    touched = [p for p in git("diff", "--name-only", f"{merge_base}..{args.head}").split() if p]

    packages = {}
    for f in touched:
        parts = Path(f).parts
        for i in range(len(parts)):
            candidate = str(Path(*parts[: i + 1]) / "package.xml")
            if candidate in touched or Path(candidate).exists():
                packages[str(Path(candidate).parent)] = candidate
                break

    base_versions = None
    for pkg_dir, pkg_xml in sorted(packages.items()):
        old = manifest_at(merge_base, pkg_xml)
        new = manifest_at(args.head, pkg_xml)
        if new is None:
            continue
        if old is None:
            # Nothing here at the base: a new package, or one that moved from another directory.
            if base_versions is None:
                base_versions = versions_at(merge_base)
            old_version = base_versions.get(new[0])
        else:
            old_version = old[1]
        if new[1] == old_version:
            continue
        print(f"{new[0]} {new[1]} {pkg_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
