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

"""Prepare the release of one package: the changelog section, the version bump, and a summary.

Commits are those touching the package's directory since the tag <package>/<version> with the
highest version, or since the commit that set the current <version> when there is no tag yet, or
the package's whole history at its birth. Each subject is read with the grammar the title check
enforces:

  * "!" before the colon, or a "BREAKING CHANGE:" footer, marks a breaking change;
  * feat, fix, perf, refactor and docs are kept, in that order after breaking changes;
  * chore, ci, test, build and release are dropped;
  * anything else is kept last, so an unlabelled change is never silently lost.

The bump is major if anything is breaking, minor if anything is a feature, patch otherwise.
--bump overrides it. Bullets under "Upcoming changes" lead the new section and that heading is
removed; anything there that is not a flat bullet stops the release instead of being dropped.

Usage:  prepare_release.py --package NAME [--bump major|minor|patch] [--path DIR] [--summary FILE]
Exit 0 with package.xml and CHANGELOG.rst rewritten, 1 with nothing written.
"""

import argparse
import datetime
import os
import re
import subprocess
import sys
import textwrap
import xml.etree.ElementTree as ET
from pathlib import Path

# REP-132, and the exact shape catkin_pkg parses: X.Y.Z, one space, a date in parentheses.
SECTION = re.compile(r"^(\d+\.\d+\.\d+) \((.+)\)$")
# A section title is followed by a line of one repeated punctuation character.
UNDERLINE = re.compile(r"^[-~^\"'`#*+=]{2,}$")
BULLET = re.compile(r"^[-*+] ")
PENDING = "Upcoming changes"
# The grammar the title check enforces, so a squash-merged subject is a pull request title.
CONVENTIONAL = re.compile(r"^(\w+)(\([^)]*\))?(!)?:\s+\S")
BREAKING = re.compile(r"^BREAKING[ -]CHANGE:", re.M)
KEPT = ["feat", "fix", "perf", "refactor", "docs"]
DROPPED = {"chore", "ci", "test", "build", "release"}
BUMPS = ["patch", "minor", "major"]
WIDTH = 100


def git(*args, allow_fail=False):
    r = subprocess.run(["git", *args], capture_output=True, text=True)
    if r.returncode and not allow_fail:
        raise SystemExit(f'git {" ".join(args)}: {r.stderr.strip()}')
    return r.stdout


def as_tuple(v):
    try:
        return tuple(int(p) for p in v.split("."))
    except (ValueError, AttributeError):
        return None


def find_package(name):
    """Directory of the tracked package.xml naming this package, or None."""
    for path in git("ls-files", "--", ":(glob)**/package.xml").split():
        try:
            if (ET.parse(path).getroot().findtext("name") or "").strip() == name:
                return Path(path).parent
        except ET.ParseError:
            continue
    return None


def last_tag(name):
    """The <name>/<version> tag with the highest version, or None."""
    best = None
    for tag in git("tag", "--list", f"{name}/*").split():
        v = as_tuple(tag[len(name) + 1 :])
        if v and len(v) == 3 and (best is None or v > best[0]):
            best = (v, tag)
    return best[1] if best else None


def version_commit(pkg_xml, version):
    """The commit that set <version> to this value, or None."""
    spaces = "[[:space:]]*"
    pattern = f"<version([[:space:]][^>]*)?>{spaces}{re.escape(version)}{spaces}</version>"
    out = git("log", "-1", "--format=%H", "--pickaxe-regex", f"-S{pattern}", "--", str(pkg_xml))
    return out.strip() or None


def birth_commit(pkg_xml):
    """The commit that added package.xml, or None."""
    added = git("log", "--diff-filter=A", "--format=%H", "--", str(pkg_xml)).split()
    return added[-1] if added else None


