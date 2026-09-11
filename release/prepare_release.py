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

"""Prepare a release: the changelog section(s), the version bump(s), and a summary.

--package NAME releases one package. The bump is derived from its commits since the tag
<package>/<version> with the highest version, or since the commit that set the current <version>
when there is no tag yet, or the package's whole history at its birth. --bump overrides it.

--repo releases every package in the repository together, at one shared version: the highest
current version among them, bumped by --bump, which is required here since there is no single
commit history to derive one from. A package with nothing to report gets "No changes." instead of
being skipped. Packages named in release-exclude.txt at the repository root (one per line, `#`
comments allowed) are left untouched entirely.

Either way, each commit subject is read with the grammar the title check enforces:

  * "!" before the colon, or a "BREAKING CHANGE:" footer, marks a breaking change;
  * feat (or feature), deprecate, fix, perf, refactor and docs are kept, in that order after
    breaking changes;
  * chore, ci, test, build and release are dropped;
  * anything else is kept last, so an unlabelled change is never silently lost.

Bullets under "Upcoming changes" lead a package's new section and that heading is removed;
anything there that is not a flat bullet stops the release instead of being dropped.

Usage:  prepare_release.py --package NAME [--bump B] [--path DIR] [--summary FILE] [--version-out FILE]
        prepare_release.py --repo --bump B [--path DIR] [--summary FILE] [--version-out FILE]
Exit 0 with every touched package.xml and CHANGELOG.rst rewritten, 1 with nothing written.
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
NO_CHANGES = "No changes."
EXCLUDE_FILE = "release-exclude.txt"
# The grammar the title check enforces, so a squash-merged subject is a pull request title.
CONVENTIONAL = re.compile(r"^(\w+)(\([^)]*\))?(!)?:\s+\S")
BREAKING = re.compile(r"^BREAKING[ -]CHANGE:", re.M)
KEPT = ["feat", "deprecate", "fix", "perf", "refactor", "docs"]
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


def is_version(v):
    t = as_tuple(v)
    return t is not None and len(t) == 3


def find_package(name):
    """Directory of the tracked package.xml naming this package, or None."""
    for name_, pkg_dir in all_packages():
        if name_ == name:
            return pkg_dir
    return None


def all_packages():
    """(name, directory) for every tracked package.xml."""
    out = []
    for path in git("ls-files", "--", ":(glob)**/package.xml").split():
        try:
            name = (ET.parse(path).getroot().findtext("name") or "").strip()
        except ET.ParseError:
            continue
        if name:
            out.append((name, Path(path).parent))
    return out


def read_exclusions():
    """Package names listed in release-exclude.txt at the repository root, or an empty set."""
    path = Path(EXCLUDE_FILE)
    if not path.exists():
        return set()
    names = set()
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            names.add(line.split()[0])
    return names


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
    kind = "feat" if kind == "feature" else kind
    breaking = bool(BREAKING.search(body)) or bool(m and m.group(3))
    if breaking:
        return 0, kind, True
    if kind in DROPPED:
        return None
    rank = KEPT.index(kind) + 1 if kind in KEPT else len(KEPT) + 1
    return rank, kind, False


def derive_bump(entries):
    if any(b for _, _, _, b in entries):
        return "major"
    if any(k in ("feat", "deprecate") for _, k, _, _ in entries):
        return "minor"
    return "patch"


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


def gather(name, pkg_dir, pkg_xml, old):
    """Everything about one package's history since its last release and its changelog state."""
    tag = last_tag(name)
    born = birth_commit(pkg_xml)
    if tag:
        start, since = tag, f"since tag `{tag}`"
    else:
        start = version_commit(pkg_xml, old) or born
        since = (
            f"since `{start[:9]}`, which set <version> to {old}; no {name}/* tag yet"
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

    headers = []
    if start and (pkg_dir / "include").is_dir():
        headers = git(
            "diff", "--name-only", f"{start}..HEAD", "--", str(pkg_dir / "include")
        ).split()

    changelog = pkg_dir / "CHANGELOG.rst"
    text = changelog.read_text() if changelog.exists() else ""
    pending, stray, text = split_pending(text)

    return {
        "entries": entries,
        "since": since,
        "headers": headers,
        "pending": pending,
        "stray": stray,
        "text": text,
        "changelog": changelog,
    }


def stray_message(changelog, stray):
    lines = "\n".join(f"  {line}" for line in stray)
    return f'{changelog}: "{PENDING}" holds lines that are not flat bullets:\n{lines}'


def bullets_for(gathered):
    """The bullets a package's new section should carry: hand-written ones lead, generated follow."""
    generated = [s for _, _, s, _ in gathered["entries"]]
    return gathered["pending"] + [s for s in generated if s not in gathered["pending"]]


def summary_one(name, old, new, derived, chosen, since, entries, headers):
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


def summary_repo(new, bump, prepared, excluded):
    lines = [f"Releases every package at `{new}` (**{bump}**).", ""]
    breaking = [
        (name, s) for name, p in sorted(prepared.items()) for _, _, s, b in p["entries"] if b
    ]
    if breaking and bump != "major":
        lines.append(f"**Breaking changes are going out under a non-major bump ({bump}):**")
        lines += [f"- {name}: {s}" for name, s in breaking]
        lines.append("")
    for name, p in sorted(prepared.items()):
        if p["bullets"] == [NO_CHANGES]:
            lines.append(f"- **{name}**: {NO_CHANGES}")
        else:
            lines.append(f"- **{name}**:")
            lines += [f"  - {s}" for s in p["bullets"]]
            if p["headers"]:
                lines.append(f"  - headers changed under include/: {', '.join(p['headers'])}")
    if excluded:
        lines += ["", "Excluded: " + ", ".join(sorted(excluded))]
    return "\n".join(lines) + "\n"


def release_package(name, bump_override, summary_path, version_out_path):
    pkg_dir = find_package(name)
    if pkg_dir is None:
        print(f"no package.xml names {name}", file=sys.stderr)
        return 1
    pkg_xml = pkg_dir / "package.xml"
    manifest = pkg_xml.read_text()
    old = (ET.fromstring(manifest).findtext("version") or "").strip()
    if not is_version(old):
        print(f"{pkg_xml}: <version> {old!r} is not X.Y.Z", file=sys.stderr)
        return 1

    gathered = gather(name, pkg_dir, pkg_xml, old)
    if gathered["stray"]:
        print(stray_message(gathered["changelog"], gathered["stray"]), file=sys.stderr)
        return 1

    bullets = bullets_for(gathered)
    if not bullets:
        print(
            f'nothing to release: no commit touching {pkg_dir} {gathered["since"]} survives '
            f'filtering, and no note is staged under "{PENDING}"',
            file=sys.stderr,
        )
        return 1

    derived = derive_bump(gathered["entries"])
    chosen = bump_override or derived
    new = bumped(old, chosen)
    if git("tag", "--list", f"{name}/{new}").strip():
        print(f"tag {name}/{new} already exists", file=sys.stderr)
        return 1

    bumped_manifest = bump_manifest(manifest, old, new)
    if bumped_manifest is None:
        print(f"{pkg_xml}: could not rewrite <version>{old}</version>", file=sys.stderr)
        return 1

    today = datetime.date.today().isoformat()
    new_text = with_section(gathered["text"], f"{new} ({today})", bullets)
    gathered["changelog"].write_text(new_text)
    pkg_xml.write_text(bumped_manifest)

    body = summary_one(
        name, old, new, derived, chosen, gathered["since"], gathered["entries"], gathered["headers"]
    )
    if summary_path:
        Path(summary_path).write_text(body)
    if version_out_path:
        Path(version_out_path).write_text(new + "\n")
    print(body, end="")
    print(f'\nwrote {gathered["changelog"]} and {pkg_xml}')
    return 0


def release_repo(bump, summary_path, version_out_path):
    excluded = read_exclusions()
    packages = {}
    for name, pkg_dir in all_packages():
        if name in excluded:
            continue
        if name in packages:
            print(
                f"two packages are both named {name}: {packages[name]} and {pkg_dir}",
                file=sys.stderr,
            )
            return 1
        packages[name] = pkg_dir
    if not packages:
        print("nothing to release: every package is excluded, or none exist", file=sys.stderr)
        return 1

    manifests = {}
    for name, pkg_dir in packages.items():
        pkg_xml = pkg_dir / "package.xml"
        manifest = pkg_xml.read_text()
        old = (ET.fromstring(manifest).findtext("version") or "").strip()
        if not is_version(old):
            print(f"{pkg_xml}: <version> {old!r} is not X.Y.Z", file=sys.stderr)
            return 1
        manifests[name] = (pkg_dir, pkg_xml, manifest, old)

    new = bumped(max((m[3] for m in manifests.values()), key=as_tuple), bump)
    clashes = [f"{n}/{new}" for n in manifests if git("tag", "--list", f"{n}/{new}").strip()]
    if clashes:
        print("tag(s) already exist: " + ", ".join(clashes), file=sys.stderr)
        return 1

    today = datetime.date.today().isoformat()
    prepared = {}
    for name, (pkg_dir, pkg_xml, manifest, old) in manifests.items():
        gathered = gather(name, pkg_dir, pkg_xml, old)
        if gathered["stray"]:
            print(stray_message(gathered["changelog"], gathered["stray"]), file=sys.stderr)
            return 1
        bullets = bullets_for(gathered) or [NO_CHANGES]
        bumped_manifest = bump_manifest(manifest, old, new)
        if bumped_manifest is None:
            print(f"{pkg_xml}: could not rewrite <version>{old}</version>", file=sys.stderr)
            return 1
        new_text = with_section(gathered["text"], f"{new} ({today})", bullets)
        prepared[name] = {
            "pkg_xml": pkg_xml,
            "manifest": bumped_manifest,
            "changelog": gathered["changelog"],
            "text": new_text,
            "entries": gathered["entries"],
            "bullets": bullets,
            "headers": gathered["headers"],
        }

    if all(p["bullets"] == [NO_CHANGES] for p in prepared.values()):
        print(
            "nothing to release: every included package has no qualifying change", file=sys.stderr
        )
        return 1

    for p in prepared.values():
        p["changelog"].write_text(p["text"])
        p["pkg_xml"].write_text(p["manifest"])

    body = summary_repo(new, bump, prepared, excluded)
    if summary_path:
        Path(summary_path).write_text(body)
    if version_out_path:
        Path(version_out_path).write_text(new + "\n")
    print(body, end="")
    print(f"\nwrote {len(prepared)} package(s) at {new}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--package", help="the package to release, by name")
    mode.add_argument(
        "--repo", action="store_true", help="release every package together, at one shared version"
    )
    ap.add_argument(
        "--bump",
        choices=BUMPS,
        help="the bump: overrides the derived one for --package, required for --repo",
    )
    ap.add_argument("--path", default=".", help="the repository root")
    ap.add_argument("--summary", help="write a Markdown summary for the pull request here")
    ap.add_argument("--version-out", help="write just the new version string here")
    args = ap.parse_args()
    os.chdir(args.path)

    if args.repo and not args.bump:
        print(
            "--repo needs --bump: there is no single commit history to derive one bump from",
            file=sys.stderr,
        )
        return 1

    if args.package:
        return release_package(args.package, args.bump, args.summary, args.version_out)
    return release_repo(args.bump, args.summary, args.version_out)


if __name__ == "__main__":
    sys.exit(main())
