#!/usr/bin/env python3
"""Fail if anything that looks like a real tenant identifier is in the repo.

Generic rules (always on):
  * email addresses must use a placeholder domain (contoso.com, example.com)
  * SharePoint / tenant hosts must be contoso.sharepoint.com / contoso.onmicrosoft.com
  * GUIDs must be the all-zero placeholder
  * no bearer tokens, SAS signatures, or flow trigger signatures

Private rules (optional): pass --denylist FILE with one regular expression per line
(case-insensitive) for names that must never appear: the real organization, people,
sites, vendors. Keep that file OUT of the repo: it is listed in .gitignore, because
committing it would publish the very terms it protects.

Usage: python3 scripts/check_sanitization.py [--denylist .sanitize-denylist.txt] [paths...]
"""
import argparse
import re
import sys
from pathlib import Path

ALLOWED_EMAIL_DOMAINS = {"contoso.com", "example.com"}
ALLOWED_GUIDS = {"00000000-0000-0000-0000-000000000000"}
TEXT_SUFFIXES = {".json", ".md", ".py", ".yml", ".yaml", ".txt", ".ps1", ".xml", ".html", ".csv"}
SKIP_DIRS = {".git", "node_modules", "__pycache__"}

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})")
SP_HOST = re.compile(r"\b([A-Za-z0-9-]+)(?:-my|-admin)?\.sharepoint\.com", re.I)
TENANT = re.compile(r"\b([A-Za-z0-9-]+)\.onmicrosoft\.com", re.I)
GUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)
SECRETS = [
    (re.compile(r"Bearer\s+[A-Za-z0-9\-_.=]{20,}"), "bearer token"),
    (re.compile(r"[?&]sig=[A-Za-z0-9%/+=]{20,}"), "URL signature (SAS / HTTP trigger)"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\."), "JWT"),
]


def files(paths):
    for p in paths:
        p = Path(p)
        if p.is_file():
            yield p
        elif p.is_dir():
            for f in p.rglob("*"):
                if f.is_file() and f.suffix.lower() in TEXT_SUFFIXES and not (set(f.parts) & SKIP_DIRS):
                    yield f


def scan(path, deny):
    problems = []
    for lineno, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
        for m in EMAIL.finditer(line):
            if m.group(1).lower() not in ALLOWED_EMAIL_DOMAINS:
                problems.append((lineno, f"email with non-placeholder domain: {m.group(0)}"))
        for m in SP_HOST.finditer(line):
            if m.group(1).lower() != "contoso":
                problems.append((lineno, f"SharePoint host is not contoso: {m.group(0)}"))
        for m in TENANT.finditer(line):
            if m.group(1).lower() != "contoso":
                problems.append((lineno, f"tenant is not contoso: {m.group(0)}"))
        for m in GUID.finditer(line):
            if m.group(0).lower() not in ALLOWED_GUIDS:
                problems.append((lineno, f"non-placeholder GUID: {m.group(0)}"))
        for rx, what in SECRETS:
            if rx.search(line):
                problems.append((lineno, f"possible secret: {what}"))
        for rx in deny:
            m = rx.search(line)
            if m:
                problems.append((lineno, f"deny-listed term: '{m.group(0)}'"))
    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--denylist", help="file of private regexes (one per line, case-insensitive)")
    ap.add_argument("paths", nargs="*", default=["."])
    args = ap.parse_args()

    deny = []
    if args.denylist:
        for raw in Path(args.denylist).read_text().splitlines():
            raw = raw.strip()
            if raw and not raw.startswith("#"):
                deny.append(re.compile(raw, re.I))

    total = 0
    for f in sorted(files(args.paths)):
        if args.denylist and f.resolve() == Path(args.denylist).resolve():
            continue
        for lineno, msg in scan(f, deny):
            print(f"{f}:{lineno}: {msg}")
            total += 1
    print(f"{'FAIL' if total else 'ok'}: {total} finding(s)"
          + (f", {len(deny)} private rule(s) applied" if deny else ", generic rules only"))
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