def commits(start, pkg_dir):
    """(subject, body) for each commit touching pkg_dir after start, newest first."""
    rng = f"{start}..HEAD" if start else "HEAD"
    out = git("log", "--no-merges", "--format=%s%x1f%b%x1e", rng, "--", str(pkg_dir))
    entries = []
    for record in out.split("\x1e"):
        if record.strip():
            subject, _, body = record.strip("\n").partition("\x1f")
            entries.append((subject.strip(), body))
    return entries


def classify(subject, body):
    """(rank, kind, breaking) for a commit, or None when it is dropped."""
    m = CONVENTIONAL.match(subject)
    kind = m.group(1).lower() if m else None
    breaking = bool(BREAKING.search(body)) or bool(m and m.group(3))
    if breaking:
        return 0, kind, True
    if kind in DROPPED:
        return None
    rank = KEPT.index(kind) + 1 if kind in KEPT else len(KEPT) + 1
    return rank, kind, False


def bumped(version, bump):
    major, minor, patch = as_tuple(version)
    return {
        "major": f"{major + 1}.0.0",
        "minor": f"{major}.{minor + 1}.0",
        "patch": f"{major}.{minor}.{patch + 1}",
    }[bump]


def bullets_of(lines):
    """(bullet texts, lines that are neither a flat bullet nor a continuation) from RST lines."""
    bullets, stray = [], []
    for line in lines:
        if BULLET.match(line):
            bullets.append(line[2:].strip())
        elif line.startswith("  ") and bullets and not BULLET.match(line.strip()):
            bullets[-1] += " " + line.strip()
        elif line.strip():
            stray.append(line)
    return bullets, stray


def is_title(lines, i):
    """Whether lines[i] is a section title: non-blank, with an underline beneath."""
    return (
        i + 1 < len(lines)
        and bool(lines[i].strip())
        and bool(UNDERLINE.match(lines[i + 1].strip()))
    )


def section_start(lines, i):
    """Where the section titled at lines[i] begins: one line earlier if it carries an overline."""
    return i - 1 if i and lines[i - 1].strip() == lines[i + 1].strip() else i


def split_pending(text):
    """(bullets under the pending section, stray lines in it, text with that section removed)."""
    lines = text.split("\n")
    for i in range(len(lines) - 1):
        if lines[i].strip() == PENDING and is_title(lines, i):
            end = len(lines)
            for j in range(i + 2, len(lines) - 1):
                if is_title(lines, j):
                    end = section_start(lines, j)
                    break
            bullets, stray = bullets_of(lines[i + 2 : end])
            return bullets, stray, "\n".join(lines[: section_start(lines, i)] + lines[end:])
    return [], [], text


def wrap(bullet):
    return textwrap.fill(
        bullet,
        WIDTH,
        initial_indent="* ",
        subsequent_indent="  ",
        break_long_words=False,
        break_on_hyphens=False,
    )


def with_section(text, title, bullets):
    """text with a new version section above the first existing one."""
    lines = text.lstrip("\n").split("\n")
    section = [title, "-" * len(title)] + [wrap(b) for b in bullets] + [""]
    for i in range(len(lines) - 1):
        if SECTION.match(lines[i]) and is_title(lines, i):
            at = section_start(lines, i)
            return "\n".join(lines[:at] + section + lines[at:])
    body = "\n".join(lines).rstrip("\n")
    return (body + "\n\n" if body.strip() else "") + "\n".join(section)


def bump_manifest(text, old, new):
    """package.xml text with <version> set to new, or None when old is not there to replace."""
    pattern = rf"(<version(?:\s[^>]*)?>)\s*{re.escape(old)}\s*(</version>)"
    text, n = re.subn(pattern, rf"\g<1>{new}\g<2>", text, count=1)
    return text if n == 1 else None


