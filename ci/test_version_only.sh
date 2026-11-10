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

# Drive version_only.jq through its cases, on fake compare API responses.
set -uo pipefail
FILTER="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/version_only.jq"
pass=0; fail=0

check() {  # check <label> <expected files needing a build, space-separated> <files JSON>
    local label="$1" want="$2" got
    got=$(jq -r -f "$FILTER" <<<"{\"files\": $3}" 2>&1 | paste -sd' ')
    if [ "$got" = "$want" ]; then printf '  PASS  %-56s\n' "$label"; pass=$((pass+1))
    else printf '  FAIL  %-56s\n' "$label"; fail=$((fail+1))
         printf '          want: %s\n          got:  %s\n' "$want" "$got"; fi
}

VERSION='"@@ -2,3 +2,3 @@\n <name>a</name>\n-  <version>1.0.0</version>\n+  <version>1.1.0</version>\n <description>a</description>"'
DEPEND='"@@ -2,3 +2,4 @@\n-  <version>1.0.0</version>\n+  <version>1.1.0</version>\n+  <depend>rclcpp</depend>"'
SAME_LINE='"@@ -2 +2 @@\n-  <version>1.0.0</version>\n+  <version>1.1.0</version><depend>rclcpp</depend>"'
LOG='"@@ -1,2 +1,5 @@\n Changelog\n+1.1.0\n+-----\n+* feat: x"'

check "versions and changelogs only" "" \
    "[{\"filename\":\"a/package.xml\",\"status\":\"modified\",\"patch\":$VERSION},
      {\"filename\":\"a/CHANGELOG.rst\",\"status\":\"modified\",\"patch\":$LOG},
      {\"filename\":\"package.xml\",\"status\":\"modified\",\"patch\":$VERSION}]"
check "a dependency added beside the version" "a/package.xml" \
    "[{\"filename\":\"a/package.xml\",\"status\":\"modified\",\"patch\":$DEPEND}]"
check "a dependency on the version's line" "a/package.xml" \
    "[{\"filename\":\"a/package.xml\",\"status\":\"modified\",\"patch\":$SAME_LINE}]"
check "a package.xml without a patch" "a/package.xml" \
    "[{\"filename\":\"a/package.xml\",\"status\":\"modified\"}]"
check "a source file" "a/main.cpp" \
    "[{\"filename\":\"a/CHANGELOG.rst\",\"status\":\"modified\",\"patch\":$LOG},
      {\"filename\":\"a/main.cpp\",\"status\":\"modified\",\"patch\":\"@@ -1 +1 @@\n-x\n+y\"}]"
check "a new changelog" "" \
    "[{\"filename\":\"a/CHANGELOG.rst\",\"status\":\"added\",\"patch\":$LOG}]"
check "a new package.xml" "c/package.xml" \
    "[{\"filename\":\"c/package.xml\",\"status\":\"added\",\"patch\":$VERSION}]"
check "a deleted changelog" "a/CHANGELOG.rst" \
    "[{\"filename\":\"a/CHANGELOG.rst\",\"status\":\"removed\"}]"
check "a renamed changelog" "b/CHANGELOG.rst" \
    "[{\"filename\":\"b/CHANGELOG.rst\",\"status\":\"renamed\",\"previous_filename\":\"a/CHANGELOG.rst\"}]"
check "a changelog under another name" "a/CHANGELOG.md" \
    "[{\"filename\":\"a/CHANGELOG.md\",\"status\":\"modified\",\"patch\":$LOG}]"
check "an empty change" "" "[]"
if jq -nc '{files: [range(300) | {filename: "a/CHANGELOG.rst", status: "modified"}]}' |
    jq -r -f "$FILTER" >/dev/null 2>&1; then
    printf '  FAIL  %-56s\n' "a possibly truncated list is an error"; fail=$((fail+1))
else printf '  PASS  %-56s\n' "a possibly truncated list is an error"; pass=$((pass+1)); fi

echo
echo "  $pass passed, $fail failed"
[ "$fail" -eq 0 ]
