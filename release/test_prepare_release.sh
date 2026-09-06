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

# Drive prepare_release.py through every case it exists to handle, in a throwaway repository.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOL="$HERE/prepare_release.py"
WORK="$(mktemp -d)"
REPO="$WORK/repo"; OUT="$WORK/out"
mkdir "$REPO"
trap 'rm -r "$WORK" 2>/dev/null' EXIT
pass=0; fail=0

python3 -c "import catkin_pkg" 2>/dev/null || { echo "catkin_pkg is not importable; the integration case needs it" >&2; exit 1; }

check() {  # check <want-exit> <label> <args...>
    local want="$1" label="$2"; shift 2
    local got
    ( cd "$REPO" && python3 "$TOOL" "$@" ) >"$OUT" 2>&1
    got=$?
    if [ "$got" = "$want" ]; then printf '  PASS  %-56s exit %s\n' "$label" "$got"; pass=$((pass+1))
    else printf '  FAIL  %-56s exit %s want %s\n' "$label" "$got" "$want"; fail=$((fail+1))
         sed 's/^/          /' "$OUT"; fi
}

expect() {  # expect <label> <count> <pattern> <file>   (relative to the repo, or absolute)
    local label="$1" want="$2" pattern="$3" file="$4" got
    case "$file" in /*) ;; *) file="$REPO/$file" ;; esac
    got=$(grep -c -- "$pattern" "$file" 2>/dev/null || true)
    if [ "$got" = "$want" ]; then printf '  PASS  %-56s %s\n' "$label" "$got"; pass=$((pass+1))
    else printf '  FAIL  %-56s %s want %s\n' "$label" "$got" "$want"; fail=$((fail+1))
         sed 's/^/          /' "$file"; fi
}

line() {  # line <label> <n> <exact text> <file>: line n of the file is exactly this
    local label="$1" n="$2" want="$3" file="$REPO/$4"
    if [ "$(sed -n "${n}p" "$file")" = "$want" ]; then printf '  PASS  %-56s\n' "$label"; pass=$((pass+1))
    else printf '  FAIL  %-56s\n' "$label"; fail=$((fail+1)); sed -n 1,6p "$file" | sed 's/^/          /'; fi
}

absent() {  # absent <label> <file>
    if [ ! -e "$REPO/$2" ]; then printf '  PASS  %-56s\n' "$1"; pass=$((pass+1))
    else printf '  FAIL  %-56s\n' "$1"; fail=$((fail+1)); fi
}

pkg() {  # pkg <dir> <version>
    mkdir -p "$REPO/$1"
    cat > "$REPO/$1/package.xml" <<EOF
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
touch_commit() {  # touch_commit <dir> <subject> [body]
    echo "$2" >> "$REPO/$1/work.txt"
    git -C "$REPO" add -A
    if [ -n "${3:-}" ]; then git -C "$REPO" commit -qm "$2" -m "$3"; else git -C "$REPO" commit -qm "$2"; fi
}
release_commit() {  # release_commit <pkg> <version>: commit what the tool wrote and tag it
    git -C "$REPO" add -A && git -C "$REPO" commit -qm "release: $1 $2 (#0)" && git -C "$REPO" tag "$1/$2"
}
prepend() {  # prepend <file> <text>: put text above the file's current content
    { printf '%b' "$2"; cat "$REPO/$1"; } > "$REPO/$1.new" && mv "$REPO/$1.new" "$REPO/$1"
}

cd "$REPO"
git init -q -b main . && git config user.email t@duatic.invalid && git config user.name t
pkg pkg_a 1.0.0
git add -A && git commit -qm "feat: add pkg_a"

echo "=== the first release has no tag, so it starts after the commit that set the version ==="
touch_commit pkg_a "feat: something (#1)"
check 0 "no tag, one feature since" --package pkg_a
expect "package.xml bumped to a minor" 1 '<version>1.1.0</version>' pkg_a/package.xml
expect "one version section" 1 '^1\.1\.0 (' pkg_a/CHANGELOG.rst
expect "the feature is recorded, with its PR number" 1 '^\* feat: something (#1)$' pkg_a/CHANGELOG.rst
expect "the creation commit is not" 0 'add pkg_a' pkg_a/CHANGELOG.rst
release_commit pkg_a 1.1.0

echo "=== bumps follow the commits ==="
touch_commit pkg_a "fix: x"
check 0 "a fix is a patch" --package pkg_a
expect "1.1.1" 1 '<version>1.1.1</version>' pkg_a/package.xml
release_commit pkg_a 1.1.1

touch_commit pkg_a "feat!: y"
check 0 "a bang is a major" --package pkg_a
expect "2.0.0" 1 '<version>2.0.0</version>' pkg_a/package.xml
release_commit pkg_a 2.0.0

touch_commit pkg_a "fix: w" "BREAKING CHANGE: the w behaviour changed"
check 0 "--bump patch over a derived major" --package pkg_a --bump patch
expect "2.0.1 chosen" 1 '<version>2.0.1</version>' pkg_a/package.xml
expect "the summary says it overrode" 1 'overriding the derived \*\*major\*\*' "$OUT"
expect "and names the breaking commit under the warning" 1 '^- fix: w$' <(grep -A1 'non-major version' "$OUT")
git checkout -q -- pkg_a
check 0 "the same without the override" --package pkg_a
expect "a BREAKING CHANGE footer is a major" 1 '<version>3.0.0</version>' pkg_a/package.xml
release_commit pkg_a 3.0.0

echo "=== only changes worth telling a user about are kept ==="
touch_commit pkg_a "chore: a"
touch_commit pkg_a "ci: b"
touch_commit pkg_a "test: c"
touch_commit pkg_a "feat: d"
touch_commit pkg_a "just a message"
check 0 "chore, ci, test, feat and an unprefixed subject" --package pkg_a
expect "feat kept" 1 '^\* feat: d$' pkg_a/CHANGELOG.rst
expect "unprefixed kept" 1 '^\* just a message$' pkg_a/CHANGELOG.rst
expect "chore, ci, test dropped" 0 '^\* \(chore\|ci\|test\): ' pkg_a/CHANGELOG.rst
line "feat before the unprefixed one" 3 "* feat: d" pkg_a/CHANGELOG.rst
release_commit pkg_a 3.1.0

echo "=== a sibling package's commits stay out ==="
pkg pkg_b 0.1.0
git add -A && git commit -qm "feat: add pkg_b"
touch_commit pkg_b "feat: only b"
touch_commit pkg_a "fix: a again"
check 0 "pkg_a with pkg_b changed alongside" --package pkg_a
expect "pkg_a has its fix" 1 '^\* fix: a again$' pkg_a/CHANGELOG.rst
expect "and not pkg_b's feature" 0 'only b' pkg_a/CHANGELOG.rst
release_commit pkg_a 3.1.1

echo "=== changed headers are called out for review ==="
mkdir -p pkg_a/include && echo "int x;" > pkg_a/include/x.hpp
git add -A && git commit -qm "feat: header"
check 0 "a header changed since the tag" --package pkg_a
expect "the summary lists it" 1 'pkg_a/include/x.hpp' "$OUT"
release_commit pkg_a 3.2.0

echo "=== an Upcoming changes section is folded in first and removed ==="
prepend pkg_a/CHANGELOG.rst 'Upcoming changes\n----------------\n* old pending note\n\n'
git add -A && git commit -qm "docs: stage a note"
check 0 "pending section present" --package pkg_a
expect "its bullet moved into the release" 1 '^\* old pending note$' pkg_a/CHANGELOG.rst
expect "the docs commit is there too" 1 '^\* docs: stage a note$' pkg_a/CHANGELOG.rst
expect "no pending section remains" 0 '^Upcoming changes$' pkg_a/CHANGELOG.rst
line "the hand-written bullet leads the section" 3 "* old pending note" pkg_a/CHANGELOG.rst
release_commit pkg_a 3.2.1

echo "=== refusals leave the tree untouched ==="
touch_commit pkg_a "chore: only housekeeping"
check 1 "nothing left after filtering" --package pkg_a
expect "version unchanged" 1 '<version>3.2.1</version>' pkg_a/package.xml
touch_commit pkg_a "fix: q"
git tag pkg_a/3.2.2
check 1 "the tag for the next version already exists" --package pkg_a
expect "version unchanged" 1 '<version>3.2.1</version>' pkg_a/package.xml
git tag -d pkg_a/3.2.2 >/dev/null
check 1 "a package that does not exist" --package pkg_nope

echo "=== the result passes the checks a release pull request gets ==="
git checkout -qb release/pkg_a-3.2.2
check 0 "prepare on a branch" --package pkg_a
git add -A && git commit -qm "release: pkg_a 3.2.2"
( cd "$REPO" && python3 "$HERE/check_changelog_format.py" --base main --head HEAD ) >"$OUT" 2>&1
[ $? -eq 0 ] && { printf '  PASS  %-56s\n' "check_changelog_format.py accepts it"; pass=$((pass+1)); } \
             || { printf '  FAIL  %-56s\n' "check_changelog_format.py accepts it"; fail=$((fail+1)); sed 's/^/          /' "$OUT"; }
( cd "$REPO" && python3 "$HERE/check_release_pr.py" --base main --head HEAD --title "release: pkg_a 3.2.2" ) >"$OUT" 2>&1
[ $? -eq 0 ] && { printf '  PASS  %-56s\n' "check_release_pr.py accepts it"; pass=$((pass+1)); } \
             || { printf '  FAIL  %-56s\n' "check_release_pr.py accepts it"; fail=$((fail+1)); sed 's/^/          /' "$OUT"; }
git checkout -q main

echo "=== a brand-new package with only its creation commit releases from that ==="
pkg pkg_c 0.1.0
git add -A && git commit -qm "feat: add pkg_c"
check 0 "pkg_c, one commit in its history" --package pkg_c
expect "changelog created" 1 '^\* feat: add pkg_c$' pkg_c/CHANGELOG.rst
expect "0.2.0" 1 '<version>0.2.0</version>' pkg_c/package.xml
release_commit pkg_c 0.2.0

echo "=== a version set by hand, with nothing after it, is not a release ==="
pkg pkg_d 0.1.0
git add -A && git commit -qm "feat: add pkg_d"
touch_commit pkg_d "feat: one"
touch_commit pkg_d "fix: two"
pkg pkg_d 1.0.0
git commit -qam "release: pkg_d 1.0.0"
check 1 "hand-bumped to 1.0.0, no tag, nothing since" --package pkg_d
expect "version unchanged" 1 '<version>1.0.0</version>' pkg_d/package.xml
absent "no changelog was written" pkg_d/CHANGELOG.rst
touch_commit pkg_d "fix: three"
check 0 "then one fix after the hand bump" --package pkg_d
expect "only that fix is in the notes" 1 '^\* fix: three$' pkg_d/CHANGELOG.rst
expect "the commits before 1.0.0 are not" 0 'feat: one\|fix: two' pkg_d/CHANGELOG.rst
release_commit pkg_d 1.0.1

echo "=== a commit that only reformats package.xml is not a release boundary ==="
pkg pkg_e 1.0.0
git add -A && git commit -qm "feat: add pkg_e"
touch_commit pkg_e "feat: real one"
sed -i 's/^  <version>/    <version>/' pkg_e/package.xml
git commit -qam "style: reindent package.xml"
touch_commit pkg_e "fix: real two"
check 0 "feature, reindent, fix, no tag" --package pkg_e
expect "the feature before the reindent is kept" 1 '^\* feat: real one$' pkg_e/CHANGELOG.rst
expect "so is the fix after it" 1 '^\* fix: real two$' pkg_e/CHANGELOG.rst
expect "minor, from the feature" 1 '<version>1.1.0</version>' pkg_e/package.xml
release_commit pkg_e 1.1.0

echo "=== hand-written bullets may use any RST marker; anything else stops the release ==="
touch_commit pkg_e "fix: after"
prepend pkg_e/CHANGELOG.rst 'Upcoming changes\n----------------\n- dash note\n+ plus note\n\n'
git add -A && git commit -qm "docs: notes with other markers"
check 0 "dash and plus bullets" --package pkg_e
expect "both survive, as asterisk bullets" 2 '^\* \(dash\|plus\) note$' pkg_e/CHANGELOG.rst
release_commit pkg_e 1.1.1
touch_commit pkg_e "fix: again"
prepend pkg_e/CHANGELOG.rst 'Upcoming changes\n----------------\n* fine\nA paragraph that is not a bullet.\n\n'
git add -A && git commit -qm "docs: a stray paragraph"
check 1 "a paragraph under the pending heading" --package pkg_e
expect "the paragraph is named" 1 'A paragraph that is not a bullet' "$OUT"
expect "the file was left alone" 1 '^Upcoming changes$' pkg_e/CHANGELOG.rst
expect "and so was the version" 1 '<version>1.1.1</version>' pkg_e/package.xml

echo "=== a long URL stays on one line ==="
pkg pkg_f 1.0.0
git add -A && git commit -qm "feat: add pkg_f"
URL="https://github.com/Duatic/duatic_teleop/blob/main/duatic_teleop_gamepad/doc/index.md#configuration-of-the-deadman-switch"
touch_commit pkg_f "docs: see $URL"
check 0 "a subject carrying a long URL" --package pkg_f
expect "the URL is intact" 1 "$URL" pkg_f/CHANGELOG.rst
release_commit pkg_f 1.0.1

echo "=== a <version> with a compatibility attribute keeps it ==="
pkg pkg_g 1.0.0
sed -i 's|<version>1.0.0</version>|<version compatibility="0.9.0">1.0.0</version>|' pkg_g/package.xml
git add -A && git commit -qm "feat: add pkg_g"
touch_commit pkg_g "fix: g"
check 0 "bump with the attribute present" --package pkg_g
expect "attribute kept, version bumped" 1 '<version compatibility="0.9.0">1.0.1</version>' pkg_g/package.xml
release_commit pkg_g 1.0.1

echo "=== BREAKING CHANGE counts only as a footer ==="
touch_commit pkg_g "fix: h" "This is not a BREAKING CHANGE, just a note about one."
check 0 "prose mentioning it in the body" --package pkg_g
expect "stays a patch" 1 '>1.0.2</version>' pkg_g/package.xml
release_commit pkg_g 1.0.2
touch_commit pkg_g "fix: i" "BREAKING-CHANGE: the hyphenated form"
check 0 "the hyphenated footer" --package pkg_g
expect "is a major" 1 '>2.0.0</version>' pkg_g/package.xml

echo
echo "  $pass passed, $fail failed"
[ "$fail" -eq 0 ]