def summary(name, old, new, derived, chosen, since, entries, headers):
    lines = [f"Releases `{name}` `{old}` -> `{new}`, {since}.", ""]
    if chosen == derived:
        lines.append(f"Bump: **{chosen}**, derived from the commits below.")
    else:
        lines.append(f"Bump: **{chosen}**, overriding the derived **{derived}**.")
    if BUMPS.index(chosen) < BUMPS.index(derived):
        lines.append("")
        lines.append("**The override releases breaking changes under a non-major version:**")
        lines += [f"- {s}" for _, _, s, b in entries if b]
    if headers:
        lines += ["", "Headers changed, so the API or ABI may have:", ""]
        lines += [f"- `{h}`" for h in headers]
    lines += ["", "Changelog:", ""]
    lines += [f"- {s}" for _, _, s, _ in entries]
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--package", required=True, help="the package to release, by name")
    ap.add_argument("--bump", choices=BUMPS, help="override the bump derived from the commits")
    ap.add_argument("--path", default=".", help="the repository root")
    ap.add_argument("--summary", help="write a Markdown summary for the pull request here")
    args = ap.parse_args()
    os.chdir(args.path)

    pkg_dir = find_package(args.package)
    if pkg_dir is None:
        print(f"no package.xml names {args.package}", file=sys.stderr)
        return 1
    pkg_xml = pkg_dir / "package.xml"
    manifest = pkg_xml.read_text()
    old = (ET.fromstring(manifest).findtext("version") or "").strip()
    if not as_tuple(old) or len(as_tuple(old)) != 3:
        print(f"{pkg_xml}: <version> {old!r} is not X.Y.Z", file=sys.stderr)
        return 1

    tag = last_tag(args.package)
    born = birth_commit(pkg_xml)
    if tag:
        start, since = tag, f"since tag `{tag}`"
    else:
        start = version_commit(pkg_xml, old) or born
        since = (
            f"since `{start[:9]}`, which set <version> to {old}; no {args.package}/* tag yet"
            if start
            else "from the package's whole history"
        )
    found = commits(start, pkg_dir)
    if not found and not tag and start and start == born:
        found, since = commits(None, pkg_dir), "from the package's whole history"

    entries = []
    for subject, body in found:
        c = classify(subject, body)
        if c:
            entries.append((c[0], c[1], subject, c[2]))
    entries.sort(key=lambda e: e[0])
    if not entries:
        print(
            f"nothing to release: no commit touching {pkg_dir} {since} survives filtering",
            file=sys.stderr,
        )
        return 1

    derived = (
        "major"
        if any(b for _, _, _, b in entries)
        else ("minor" if any(k == "feat" for _, k, _, _ in entries) else "patch")
    )
    chosen = args.bump or derived
    new = bumped(old, chosen)
    if git("tag", "--list", f"{args.package}/{new}").strip():
        print(f"tag {args.package}/{new} already exists", file=sys.stderr)
        return 1

    bumped_manifest = bump_manifest(manifest, old, new)
    if bumped_manifest is None:
        print(f"{pkg_xml}: could not rewrite <version>{old}</version>", file=sys.stderr)
        return 1

    changelog = pkg_dir / "CHANGELOG.rst"
    text = changelog.read_text() if changelog.exists() else ""
    pending, stray, text = split_pending(text)
    if stray:
        print(f'{changelog}: "{PENDING}" holds lines that are not flat bullets:', file=sys.stderr)
        for line in stray:
            print(f"  {line}", file=sys.stderr)
        return 1
    generated = [s for _, _, s, _ in entries]
    bullets = pending + [s for s in generated if s not in pending]
    title = f"{new} ({datetime.date.today().isoformat()})"

    headers = []
    if start and (pkg_dir / "include").is_dir():
        headers = git(
            "diff", "--name-only", f"{start}..HEAD", "--", str(pkg_dir / "include")
        ).split()

    changelog.write_text(with_section(text, title, bullets))
    pkg_xml.write_text(bumped_manifest)

    body = summary(args.package, old, new, derived, chosen, since, entries, headers)
    if args.summary:
        Path(args.summary).write_text(body)
    print(body, end="")
    print(f"\nwrote {changelog} and {pkg_xml}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
