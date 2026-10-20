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

# Drive expand_repos.py through its cases, against throwaway git remotes.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOL="$HERE/expand_repos.py"
WORK="$(mktemp -d)"
trap 'rm -r "$WORK" 2>/dev/null' EXIT
pass=0; fail=0

check() {  # check <label> <expected-exit> <exact keys, or error substring> <root list body> [args...]
    local label="$1" want_rc="$2" want="$3" body="$4" got rc
    shift 4
    printf 'repositories:\n%s' "$body" > "$WORK/root.list"
    got=$(python3 "$TOOL" "$WORK/root.list" "$@" 2>&1); rc=$?
    [ "$rc" -eq 0 ] && got=$(printf '%s\n' "$got" | sed -nE 's/^  ([^ :]+):$/\1/p' | paste -sd' ')
    if [ "$rc" -eq "$want_rc" ] && { [[ "$rc" -ne 0 && "$got" == *"$want"* ]] || [ "$got" = "$want" ]; }; then printf '  PASS  %-56s\n' "$label"; pass=$((pass+1))
    else printf '  FAIL  %-56s\n' "$label"; fail=$((fail+1))
         printf '          want: rc=%s %s\n          got:  rc=%s %s\n' "$want_rc" "$want" "$rc" "$got"; fi
}

entry() {  # entry <name> [version] [url suffix]: one repos.list entry for the remote <name>, newline first
    printf '\n  %s:\n    type: git\n    url: file://%s/r/%s%s\n    version: %s\n' "$1" "$WORK" "$1" "${3-.git}" "${2:-main}"
}

remote() {  # remote <name> [repos.list body]: a bare remote on main, carrying that repos.list
    local src="$WORK/src/$1"
    git init -q -b main "$src"
    if [ $# -gt 1 ]; then printf 'repositories:\n%s' "$2" > "$src/repos.list"; else echo leaf > "$src/README"; fi
    git -C "$src" add -A && git -C "$src" -c user.email=t@duatic.invalid -c user.name=t commit -qm init
    git clone -q --bare "$src" "$WORK/r/$1.git"
}

remote leaf
remote mid "$(entry leaf)"
remote top "$(entry mid)"
remote pin_main "$(entry leaf)"
remote pin_tag "$(entry leaf v1)"
remote spelled "$(entry leaf main '')"
remote cyc_x "$(entry cyc_y)"
remote cyc_y "$(entry cyc_x)"
remote back "$(entry self)"
remote upper "$(entry leaf main .GIT)"
remote renamed "$(printf '\n  other_key:\n    type: git\n    url: file://%s/r/leaf.git\n    version: main\n' "$WORK")"

check "pulls in dependencies of dependencies"   0 "top mid leaf"  "$(entry top)"
check "an entry two lists agree on appears once" 0 "mid leaf"     "$(entry mid)$(entry leaf)"
check "url with and without .git agree"         0 "spelled leaf"  "$(entry spelled)$(entry leaf)"
check "a version disagreement is an error"      1 "conflicting entries for leaf" \
    "$(entry pin_main)$(entry pin_tag)"
check "the error names both lists"              1 "pin_tag/repos.list" "$(entry pin_main)$(entry pin_tag)"
check "one repository under two keys is an error" 1 "file://$WORK/r/leaf.git is named both leaf" \
    "$(entry leaf)$(entry renamed)"
check "url case does not matter"               0 "leaf upper"    "$(entry leaf)$(entry upper)"
check "a cycle terminates"                      0 "cyc_x cyc_y"   "$(entry cyc_x)"
check "--exclude-url drops the repo being built" 0 "back"         "$(entry back)" --exclude-url "file://$WORK/r/self"
check "an unreachable repository is an error"   1 "nowhere.git@main" "$(entry nowhere)"

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
