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

"""Print one version's bullets from a CHANGELOG.rst, for a GitHub Release body.

Usage:  changelog_section.py CHANGELOG.rst VERSION
Exit 0 with the section's bullets on stdout, 1 if that version has no section in the file.
"""

import re
import sys

# REP-132, and the exact shape catkin_pkg parses: X.Y.Z, one space, a date in parentheses.
SECTION = re.compile(r"^(\d+\.\d+\.\d+) \((.+)\)$")
# A section title is followed by a line of one repeated punctuation character.
UNDERLINE = re.compile(r"^[-~^\"'`#*+=]{2,}$")


def is_title(lines, i):
    return (
        i + 1 < len(lines)
        and bool(lines[i].strip())
        and bool(UNDERLINE.match(lines[i + 1].strip()))
    )


def main():
    path, version = sys.argv[1], sys.argv[2]
    lines = open(path, encoding="utf-8").read().split("\n")
    for i in range(len(lines) - 1):
        m = SECTION.match(lines[i])
        if m and m.group(1) == version and is_title(lines, i):
            end = len(lines)
            for j in range(i + 2, len(lines) - 1):
                if is_title(lines, j):
                    end = j
                    break
            print("\n".join(lines[i + 2 : end]).strip())
            return 0
    print(f"{path}: no {version} section", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
