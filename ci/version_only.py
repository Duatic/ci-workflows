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

"""Print true when a change touches nothing but changelogs and package versions.

Between BASE and HEAD, every changed file must be an existing CHANGELOG.rst, or an existing
package.xml that differs only in its <version> element. Anything else, an added, deleted or renamed
file included, prints false.

Usage:  version_only.py BASE HEAD
"""

import re
import subprocess
import sys

VERSION = re.compile(r"<version\b[^>]*>[^<]*</version>")


def git(*args):
    r = subprocess.run(["git", *args], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f'git {" ".join(args)}: {r.stderr.strip()}')
    return r.stdout


def version_only(base, head):
    fields = git("diff", "--name-status", "--no-renames", "-z", base, head).split("\0")[:-1]
    for status, path in zip(fields[::2], fields[1::2]):
        name = path.rsplit("/", 1)[-1]
        if status != "M":
            return False
        if name == "CHANGELOG.rst":
            continue
        if name == "package.xml" and VERSION.sub("", git("show", f"{base}:{path}")) == VERSION.sub(
            "", git("show", f"{head}:{path}")
        ):
            continue
        return False
    return True


def main():
    base, head = sys.argv[1:3]
    print("true" if version_only(base, head) else "false")
    return 0


if __name__ == "__main__":
    sys.exit(main())
