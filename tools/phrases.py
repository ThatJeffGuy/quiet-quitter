#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 That Scottish Guy
# SPDX-License-Identifier: AGPL-3.0-only
"""Export the console phrases to an editable text file, and import an edited one back.

  python3 tools/phrases.py export  ~/Downloads/quiet-quitter-phrases.txt
  python3 tools/phrases.py import  ~/Downloads/quiet-quitter-phrases.txt      # checks it, then rewrites phrases.json
  python3 tools/phrases.py check   ~/Downloads/quiet-quitter-phrases.txt      # checks only, changes nothing

The text file: [section] headers, one phrase per line, '#' lines and blank lines are ignored.
"""
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
JSON = HERE / "phrases.json"

WHEN = {
    "think": "The little 'thinking' word shown with a spinner just before a line is typed (it gets '...' added).",
    "boot": "Typed about 2 seconds after the page loads, when you have no personal greeting set (a personal greeting wins).",
    "idle": "Now and then when you've been quiet for a couple of minutes.",
    "view.jobs": "When you open the Jobs tab.", "view.docs": "When you open My documents.", "view.settings": "When you open Settings.", "view.admin": "When an admin opens Admin.",
    "status.applied": "You set a posting to Applied.", "status.interview": "...to Interview.", "status.offer": "...to Offer.", "status.rejected": "...to Rejected.",
    "status.withdrawn": "...to Withdrawn.", "status.not_interested": "...to Not interested.", "status.none": "...back to Not applied.",
    "input.mode": "You change the category. {mode} = the category's name (lower case).", "input.src": "You pick an employer.", "input.sort": "You change the sort order.",
    "input.status_on": "You choose a status filter.", "input.status_off": "You clear the status filter.", "input.radius_on": "You set a distance limit.", "input.radius_off": "You remove the distance limit.",
    "input.hideapplied_on": "You tick Hide applied jobs.", "input.hideapplied_off": "You untick it.", "input.union_on": "You tick Unionized only.", "input.union_off": "You untick it.",
    "input.newonly_on": "You tick New since my last visit.", "input.newonly_off": "You untick it.", "input.search": "A moment after you stop typing in the search box. {q} = what you typed.",
    "one.open_post": "You click View job post.", "one.gossip": "You click Share > Email to someone.", "one.copy": "You click Share > Copy link.", "one.compare": "You open the Keyword Finder.",
    "one.chatter_on": "You switch Console chatter back on in Settings.", "one.filter_drawer": "You open the Filters drawer.", "one.saved": "You save your Settings.",
    "one.dark": "You switch to dark mode.", "one.light": "You switch to light mode.", "one.tailor": "You open Tailor Resume.", "one.tailor_redo": "You redraft in Tailor Resume.",
    "egg.warning": "EASTER EGG: the 5th quick click on the donut.",
    "egg.hack": "EASTER EGG: the pretend 'hacking' lines after the 10th click, in order. Add ' |bar' at the end of a line to show a progress bar on it.",
    "egg.ready": "EASTER EGG: shown while the audio plays.", "egg.received": "EASTER EGG: when the audio finishes by itself.", "egg.restored": "EASTER EGG: when you stop it early with 'restore protocols'.",
    "egg.missing": "EASTER EGG: shown instead of the audio if the sound file isn't installed on the server.",
}
PLACEHOLDERS = {"input.mode": {"mode"}, "input.search": {"q"}}
MAX_LEN = 110            # roughly what fits on the pill at desktop width before it is cut off with an ellipsis

HEADER = """# THE QUIET QUITTER - console phrases
#
# Change any line to whatever you like. Rules:
#   - one phrase per line, under its [section] heading
#   - lines starting with # and blank lines are ignored
#   - you can add or delete lines in a section (the console picks one at random); keep at least one per section
#   - do not rename or delete the [section] headings
#   - {mode} and {q} are fill-ins (see the notes under the sections that use them); leave them as they are
#   - the pill fits about %d characters on a desktop screen; longer lines get cut off with ...
#   - your personal greeting (the line typed at the start) is set in the Admin tab, not here
""" % MAX_LEN


def export(out):
    data = json.loads(JSON.read_text())
    lines = [HEADER]
    for key, phrases in data.items():
        lines += ["", f"[{key}]", f"# {WHEN.get(key, '')}".rstrip()] + list(phrases)
    Path(out).expanduser().write_text("\n".join(lines) + "\n")
    print(f"wrote {out}: {len(data)} sections, {sum(len(v) for v in data.values())} phrases")


def parse(path):
    current = json.loads(JSON.read_text())
    out, cur, problems, warnings = {}, None, [], []
    for n, raw in enumerate(Path(path).expanduser().read_text().splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = re.fullmatch(r"\[([a-z0-9_.]+)\]", line)
        if m:
            cur = m.group(1)
            if cur not in current:
                problems.append(f"line {n}: unknown section [{cur}] (sections can't be added or renamed)")
            elif cur in out:
                problems.append(f"line {n}: section [{cur}] appears twice")
            out[cur] = []
            continue
        if cur is None:
            problems.append(f"line {n}: text before the first [section] heading: {line[:40]!r}")
            continue
        if cur in current:
            bad = set(re.findall(r"\{(\w*)\}", line)) - PLACEHOLDERS.get(cur, set())
            if bad:
                problems.append(f"line {n}: [{cur}] has an unknown fill-in {{{sorted(bad)[0]}}}")
            if line.count("{") != line.count("}"):
                problems.append(f"line {n}: unbalanced curly braces")
            body = re.sub(r"\s*\|bar\s*$", "", line)
            if len(body) > MAX_LEN:
                warnings.append(f"line {n}: {len(body)} characters, may be cut off on the pill: {body[:50]}...")
            if "|bar" in body:
                problems.append(f"line {n}: '|bar' only goes at the very end of a line")
            if "<" in line and ">" in line:
                warnings.append(f"line {n}: contains < and >; it will be shown as plain text, not HTML")
        out.setdefault(cur, []).append(line)
    for key in current:
        if key not in out:
            problems.append(f"missing section [{key}]")
        elif not out[key]:
            problems.append(f"section [{key}] is empty (keep at least one phrase)")
    return out, problems, warnings, current


def check(path, write=False):
    out, problems, warnings, current = parse(path)
    for w in warnings:
        print("warning:", w)
    for p in problems:
        print("PROBLEM:", p)
    if problems:
        print(f"\n{len(problems)} problem(s): nothing was changed.")
        return 1
    changed = sum(1 for k in current if out[k] != current[k])
    print(f"ok: {len(out)} sections, {sum(len(v) for v in out.values())} phrases; {changed} section(s) differ from the current file.")
    if write:
        backup = JSON.with_name(f"phrases.json.bak-{datetime.now():%Y%m%d-%H%M%S}")
        shutil.copy2(JSON, backup)
        JSON.write_text(json.dumps({k: out[k] for k in current}, indent=1, ensure_ascii=False) + "\n")
        print(f"wrote {JSON} (previous copy kept as {backup.name})")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] not in ("export", "import", "check"):
        sys.exit(__doc__)
    if sys.argv[1] == "export":
        export(sys.argv[2])
    else:
        sys.exit(check(sys.argv[2], write=sys.argv[1] == "import"))
