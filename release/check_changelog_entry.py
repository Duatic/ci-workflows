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

"""Check that a pull request touching a package also records the change in its changelog.

The entry has to land under "Upcoming changes". That section is the one a release later renames, so
anything not written there is absent from the release notes and from the .deb that ships them.

Scope, and what is deliberately not checked:

  * a package is touched when any file under it changes other than its own CHANGELOG.rst;
  * a package whose version changed is skipped, because that is a release and
    check_release_pr.py already requires a section named for the new version;
  * the entry only has to be new, not well written. check_changelog_format.py judges the shape.

Usage:  check_changelog_entry.py --base origin/main [--head HEAD]
Exit 0 if every touched package gained an entry, 1 if not.
"""

import argparse
import os
import re
import subprocess
import sys

# A section title is followed by a line of one repeated punctuation character.
UNDERLINE = re.compile(r"^[-~^\"'`#*+=]{2,}$")
PENDING = "Upcoming changes"


def git(*args, allow_fail=False):
    r = subprocess.run(["git", *args], capture_output=True, text=True)
    if r.returncode and not allow_fail:
        raise SystemExit(f'git {" ".join(args)}: {r.stderr.strip()}')
    return r.stdout


def blob(ref, path):
    return git("show", f"{ref}:{path}", allow_fail=True)


def upcoming_entries(text):
    """The bullets under "Upcoming changes", or None if the section is absent."""
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines[:-1]):
        if line.strip() == PENDING and UNDERLINE.match(lines[i + 1].strip()):
            start = i + 2
            break
    if start is None:
        return None
    entries = []
    for i in range(start, len(lines)):
        line = lines[i]
        if i + 1 < len(lines) and line.strip() and UNDERLINE.match(lines[i + 1].strip()):
            break  # the next section
        if line.startswith("* "):
            entries.append(line[2:].strip())
    return entries


def package_of(path, packages):
    """The package directory owning a path. Deepest first, so a nested package wins."""
    for pkg in sorted((p for p in packages if p != "."), key=len, reverse=True):
        if path.startswith(pkg + "/"):
            return pkg
    return "." if "." in packages else None


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", required=True, help="the ref to diff against, e.g. origin/main")
    parser.add_argument("--head", default="HEAD")
    args = parser.parse_args()

    packages = {
        os.path.dirname(p) or "."
        for p in git("ls-tree", "-r", "--name-only", args.head).split()
        if os.path.basename(p) == "package.xml"
    }
    if not packages:
        print("no packages in this repository")
        return 0

    changed = git("diff", "--name-only", f"{args.base}...{args.head}").split()
    touched = {}
    for path in changed:
        pkg = package_of(path, packages)
        if pkg is None:
            continue
        changelog = "CHANGELOG.rst" if pkg == "." else f"{pkg}/CHANGELOG.rst"
        if path == changelog:
            continue  # the changelog alone is not a change to the package
        touched.setdefault(pkg, changelog)

    if not touched:
        print("no package touched")
        return 0

    problems = []
    for pkg, changelog in sorted(touched.items()):
        manifest = "package.xml" if pkg == "." else f"{pkg}/package.xml"

        def version(ref):
            m = re.search(r"<version>(.*?)</version>", blob(ref, manifest), re.S)
            return m.group(1).strip() if m else None

        if version(args.base) != version(args.head):
            print(f"  skip  {pkg}: version changed, this is a release")
            continue

        head_text = blob(args.head, changelog)
        if not head_text.strip():
            problems.append((changelog, f"{pkg} was changed but has no CHANGELOG.rst"))
            continue

        head_entries = upcoming_entries(head_text)
        if head_entries is None:
            problems.append((changelog, f'no "{PENDING}" section to record the change under'))
            continue

        base_entries = upcoming_entries(blob(args.base, changelog)) or []
        if len(head_entries) <= len(base_entries):
            problems.append((changelog, f'{pkg} was changed but gained no entry under "{PENDING}"'))
        else:
            print(f"  ok    {pkg}: {len(head_entries) - len(base_entries)} new entry(s)")

    for path, message in problems:
        print(f"::error file={path}::{message}")
    if problems:
        print(f"\n{len(problems)} of {len(touched)} touched packages did not record the change")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
