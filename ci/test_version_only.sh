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

# Drive version_only.py through its cases, in a throwaway repository.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOL="$HERE/version_only.py"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK" 2>/dev/null' EXIT
pass=0; fail=0

check() {  # check <label> <expected-output>
    local label="$1" want="$2" got
    git add -A && git commit -qm "$label"
    got=$( python3 "$TOOL" HEAD^ HEAD 2>/dev/null )
    if [ "$got" = "$want" ]; then printf '  PASS  %-56s\n' "$label"; pass=$((pass+1))
    else printf '  FAIL  %-56s\n' "$label"; fail=$((fail+1))
         printf '          want: %s\n          got:  %s\n' "$want" "$got"; fi
}

pkg() {  # pkg <dir> <version> [depend]
    mkdir -p "$WORK/$1"
    cat > "$WORK/$1/package.xml" <<XML
<?xml version="1.0"?>
<package format="3">
  <name>$(basename "$1")</name>
  <version>$2</version>
  <description>test</description>
  <maintainer email="t@duatic.invalid">t</maintainer>
  <license>BSD-3-Clause</license>
  ${3:+<depend>$3</depend>}
</package>
XML
}

cd "$WORK"
git init -q -b main . && git config user.email t@duatic.invalid && git config user.name t
pkg a 1.0.0; pkg nested/b 2.0.0; echo src > a/main.cpp
printf 'Changelog\n=========\n' | tee a/CHANGELOG.rst > nested/b/CHANGELOG.rst
git add -A && git commit -qm base

pkg a 1.1.0; pkg nested/b 2.0.1
printf '1.1.0\n-----\n* feat: x\n' >> a/CHANGELOG.rst; printf '2.0.1\n-----\n' >> nested/b/CHANGELOG.rst
check "versions and changelogs only" "true"

pkg a 1.2.0 rclcpp
check "a dependency added beside the version" "false"

echo more >> a/main.cpp
check "a source file" "false"

pkg c 0.1.0
check "a new package.xml" "false"

git rm -q nested/b/CHANGELOG.rst
check "a deleted changelog" "false"

echo note > a/CHANGELOG.md
check "a changelog under another name" "false"

git commit -q --allow-empty -m empty
got=$( python3 "$TOOL" HEAD^ HEAD 2>/dev/null )
if [ "$got" = "true" ]; then printf '  PASS  %-56s\n' "an empty change"; pass=$((pass+1))
else printf '  FAIL  %-56s\n' "an empty change"; fail=$((fail+1)); fi

echo
echo "  $pass passed, $fail failed"
[ "$fail" -eq 0 ]
