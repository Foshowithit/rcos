#!/usr/bin/env python3
"""Compact the changelog of ~/.agents/AGENTS.md (the shared cross-agent memory).

Policy (set 2026-09-17 by the ZCode memory keeper):
  - Only the region from '## Changelog' onward is touched. User / Standing rules /
    Active projects / Deep memory sections are never rewritten by this script.
  - Each changelog entry is replaced by its bold headline (or its first ~220 chars
    when it has none) plus a trailing ellipsis marker. The file is an INDEX —
    full detail belongs in each tool's native memory; verbatim text is kept in
    ~/.agents/archive/ (a dated backup is written automatically before every run).
  - '#' headings inside the changelog are preserved verbatim.

Revised 2026-09-17 (bug fix, ZCode host-independence session):
  - The old headline regex anchored '**' to the date, so entries written as
    '- <date> TOPIC: ...' or '- <date> ⚠ **HEADLINE** ...' missed it and fell
    through to a raw line[:220] cut. 55 of 100 live entries ended mid-word, and
    two had their own headline amputated. Headlines are now found within the
    first few tokens, and every cut ends on a clause/word boundary.
  - --repair-from re-derives a mangled entry's digest from the verbatim text in
    ~/.agents/archive/ (matched by 200-char prefix), so an entry whose tail was
    cut can be re-digested from its full text instead of staying mangled.
    It is idempotent: re-running on an already-correct digest is a no-op.

Usage:
  python3 compact_agents_md.py [--dry-run] [--file PATH] [--repair-from [ARCHIVE ...]]
"""
import argparse
import glob
import os
import re
import sys
import time

DEFAULT_FILE = "/Users/adam26/.agents/AGENTS.md"
ARCHIVE_GLOB = "/Users/adam26/.agents/archive/AGENTS-*-full.md"
DIGEST_MAX = 220
HEADLINE_MAX = 300
PREFIX_KEY = 200

# The headline is a bold span in the entry's first few tokens, optionally after a
# label/marker ('- 09-17 RCOS FAM-C: **EPOCH-3 ...**', '- 09-17 ⚠ **...**'), not
# necessarily right after the date. The label is part of the digest, not dropped.
HEADLINE_RE = re.compile(
    r"^(- (?:20\d\d-)?\d\d-\d\d)\s+((?:\S+\s+){0,8})(\*\*.+?\*\*)"
)
# The keeper's own policy lines ('- ⚠ *...') state where the verbatim text lives.
# Digesting them would delete the pointer to the archive. Never touched.
POLICY_RE = re.compile(r"^- ⚠ \*")


def _balance(s: str) -> str:
    """Drop a dangling inline-code or bold marker left by a mid-token cut."""
    for mark in ("`", "**"):
        if s.count(mark) % 2:
            i = s.rfind(mark)
            if i > 0:
                s = s[:i]
    return s.rstrip(" ,;:-—–(")


def clip(s: str, n: int) -> str:
    """Cut to <= n chars on a clause/word boundary, never mid-word."""
    if len(s) <= n:
        return s
    cut = s[:n].rstrip()
    for sep in (". ", "; ", ", "):
        i = cut.rfind(sep)
        if i >= n * 0.5:
            return _balance(cut[: i + 1].rstrip()) + " …"
    i = cut.rfind(" ")
    if i > 0:
        cut = cut[:i]
    return _balance(cut) + " …"


def digest_entry(line: str) -> str:
    m = HEADLINE_RE.match(line)
    if m:
        d = f"{m.group(1)} {m.group(2)}{m.group(3)}"
        if len(d) > HEADLINE_MAX:
            return clip(d, HEADLINE_MAX)
        if len(line) > len(d):
            d += " …"
        return d
    return clip(line, DIGEST_MAX)


def load_verbatim(patterns) -> list:
    pool = []
    for pat in patterns:
        for path in sorted(glob.glob(pat), reverse=True):
            with open(path, encoding="utf-8") as fh:
                pool += [l for l in fh.read().split("\n") if l.startswith("- ")]
    return pool


def find_full(line: str, pool) -> str:
    """The archived verbatim line this digest was cut from, if archived."""
    key = line[:PREFIX_KEY]
    for cand in pool:
        if len(cand) > len(line) and cand.startswith(key):
            return cand
    return None


def backup(path: str) -> str:
    dst = f"{os.path.dirname(path)}/archive/AGENTS-{time.strftime('%Y%m%d-%H%M')}-pre-compact.md"
    if os.path.exists(dst):
        return dst
    with open(path, encoding="utf-8") as src, open(dst, "w", encoding="utf-8") as out:
        out.write(src.read())
    return dst


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=DEFAULT_FILE)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--repair-from", nargs="*", default=None, metavar="ARCHIVE",
                    help="archived verbatim files to re-derive mangled digests from")
    args = ap.parse_args()

    pool = load_verbatim(args.repair_from) if args.repair_from is not None \
        else load_verbatim([ARCHIVE_GLOB])

    with open(args.file, encoding="utf-8") as fh:
        src = fh.read()
    lines = src.split("\n")

    ci = next(i for i, l in enumerate(lines) if l.startswith("## Changelog"))
    head, body = lines[:ci], lines[ci:]

    out = []
    n_entries = n_kept = n_repaired = 0
    saved = 0
    for l in body:
        if not l.strip():
            continue
        if l.startswith("#"):
            out.append(l)
            continue
        if l.startswith("- ") and not POLICY_RE.match(l):
            n_entries += 1
            full = find_full(l, pool)
            if full is not None:
                n_repaired += 1
            d = digest_entry(full or l)
            saved += max(0, len(l) - len(d))
            out.append(d)
        elif l.startswith("- "):
            out.append(l)
        else:
            n_kept += 1
            out.append(clip(l, HEADLINE_MAX))
            print(f"NOTE non-entry line kept: {l[:90]!r}")

    new = "\n".join(head + out) + "\n"
    print(
        f"entries digested: {n_entries}  (re-derived from archive: {n_repaired})  "
        f"(bytes saved ~{saved/1024:.0f}KB)  non-entry lines kept: {n_kept}"
    )
    print(f"file: {len(src)/1024:.0f}KB -> {len(new)/1024:.0f}KB  "
          f"lines: {src.count(chr(10))} -> {new.count(chr(10))}")
    if args.dry_run:
        print("dry run: nothing written (entries that would change, first 8)")
        shown = 0
        for old, made in zip(
            [l for l in body if l.startswith("- ")],
            [l for l in out if l.startswith("- ")],
        ):
            if old != made and shown < 8:
                shown += 1
                print(f"  - {old[:100]}")
                print(f"  + {made[:100]}")
        return 0

    b = backup(args.file)
    print(f"backup: {b}")
    tmp = args.file + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(new)
    os.replace(tmp, args.file)
    print("written.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
