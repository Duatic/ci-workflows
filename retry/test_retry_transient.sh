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

# Drive retry_transient.py --classify through job log lines seen in failed CI runs.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOL="$HERE/retry_transient.py"
pass=0
fail=0

check() { # check <label> <expected-cause> <log line>
    local label="$1" want="$2" got
    got=$(printf '2026-11-09T07:41:09.8362985Z %s\n' "$3" | python3 "$TOOL" --classify /dev/stdin 2>&1)
    if [ "$got" = "$want" ]; then
        printf '  PASS  %-56s\n' "$label"
        pass=$((pass + 1))
    else
        printf '  FAIL  %-56s\n' "$label"
        fail=$((fail + 1))
        printf '          want: %s\n          got:  %s\n' "$want" "$got"
    fi
}

echo "package mirror unreachable"
check "apt package fetch, seen in duadrive_testbench" "package mirror unreachable" \
    "E: Failed to fetch http://archive.ubuntu.com/ubuntu/pool/main/b/binutils/binutils_2.42-4ubuntu2.10_amd64.deb  Unable to connect to archive.ubuntu.com:http: [IP: 91.189.90.12 80]"
check "apt index timing out, seen in duadrive_simulation" "package mirror unreachable" \
    "W: Failed to fetch http://archive.ubuntu.com/ubuntu/dists/noble/InRelease  Could not connect to archive.ubuntu.com:80 (91.189.90.12), connection timed out"
check "apt progress line, DNS failure on the ROS mirror" "package mirror unreachable" \
    "Err:5 http://packages.ros.org/ros2/ubuntu noble InRelease  Temporary failure resolving 'packages.ros.org'"
check "apt on arm64, connection refused" "package mirror unreachable" \
    "Err:1 http://ports.ubuntu.com/ubuntu-ports noble-updates InRelease  Connection failed [IP: 185.125.190.36 80]  Connection refused"
check "apt hash mismatch while a mirror syncs" "package mirror unreachable" \
    "E: Failed to fetch http://ports.ubuntu.com/ubuntu-ports/dists/noble-updates/main/binary-arm64/Packages.xz  Hash Sum mismatch"
check "apt server error from the security archive" "package mirror unreachable" \
    "E: Failed to fetch http://security.ubuntu.com/ubuntu/dists/noble-security/InRelease  503  Service Unavailable [IP: 91.189.91.82 80]"
check "apt package missing from a mirror mid-sync, seen in duatic_control" "package mirror unreachable" \
    "41.42 E: Failed to fetch http://security.ubuntu.com/ubuntu/pool/main/p/perl/perl-base_5.38.2-3.2ubuntu0.7_amd64.deb  404  Not Found [IP: 91.189.91.81 80]"
check "apt index size mismatch, seen in duatic_scan_2d_merger" "package mirror unreachable" \
    "E: Failed to fetch http://security.ubuntu.com/ubuntu/dists/resolute-security/main/binary-amd64/Packages.gz  File has unexpected size (819537 != 819543). Mirror sync in progress? [IP: 91.189.91.82 80]"
check "apt connection failed, seen in duatic_gazebo" "package mirror unreachable" \
    "E: Failed to fetch http://archive.ubuntu.com/ubuntu/pool/universe/x/xapian-core/libxapian30_1.4.22-1build1_amd64.deb  Connection failed [IP: 91.189.90.12 80]"

echo "github unreachable"
check "git clone, DNS failure" "github unreachable" \
    "fatal: unable to access 'https://github.com/Duatic/duatic_helpers.git/': Could not resolve host: github.com"
check "git clone, server error" "github unreachable" \
    "fatal: unable to access 'https://github.com/Duatic/duatic_helpers.git/': The requested URL returned error: 502"
check "git fetch, connection reset" "github unreachable" \
    "fatal: unable to access 'https://github.com/Duatic/duatic_helpers.git/': Recv failure: Connection reset by peer"
check "curl to the GitHub API" "github unreachable" \
    "curl: (7) Failed to connect to api.github.com port 443 after 129415 ms: Connection timed out"
check "image pull from GHCR, DNS timeout" "github unreachable" \
    'Error response from daemon: Get "https://ghcr.io/v2/": dial tcp: lookup ghcr.io on 127.0.0.53:53: read udp: i/o timeout'
check "image pull from GHCR, TLS timeout" "github unreachable" \
    'Error response from daemon: Get "https://ghcr.io/v2/duatic/ci/manifests/jazzy": net/http: TLS handshake timeout'
check "image push to GHCR, server error" "github unreachable" \
    "failed to push ghcr.io/duatic/duatic_dxtr:ci-jazzy: unexpected status from PUT request: 503 Service Unavailable"
check "pip install from a GitHub archive" "github unreachable" \
    "ERROR: HTTP error 504 while getting https://codeload.github.com/Duatic/pyroki/tar.gz/main"
check "git transfer cut off" "github unreachable" \
    "error: RPC failed; curl 92 HTTP/2 stream 5 was not closed cleanly: CANCEL (err 8)"
check "action download at job setup" "github unreachable" \
    "##[error]Failed to download action 'https://api.github.com/repos/actions/checkout/tarball/abc'. Error: Response status code does not indicate success: 503"
check "rosdep sources download timing out" "github unreachable" \
    "ERROR: unable to process source [https://raw.githubusercontent.com/ros/rosdistro/master/rosdep/base.yaml]: <urlopen error timed out>"

echo "container or runner died"
check "build container killed, seen in duatic_dxtr" "container or runner died" \
    'time="2026-11-09T07:41:09Z" level=error msg="error waiting for container: unexpected EOF"'
check "runner pod shut down" "container or runner died" \
    "##[error]The runner has received a shutdown signal. This can happen when the runner service is stopped, or a manually started runner is canceled."
check "ANSI colour codes around the signature" "container or runner died" \
    $'\x1b[31mtime="2026-11-09T07:41:09Z" level=error msg="error waiting for container: unexpected EOF"\x1b[0m'

echo "not transient"
check "package not released for the distro" "" \
    "E: Unable to locate package ros-rolling-moveit-ros-visualization"
check "rosdep key missing" "" \
    "duatic_duarover_slam: Cannot locate rosdep definition for [nav2_bringup]"
check "pip dependency conflict" "" \
    "ERROR: ResolutionImpossible: for help visit https://pip.pypa.io/en/latest/topics/dependency-resolution/#dealing-with-dependency-conflicts"
check "colcon package build failure" "" \
    "Failed   <<< nav2_mppi_controller [1.61s, exited with code 1]"
check "repository missing on GitHub" "" \
    "fatal: repository 'https://github.com/Duatic/duatic_missing.git/' not found"
check "GitHub denying access" "" \
    "remote: Permission to Duatic/duatic_helpers.git denied to github-actions[bot]."
check "image not found on GHCR" "" \
    "Error response from daemon: manifest unknown: ghcr.io/duatic/duatic_dxtr:ci-humble not found"
check "apt warning about a third-party mirror" "" \
    "W: Failed to fetch https://example.com/apt/dists/noble/InRelease  Could not connect to example.com:443"
check "test connecting to a robot timing out" "" \
    "[ERROR] [driver]: Connection timed out while waiting for 192.168.1.10"
check "GitHub URL and a timeout on different lines" "" \
    $'Cloning https://github.com/Duatic/duatic_helpers.git\n[ERROR] [driver]: Connection timed out'

echo
echo "passed: $pass  failed: $fail"
[ "$fail" -eq 0 ]
