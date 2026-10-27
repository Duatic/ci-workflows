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

# Drive edge_packages.py through its cases, in a throwaway repository.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOL="$HERE/edge_packages.py"
WORK="$(mktemp -d)"
trap 'rm -r "$WORK" 2>/dev/null' EXIT
pass=0; fail=0

check() {  # check <label> <expected-output>
    local label="$1" want="$2" got
    got=$( cd "$WORK" && python3 "$TOOL" 2>/dev/null )
    if [ "$got" = "$want" ]; then printf '  PASS  %-56s\n' "$label"; pass=$((pass+1))
    else printf '  FAIL  %-56s\n' "$label"; fail=$((fail+1))
         printf '          want: %s\n          got:  %s\n' "$want" "$got"; fi
}

pkg() {  # pkg <dir> <version> [root]
    mkdir -p "$WORK/$1"
    cat > "$WORK/$1/package.xml" <<XML
<?xml version="1.0"?>
<package format="3">
  <name>$(basename "$1")</name>
  <version>$2</version>
  <description>test</description>
  <maintainer email="t@duatic.invalid">t</maintainer>
  <license>BSD-3-Clause</license>
  <export>${3:+<duatic_archive_root>$3</duatic_archive_root>}</export>
</package>
XML
}

cd "$WORK"
git init -q -b main . && git config user.email t@duatic.invalid && git config user.name t
commit() { GIT_COMMITTER_DATE="$1" git commit -qm "$2"; }

pkg plain 1.0.0
git add -A && commit "2026-10-27T15:30:12+02:00" "feat: a package without a root"
check "a package without a root is not built" "[]"

pkg nested/routed 0.4.1 public; pkg gated 2.0.0 private/robots
git add -A && commit "2026-10-27T15:30:12+02:00" "feat: routed packages"
sha="$(git rev-parse HEAD)"
s="+git20261027133012.${sha:0:7}"
check "every routed package, at the commit time in UTC and the commit" \
    "[{\"package\": \"gated\", \"version\": \"2.0.0$s\", \"suffix\": \"$s\", \"tag\": \"$sha\", \"root\": \"private/robots\"}, {\"package\": \"routed\", \"version\": \"0.4.1$s\", \"suffix\": \"$s\", \"tag\": \"$sha\", \"root\": \"public\"}]"

echo
echo "  $pass passed, $fail failed"
[ "$fail" -eq 0 ]
