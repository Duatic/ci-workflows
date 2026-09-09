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

# Drive released_packages.py through its cases, in a throwaway repository.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOL="$HERE/released_packages.py"
WORK="$(mktemp -d)"
trap 'rm -r "$WORK" 2>/dev/null' EXIT
pass=0; fail=0

check() {  # check <label> <expected-output>
    local label="$1" want="$2" got
    got=$( cd "$WORK" && python3 "$TOOL" --base main --head HEAD 2>&1 )
    if [ "$got" = "$want" ]; then printf '  PASS  %-56s\n' "$label"; pass=$((pass+1))
    else printf '  FAIL  %-56s\n' "$label"; fail=$((fail+1))
         printf '          want: %s\n          got:  %s\n' "$want" "$got"; fi
}

pkg() {  # pkg <dir> <version>
    mkdir -p "$WORK/$1"
    cat > "$WORK/$1/package.xml" <<EOF
<?xml version="1.0"?>
<package format="3">
  <name>$(basename "$1")</name>
  <version>$2</version>
  <description>test</description>
  <maintainer email="t@duatic.invalid">t</maintainer>
  <license>BSD-3-Clause</license>
</package>
EOF
}

cd "$WORK"
git init -q -b main . && git config user.email t@duatic.invalid && git config user.name t
pkg pkg_a 1.0.0; pkg nested/pkg_b 0.1.0
printf '1.0.0 (2026-01-01)\n------------------\n* first\n' > pkg_a/CHANGELOG.rst
git add -A && git commit -qm baseline

git checkout -qb one
pkg pkg_a 1.1.0; git commit -qam "release: pkg_a 1.1.0"
check "one package bumped" "pkg_a 1.1.0 pkg_a"

git checkout -q main && git checkout -qb two
pkg pkg_a 1.1.0; pkg nested/pkg_b 0.2.0; git commit -qam "release: both"
check "two packages bumped, sorted by directory" "$(printf 'pkg_b 0.2.0 nested/pkg_b\npkg_a 1.1.0 pkg_a')"

git checkout -q main && git checkout -qb none
echo "* note" >> pkg_a/CHANGELOG.rst; git commit -qam "docs: a note"
check "a changelog edit alone releases nothing" ""

git checkout -q main && git checkout -qb new
pkg pkg_c 0.1.0; git add -A && git commit -qm "feat: add pkg_c"
check "a new package counts as released at its first version" "pkg_c 0.1.0 pkg_c"

git checkout -q main && git checkout -qb moved
mkdir -p group && git mv pkg_a group/pkg_a && git commit -qm "refactor: move pkg_a"
check "a package moved at the same version releases nothing" ""

git checkout -q main && git checkout -qb moved-and-bumped
mkdir -p group && git mv pkg_a group/pkg_a && pkg group/pkg_a 1.1.0
git add -A && git commit -qm "release: pkg_a 1.1.0, moved"
check "a package moved and bumped is released once, at its new path" "pkg_a 1.1.0 group/pkg_a"

echo
echo "  $pass passed, $fail failed"
[ "$fail" -eq 0 ]
