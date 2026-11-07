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

# Drive build_matrix.py through its cases.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOL="$HERE/build_matrix.py"
pass=0; fail=0

check() {  # check <label> <build> <distros> <expected-output>
    local label="$1" want="$4" got
    got=$(BUILD="$2" DISTROS="$3" python3 "$TOOL" 2>&1) || got="exit $? $got"
    if [ "$got" = "$want" ]; then printf '  PASS  %-56s\n' "$label"; pass=$((pass+1))
    else printf '  FAIL  %-56s\n' "$label"; fail=$((fail+1))
         printf '          want: %s\n          got:  %s\n' "$want" "$got"; fi
}

ALL='["humble", "jazzy", "kilted", "lyrical", "rolling"]'
check "a ROS package builds for every distro" '[{"package": "a", "kind": "ros"}]' '["jazzy", "kilted"]' \
    '[{"package": "a", "kind": "ros", "ros_distro": "jazzy"}, {"package": "a", "kind": "ros", "ros_distro": "kilted"}]'
check "a package without a kind is a ROS package" '[{"package": "a"}]' '["jazzy", "kilted"]' \
    '[{"package": "a", "ros_distro": "jazzy"}, {"package": "a", "ros_distro": "kilted"}]'
check "a system package builds once per Ubuntu release" '[{"package": "s", "kind": "system"}]' "$ALL" \
    '[{"package": "s", "kind": "system", "ros_distro": "humble"}, {"package": "s", "kind": "system", "ros_distro": "jazzy"}, {"package": "s", "kind": "system", "ros_distro": "lyrical"}]'
check "for that release's system distro, whatever is listed" '[{"package": "s", "kind": "system"}]' '["kilted", "rolling"]' \
    '[{"package": "s", "kind": "system", "ros_distro": "jazzy"}, {"package": "s", "kind": "system", "ros_distro": "lyrical"}]'
check "both kinds together" '[{"package": "a", "kind": "ros"}, {"package": "s", "kind": "system"}]' '["jazzy", "kilted"]' \
    '[{"package": "a", "kind": "ros", "ros_distro": "jazzy"}, {"package": "a", "kind": "ros", "ros_distro": "kilted"}, {"package": "s", "kind": "system", "ros_distro": "jazzy"}]'
check "nothing to build" '[]' "$ALL" '[]'
check "an unknown distro fails" '[{"package": "a"}]' '["noetic"]' \
    "exit 1 no Ubuntu release known for ROS distro 'noetic'"
check "an unknown kind fails" '[{"package": "a", "kind": "snap"}]' '["jazzy"]' \
    "exit 1 a: kind is 'snap', not ros or system"

echo
echo "  $pass passed, $fail failed"
[ "$fail" -eq 0 ]
