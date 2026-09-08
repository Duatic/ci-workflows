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

# Drive changelog_section.py through its cases, against a throwaway file.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOL="$HERE/changelog_section.py"
WORK="$(mktemp -d)"
CHANGELOG="$WORK/CHANGELOG.rst"
trap 'rm -r "$WORK" 2>/dev/null' EXIT
pass=0; fail=0

check() {  # check <want-exit> <label> <version> [want-output]
    local want="$1" label="$2" version="$3" want_out="${4:-}"
    local got out
    out=$(python3 "$TOOL" "$CHANGELOG" "$version" 2>"$WORK/err")
    got=$?
    if [ "$got" != "$want" ]; then
        printf '  FAIL  %-56s exit %s want %s\n' "$label" "$got" "$want"
        sed 's/^/          /' "$WORK/err"
        fail=$((fail+1))
        return
    fi
    if [ -n "$want_out" ] && [ "$out" != "$want_out" ]; then
        printf '  FAIL  %-56s output mismatch\n' "$label"
        printf '          want: %s\n          got:  %s\n' "$want_out" "$out"
        fail=$((fail+1))
        return
    fi
    printf '  PASS  %-56s exit %s\n' "$label" "$got"
    pass=$((pass+1))
}

cat > "$CHANGELOG" <<'EOF'
Upcoming changes
----------------
* staged for later

2.0.0 (2026-02-01)
------------------
* feat: second release
* fix: a follow-up

1.0.0 (2026-01-01)
------------------
* First public release.
EOF

check 0 "the middle section, bounded by the next one" "2.0.0" "$(printf '* feat: second release\n* fix: a follow-up')"
check 0 "the last section, bounded by end of file" "1.0.0" "* First public release."
check 1 "a version with no section" "9.9.9"

echo
echo "  $pass passed, $fail failed"
[ "$fail" -eq 0 ]
